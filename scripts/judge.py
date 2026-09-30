"""LLM-as-judge accuracy + deeplink-mapping ablation.

For every provided scenario:
  * Step accuracy (0-3): completeness, correctness vs the SIIS reference, ordering (safe first, critical last)
  * Deeplink relevance (0-2) per action with a deeplink: 2 = exact target screen, 1 = parent/related, 0 = wrong
Ablation re-runs ONLY the deeplink stage (extraction is identical) with fresh LLM calls:
  Baseline full_llm | A hybrid_only (BM25+dense) | B rules_only | ours (exact-leaf + hybrid + depth rerank + closed-set LLM)
Writes eval/judge.json and eval/ablation.json.
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config  # noqa: E402
from app.llm import chat_json  # noqa: E402
from app.pipeline import troubleshoot  # noqa: E402
from app.retrieval import catalog, kb, siis_to_text  # noqa: E402

config.LLM_MAX_WAIT_S = 120
EVAL = config.ROOT / "eval"
# judge = different model family than the generator (no self-grading); Gemini pool, falls back to Groq
JUDGE_POOL = ["gemini-3.6-flash", "gemini-3-flash-preview", "gemini-3.8-flash", "gemini-flash-lite-latest",
              "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
JUDGE_MODEL = JUDGE_POOL[0]


async def judge_call(system, user, max_tokens):
    if config.BASELINE_API_KEY:
        try:
            return await chat_json(system, user, model=JUDGE_MODEL, max_tokens=max_tokens,
                                   base_url=config.BASELINE_BASE_URL, api_key=config.BASELINE_API_KEY, pool=JUDGE_POOL)
        except Exception as e:  # noqa: BLE001
            print("   gemini judge unavailable, falling back:", str(e)[:100])
    return await chat_json(system, user, model=config.LLM_MODEL, max_tokens=max_tokens)

STEP_SYS = """You are a strict QA reviewer for device troubleshooting plans.
Given a customer complaint, the reference article, and a generated plan, score the plan's STEP ACCURACY:
3 = complete, correct (every step supported by the reference and relevant to the complaint), well ordered
ORDERING CONTRACT (fixed product rule - never penalise it): actions appear in category blocks
  [auto] ... then [manual] ... then [critical] ...
Example of a CORRECT order: [auto] Adjust Brightness, [manual] Inspect Device, [manual] Contact Service Center,
[critical] Force Restart. Critical actions (restart, safe mode, reset, clear data, updates) at the END is CORRECT.
Only judge ordering WITHIN a block against the reference. Judge content: correctness, grounding, completeness.
2 = mostly correct; minor omissions or ordering issues
1 = partially correct; notable missing/irrelevant/unsupported steps
0 = wrong, irrelevant or hallucinated
If the plan is EMPTY: score 3 if the reference truly has nothing relevant to the complaint, else 0.
Return JSON {"score": <0-3>, "reason": "<one sentence>"}"""

DL_SYS = """You grade deeplink mappings. Each action lists its steps and the Settings deeplink attached to it
(message + description of the target screen). Score EACH action:
2 = the deeplink opens exactly the screen/toggle where the steps happen
1 = related but a parent menu / neighbouring screen / generic placeholder naming the right screen
0 = wrong screen
Return JSON {"scores": [{"i": <action index>, "score": <0-2>}]}"""


def plan_text(resp: dict) -> str:
    out = []
    for g in resp["contexts"]:
        out.append(f"GOAL: {g['goal']} ({g['title']})")
        for a in g["actions"]:
            out.append(f"  [{a['category']}] {a['actionName']}: " + " ".join(a["stepGroups"][0]["steps"]))
    return "\n".join(out) or "(empty plan)"


def dl_items(resp: dict) -> list[dict]:
    items = []
    for g in resp["contexts"]:
        for a in g["actions"]:
            dl = a["stepGroups"][0].get("actionableDeeplink")
            if dl:
                items.append({"action": a["actionName"], "steps": a["stepGroups"][0]["steps"], "dl": dl})
    return items


async def judge_steps(row, resp):
    user = (f"Complaint: {row['original_query']}\n\nReference article:\n{siis_to_text(row['siis_response'])[:6000]}"
            f"\n\nPlan:\n{plan_text(resp)}")
    r = await judge_call(STEP_SYS, user, 400)
    return float(r.get("score", 0)), r.get("reason", "")


async def judge_dls(items):
    if not items:
        return []
    lines = "\n".join(f"{i}. {it['action']} | steps: {' '.join(it['steps'])} | deeplink: "
                      f"{it['dl']['message']} - {it['dl']['description']}" for i, it in enumerate(items))
    r = await judge_call(DL_SYS, lines, 600)
    sc = {int(x["i"]): float(x["score"]) for x in r.get("scores", []) if str(x.get("i", "")).isdigit()}
    return [sc.get(i, 0.0) for i in range(len(items))]


async def main(modes):
    rows = kb().rows
    dummy = catalog().dummy["deeplink"]
    ablation, judge_rows = {}, []
    for mode in modes:
        lat, cost, dl_scores, settings_actions, real_dl = [], [], [], 0, 0
        step_scores = []
        for row in rows:
            out = await troubleshoot(row["original_query"], row["siis_response"], use_cache=False,
                                     write_cache=False, debug=True, mapping_mode=mode, fresh_mapping=True)
            resp = out["response"]
            tr = out.get("trace", {})
            if out["meta"].get("fallback") == "engine_error":
                print("   engine_error:", out["meta"].get("error", "")[:160])
            lat.append(tr.get("stages", {}).get("deeplink_mapping_ms", 0))
            cost.append(tr.get("mapping_cost_usd", 0.0))
            items = dl_items(resp)
            scores = await judge_dls(items)
            dl_scores += scores
            for g in resp["contexts"]:
                for a in g["actions"]:
                    if a["category"] != "manual" or a["stepGroups"][0].get("actionableDeeplink"):
                        settings_actions += 1
            real_dl += sum(1 for it in items if it["dl"]["deeplink"] != dummy)
            if mode == "ours":
                s, why = await judge_steps(row, resp)
                step_scores.append(s)
                judge_rows.append({"id": row["id"], "step_score": s, "reason": why, "dl_scores": scores,
                                   "n_goals": len(resp["contexts"]), "fallback": out["meta"].get("fallback")})
            print(f"  {mode:12} {row['id']:7} dl={scores} map={lat[-1]}ms")
        ablation[mode] = {
            "deeplink_relevance_avg_0_2": round(float(np.mean(dl_scores)), 3) if dl_scores else None,
            "n_deeplinks": len(dl_scores), "real_catalog_deeplinks": real_dl,
            "mapping_latency_p50_ms": float(np.percentile(lat, 50)), "mapping_latency_p95_ms": float(np.percentile(lat, 95)),
            "mapping_cost_per_query_usd": round(float(np.mean(cost)), 6),
        }
        if step_scores:
            ablation[mode]["step_accuracy_avg_0_3"] = round(float(np.mean(step_scores)), 3)
        print(mode, ablation[mode])
        prev = json.loads((EVAL / "ablation.json").read_text()) if (EVAL / "ablation.json").exists() else {}
        prev.update(ablation)                                   # save after every variant
        (EVAL / "ablation.json").write_text(json.dumps(prev, indent=2), encoding="utf-8")
        if judge_rows:
            (EVAL / "judge.json").write_text(json.dumps(judge_rows, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--modes", default="ours,hybrid_only,rules_only,full_llm")
    a = ap.parse_args()
    t = time.time()
    asyncio.run(main(a.modes.split(",")))
    print(f"done in {time.time() - t:.0f}s")
