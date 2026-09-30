"""End-to-end latency benchmark against the running API (client-side wall clock, N >= 30 per path).

    python -m scripts.bench --url http://localhost:8000 [--cold 30] [--cold-gap 20]

paths: exact cache hit | unseen-paraphrase cache hit | cold (full pipeline, fresh LLM calls)
Writes eval/bench.json.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import httpx
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config  # noqa: E402

EVAL = config.ROOT / "eval"


def pct(xs, p):
    return round(float(np.percentile(xs, p)), 1) if xs else None


def summary(xs, server, costs=None):
    out = {"n": len(xs), "p50_ms": pct(xs, 50), "p95_ms": pct(xs, 95), "max_ms": round(max(xs), 1) if xs else None,
           "server_p50_ms": pct(server, 50), "server_p95_ms": pct(server, 95)}
    if costs is not None:
        out["avg_cost_usd"] = round(float(np.mean(costs)), 6) if costs else None
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")  # not "localhost": Windows tries IPv6 first (+2 s per new connection)
    ap.add_argument("--cold", type=int, default=30)
    ap.add_argument("--cold-gap", type=float, default=20.0, help="seconds between cold calls (provider TPM limits)")
    ap.add_argument("--skip-cold", action="store_true")
    a = ap.parse_args()
    rows = {r["id"]: r for r in json.loads(config.SIIS_PATH.read_text(encoding="utf-8"))["responses"]}
    paras = [json.loads(l) for l in (EVAL / "heldout_paraphrases.jsonl").read_text(encoding="utf-8").splitlines() if l]
    c = httpx.Client(base_url=a.url, timeout=120)
    assert c.get("/health").json()["status"] == "ok"
    res = {}

    # ---- exact hits: the original scenarios, repeated
    lat, srv = [], []
    for i in range(40):
        r = list(rows.values())[i % len(rows)]
        t = time.perf_counter()
        o = c.post("/v1/troubleshoot", json={"query": r["original_query"], "siis_response": r["siis_response"]}).json()
        lat.append((time.perf_counter() - t) * 1000)
        srv.append(o["meta"]["latency_ms"])
        assert o["meta"]["cache_hit"], "expected exact hit - run build_cache first"
    res["cache_hit_exact"] = summary(lat, srv)
    print("exact hit    ", res["cache_hit_exact"])

    # ---- paraphrase hits (unseen wording)
    lat, srv, n_hit = [], [], 0
    for p in paras:
        r = rows[p["row"]]
        t = time.perf_counter()
        o = c.post("/v1/troubleshoot", json={"query": p["text"], "siis_response": r["siis_response"]},
                   params={"lookup_only": "true"}).json()
        dt = (time.perf_counter() - t) * 1000
        if o["meta"]["cache_hit"]:
            n_hit += 1
            lat.append(dt)
            srv.append(o["meta"]["latency_ms"])
    res["cache_hit_paraphrase"] = summary(lat, srv)
    res["cache_hit_paraphrase"]["hit_rate"] = round(n_hit / len(paras), 4)
    print("para hit     ", res["cache_hit_paraphrase"])

    # ---- cold path
    if not a.skip_cold:
        lat, srv, costs, fallbacks = [], [], [], 0
        picks = paras[:: max(1, len(paras) // a.cold)][: a.cold]
        for i, p in enumerate(picks):
            r = rows[p["row"]]
            t = time.perf_counter()
            o = c.post("/v1/troubleshoot", json={"query": p["text"], "siis_response": r["siis_response"]},
                       params={"nocache": "true", "fresh": "true"}).json()
            dt = (time.perf_counter() - t) * 1000
            if o["meta"].get("fallback") == "engine_error":
                fallbacks += 1
                print("   engine_error:", o["meta"].get("error", "")[:120])
            else:
                lat.append(dt)
                srv.append(o["meta"]["latency_ms"])
                costs.append(o["meta"]["cost_usd"])
            print(f"   cold {i + 1}/{len(picks)} {dt:.0f}ms ${o['meta']['cost_usd']:.5f}")
            time.sleep(a.cold_gap)
        res["cold"] = summary(lat, srv, costs)
        res["cold"]["engine_errors"] = fallbacks
        print("cold         ", res["cold"])
    prev = json.loads((EVAL / "bench.json").read_text()) if (EVAL / "bench.json").exists() else {}
    prev.update(res)
    (EVAL / "bench.json").write_text(json.dumps(prev, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
