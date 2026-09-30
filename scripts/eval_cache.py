"""Semantic-cache evaluation (no LLM calls): hit rate on unseen paraphrases, false-hit rate on near-miss /
out-of-domain queries, lookup latency, threshold sweep and guard ablation. Writes eval/cache_eval.json."""
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config  # noqa: E402
from app.cache import get_cache, siis_hash  # noqa: E402
from app.embed import _embed_one_cached  # noqa: E402
from app.retrieval import kb, siis_to_text  # noqa: E402

EVAL = config.ROOT / "eval"


def load(name):
    p = EVAL / name
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


def run(cache, paras, negs, rows, with_siis: bool):
    art_hash = {r["id"]: siis_hash(siis_to_text(r["siis_response"])) for r in rows}
    siis_of = {r["id"]: siis_to_text(r["siis_response"]) for r in rows}
    hits = correct = 0
    lat = []
    _embed_one_cached.cache_clear()          # measure real embedding cost, not the LRU
    for p in paras:
        t = time.perf_counter()
        e, _ = cache.lookup(p["text"], siis_of[p["row"]] if with_siis else "")
        lat.append((time.perf_counter() - t) * 1000)
        if e:
            hits += 1
            correct += e.get("siis_hash") == art_hash[p["row"]]   # served a plan built from the right article
    false_hits = 0
    fh_examples = []
    for n in negs:
        e, info = cache.lookup(n["text"], "")
        if e:
            false_hits += 1
            fh_examples.append({"query": n["text"][:90], "served": e["query"][:90], "sim": info.get("similarity")})
    return {
        "n_paraphrases": len(paras), "hit_rate": round(hits / max(1, len(paras)), 4),
        "correct_hit_rate": round(correct / max(1, len(paras)), 4),
        "n_negatives": len(negs), "false_hit_rate": round(false_hits / max(1, len(negs)), 4),
        "lookup_ms_p50": round(float(np.percentile(lat, 50)), 2), "lookup_ms_p95": round(float(np.percentile(lat, 95)), 2),
        "false_hit_examples": fh_examples[:5],
    }


def main():
    cache = get_cache()
    rows = kb().rows
    paras = load("heldout_paraphrases.jsonl") + load("human_paraphrases.jsonl")
    paras = [p for p in paras if p.get("row") in {r["id"] for r in rows}]
    negs = load("adversarial.jsonl")
    cache.lookup("warm up", "")
    out = {"cache_entries": len(cache.entries), "cache_vectors": int(len(cache.mat))}
    out["ours_with_siis"] = run(cache, paras, negs, rows, with_siis=True)
    out["ours_query_only"] = run(cache, paras, negs, rows, with_siis=False)
    cache.guard_enabled = False
    out["no_guard_query_only"] = run(cache, paras, negs, rows, with_siis=False)
    cache.guard_enabled = True
    sweep = []
    tau0, low0 = cache.tau, cache.tau_low
    for tau in (0.80, 0.83, 0.86, 0.89, 0.92):
        cache.tau, cache.tau_low = tau, tau
        r = run(cache, paras, negs, rows, with_siis=False)
        sweep.append({"tau": tau, "hit_rate": r["hit_rate"], "correct_hit_rate": r["correct_hit_rate"],
                      "false_hit_rate": r["false_hit_rate"]})
    cache.tau, cache.tau_low = tau0, low0
    out["threshold_sweep_query_only"] = sweep
    (EVAL / "cache_eval.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    for k in ("ours_with_siis", "ours_query_only", "no_guard_query_only"):
        v = out[k]
        print(f"{k:22} hit={v['hit_rate']:.1%} correct={v['correct_hit_rate']:.1%} false_hit={v['false_hit_rate']:.1%} "
              f"lookup p50={v['lookup_ms_p50']}ms p95={v['lookup_ms_p95']}ms")
    for s in sweep:
        print("  sweep", s)
    for ex in out["ours_query_only"]["false_hit_examples"]:
        print("  FH:", ex)


if __name__ == "__main__":
    main()
