"""Builds the evaluation sets (kept separate from the cache-warming paraphrases):

eval/heldout_paraphrases.jsonl  - 5 paraphrases per scenario written by a DIFFERENT model + prompt than the
                                  enrichment stage (avoids paraphrase leakage inflating the hit rate)
eval/adversarial.jsonl          - near-miss complaints: same component, DIFFERENT problem (must NOT hit),
                                  polarity flips and out-of-domain queries
eval/human_paraphrases.jsonl    - optional, written by the team (same format as heldout)
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config  # noqa: E402
from app.llm import chat_json  # noqa: E402
from app.retrieval import kb  # noqa: E402

config.LLM_MAX_WAIT_S = 120
EVAL = config.ROOT / "eval"

PARA_SYS = """You simulate real customers contacting phone support. Rewrite the complaint 5 times as 5 DIFFERENT people would
type it into a support chat: vary length, vocabulary and tone (one very short, one rambling, one with typos,
one angry, one polite). Keep exactly the same problem; do not add symptoms; do not copy phrases from the original.
Return JSON {"paraphrases": ["...", "...", "...", "...", "..."]}"""

NEG_SYS = """You create hard NEGATIVE test cases for a troubleshooting cache. Given a complaint, write 2 complaints about the
SAME device part that describe a clearly DIFFERENT problem needing a different fix (e.g. 'screen too dim' vs
'screen flickers'; 'keeps turning ON by itself' vs 'keeps turning OFF by itself'). Keep the wording style close
to the original so they look similar. Return JSON {"negatives": ["...", "..."]}"""

OOD = [
    "My car's bluetooth won't pair with the dashboard screen",
    "How do I bake sourdough bread at home?",
    "My laptop keyboard keys are sticking after I spilled coffee",
    "The refrigerator is making a loud buzzing noise at night",
    "My WiFi keeps turning on by itself even after I switch it off",
    "My WiFi keeps turning off by itself even though I switch it on",
    "Phone battery drains really fast overnight",
    "Camera app crashes when I switch to video mode",
    "I want to change my ringtone to a custom song",
    "The phone speaker crackles when I play music loudly",
]


async def main():
    EVAL.mkdir(exist_ok=True)
    rows = kb().rows
    sem = asyncio.Semaphore(2)

    async def one(r):
        async with sem:
            p = await chat_json(PARA_SYS, f"Complaint: {r['original_query']}", model=config.LLM_MODEL, max_tokens=900)
            n = await chat_json(NEG_SYS, f"Complaint: {r['original_query']}", model=config.LLM_MODEL, max_tokens=600)
            return r, p.get("paraphrases", [])[:5], n.get("negatives", [])[:2]

    res = await asyncio.gather(*(one(r) for r in rows))
    with (EVAL / "heldout_paraphrases.jsonl").open("w", encoding="utf-8") as f:
        for r, ps, _ in res:
            for p in ps:
                f.write(json.dumps({"row": r["id"], "text": p, "source": "llm_heldout"}, ensure_ascii=False) + "\n")
    with (EVAL / "adversarial.jsonl").open("w", encoding="utf-8") as f:
        for r, _, ns in res:
            for n in ns:
                f.write(json.dumps({"row": r["id"], "text": n, "type": "near_miss"}, ensure_ascii=False) + "\n")
        for q in OOD:
            f.write(json.dumps({"row": None, "text": q, "type": "out_of_domain"}, ensure_ascii=False) + "\n")
    print("paraphrases:", sum(len(p) for _, p, _ in res), "| near-miss:", sum(len(n) for *_, n in res), "| ood:", len(OOD))


if __name__ == "__main__":
    asyncio.run(main())
