"""Catalog-grounded fallback (opt-in): when no knowledge-base article covers a complaint, build a short plan from
the Settings deeplink catalog itself - the only other reference data we were given.

The LLM may only CHOOSE catalog entries (by id) that relate to the complaint; every action, step and deeplink is
then written by code from that entry's own message/description, so nothing is invented. Confidence is capped
because a catalog entry says *what a setting does*, not *that it fixes this fault*.
"""
import re

from . import rules
from .llm import chat_json
from .retrieval import catalog
from .text import title_case

CAT_SYS = """You help a phone support agent. No troubleshooting article exists for this complaint, so you may only
suggest device Settings from the candidate list below (id | type | name | what it does).
Pick at most 4 entries that a support agent would realistically suggest for THIS complaint. Only pick an entry
if what it does clearly relates to the symptom; prefer fewer, better picks. Respect direction: onURL turns a
setting ON, offURL turns it OFF, onClickURL opens a settings page.
If nothing relates, return an empty "picks" list and relevance 0.
If the complaint is not about a phone/tablet at all (a car, an appliance, cooking, general questions), return
no picks and relevance 0 - never force a suggestion.
Return ONLY JSON:
{"topic": "<2-4 word Title Case topic>", "title": "<2-3 word sentence-case title>",
 "relevance": <0-1, how likely these settings help>,
 "picks": [{"id": "<candidate id>", "description": "<exactly 5-7 words starting 'It will'>"}]}"""

_VERB = re.compile(r"^(enable|disable|view|adjust|increase|decrease|check|set|switch|turn on|turn off|open)\s+", re.I)
MAX_SCORE = 0.7


def _target(e: dict) -> str:
    t = _VERB.sub("", (e.get("message") or "").strip()) or e.get("description", "setting")
    return t[0].upper() + t[1:] if t else "Setting"


def _steps(e: dict) -> list[str]:
    target, typ = _target(e), e.get("originalType")
    first = f"Tap the one-tap link to open {target} in Settings."
    if typ == "onURL":
        return [first, f"Turn on {target}."]
    if typ == "offURL":
        return [first, f"Turn off {target}."]
    if typ == "updateURL":
        return [first, f"Adjust {target} to a comfortable level."]
    return [first, f"Review the {target} options and change them if needed."]


def _action_name(e: dict) -> str:
    msg = (e.get("message") or _target(e)).strip()
    msg = re.sub(r"^view\s+", "Open ", msg, flags=re.I)
    return title_case(msg)


async def build(query: str, enrich: dict, model: str) -> tuple[list[dict], dict]:
    cat = catalog()
    q = f"{enrich.get('canonical_query') or ''} {query}"
    cands = [e for e, _ in cat.retrieve(q, 24)
             if "device Settings" in (e.get("description") or "") or e.get("qna_description")][:14]
    info = {"candidates": [f'{e["id"]}: {e.get("message")}' for e in cands[:6]]}
    if not cands:
        return [], info
    lines = "\n".join(f'{e["id"]} | {e.get("originalType") or "-"} | {e.get("message")} | '
                      f'{e.get("qna_description") or e.get("description")}' for e in cands)
    res = await chat_json(CAT_SYS, f"Complaint: {query}\n\nCandidates:\n{lines}", model=model, max_tokens=700)
    allowed = {e["id"]: e for e in cands}
    picks = [p for p in (res.get("picks") or []) if str(p.get("id")) in allowed][:4]
    rel = float(res.get("relevance") or 0)
    info.update(picked=[p["id"] for p in picks], relevance=rel)
    if not picks or rel < 0.6:
        return [], info
    actions, seen = [], set()
    for p in picks:
        e = allowed[p["id"]]
        if _action_name(e).lower() in seen:        # catalog has same-named twins for different pages
            continue
        seen.add(_action_name(e).lower())
        a = {"actionName": _action_name(e), "kind": "setting", "toggle": "none", "screen": "", "steps": _steps(e)}
        a["category"] = rules.categorise(a)
        desc = rules.fit_words(str(p.get("description") or ""), 5, 7, prefix="It will") or \
            rules.compact_description(e.get("qna_description") or e.get("description") or "", a["actionName"])
        actions.append({
            "actionName": a["actionName"], "description": desc.rstrip("."), "category": a["category"],
            "stepGroups": [{"steps": a["steps"], "actionableDeeplink": rules.deeplink_obj(e),
                            "validationDeeplink": rules.validation_obj(e)}],
            "_level": rules.disruption_level(a),
        })
    actions.sort(key=lambda x: (rules.CAT_RANK[x["category"]], x["_level"]))
    for x in actions:
        x.pop("_level")
    title = rules.fix_title(res.get("title") or res.get("topic") or "Settings check")
    if not 2 <= len(title.split()) <= 3:
        title = rules.fix_title(rules.force_words(title, 2, 3, pad="check"))
    score = round(min(MAX_SCORE, 0.35 + 0.35 * rel), 2)
    goal = {"goal": rules.goal_text(res.get("topic") or enrich.get("topic") or "Device", "Troubleshooting"),
            "title": title, "actions": actions, "score": score}
    return [goal], info
