"""Deeplink-resolution benchmark with ground truth.

1. Sample N phone Settings entries from the catalog (open-page / enable / disable), stratified.
2. An LLM writes a realistic troubleshooting action that ends on that screen (steps, navigation path, direction),
   told NOT to reuse the catalog wording.  -> eval/deeplink_bench.jsonl  (generated once, then reused)
3. Every mapping variant resolves every action; accuracy@1 = exact catalog entry, plus "same screen" accuracy
   (right screen, wrong on/off twin) and "no deeplink" rate.  -> eval/deeplink_eval.json
"""
import argparse
import asyncio
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config  # noqa: E402
from app.llm import BYPASS_DISK_CACHE, chat_json, start_usage  # noqa: E402
from app.pipeline import map_deeplinks  # noqa: E402
from app.retrieval import catalog  # noqa: E402

config.LLM_MAX_WAIT_S = 120
EVAL = config.ROOT / "eval"
BENCH = EVAL / "deeplink_bench.jsonl"

GEN_SYS = """You write one step of a phone troubleshooting guide. Given a Settings target, describe the user action
that reaches it, the way a support article would. Do NOT copy the target's wording verbatim; use natural phrasing.
Return JSON {"actionName": "<Title Case, 2-5 words>", "screen": "Settings > <menu> > ... > <final screen>",
"toggle": "enable" | "disable" | "open", "steps": ["Navigate to and open Settings.", "Tap on <menu>.", "...", "<final interaction>."]}"""


def screen_key(e):
    d = (e.get("description") or "").lower()
    for p in ("opens the ", "enables ", "disables ", "updates the "):
        if d.startswith(p):
            d = d[len(p):]
    return d.split(" via ")[0].split(" settings page")[0].split(" in device")[0].strip()


async def build(n: int):
    cat = catalog()
    phone = [e for e in cat.search if e.get("originalType") in ("onClickURL", "onURL", "offURL")
             and "device Settings" in (e.get("description") or "")]
    rnd = random.Random(7)
    by_type = {t: [e for e in phone if e["originalType"] == t] for t in ("onClickURL", "onURL", "offURL")}
    picks = rnd.sample(by_type["onClickURL"], n // 2) + rnd.sample(by_type["onURL"], n // 4) + \
        rnd.sample(by_type["offURL"], n - n // 2 - n // 4)
    out = []
    for e in picks:
        target = f"type={e['originalType']} | {e['message']} | {e['description']} | {e.get('qna_description', '')}"
        a = await chat_json(GEN_SYS, target, model=config.LLM_ENRICH_MODEL, max_tokens=500)
        out.append({"target_id": e["id"], "action": a})
    BENCH.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in out) + "\n", encoding="utf-8")
    return out


async def evaluate(items, modes):
    cat = catalog()
    res = {}
    for mode in modes:
        exact = same_screen = none = 0
        lat, cost = [], []
        for it in items:
            a = dict(it["action"])
            a.setdefault("kind", "setting")
            a["category"] = "auto"
            a["actionName"] = a.get("actionName") or "Open Setting"
            a["steps"] = a.get("steps") or []
            u = start_usage()
            tok = BYPASS_DISK_CACHE.set(True)
            t = time.perf_counter()
            try:
                await map_deeplinks([a], mode=mode)
            finally:
                BYPASS_DISK_CACHE.reset(tok)
            lat.append((time.perf_counter() - t) * 1000)
            cost.append(u.cost_usd)
            dl = a.get("_dl")
            tgt = cat.by_id[it["target_id"]]
            chosen = next((e for e in cat.entries if dl and e["deeplink"] == dl["deeplink"]), None)
            if not chosen or chosen["id"] == "DL-DUMMY":
                none += 1
            elif chosen["id"] == tgt["id"]:
                exact += 1
            elif screen_key(chosen) == screen_key(tgt):
                same_screen += 1
        n = len(items)
        lat.sort()
        res[mode] = {"n": n, "accuracy_at_1": round(exact / n, 3), "same_screen_wrong_direction": round(same_screen / n, 3),
                     "no_deeplink": round(none / n, 3), "latency_p50_ms": round(lat[n // 2], 1),
                     "latency_p95_ms": round(lat[int(0.95 * (n - 1))], 1), "cost_per_action_usd": round(sum(cost) / n, 6)}
        print(mode, res[mode])
        prev = json.loads((EVAL / "deeplink_eval.json").read_text()) if (EVAL / "deeplink_eval.json").exists() else {}
        prev.update({mode: res[mode]})
        (EVAL / "deeplink_eval.json").write_text(json.dumps(prev, indent=2), encoding="utf-8")


async def main(n, modes):
    items = [json.loads(l) for l in BENCH.read_text(encoding="utf-8").splitlines() if l.strip()] \
        if BENCH.exists() else await build(n)
    print("bench actions:", len(items))
    await evaluate(items, modes)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--modes", default="ours,hybrid_only,rules_only,full_llm")
    a = ap.parse_args()
    asyncio.run(main(a.n, a.modes.split(",")))
