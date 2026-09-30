"""The three LLM stages: [0] query enrichment, [1] structure extraction, [2] deeplink choice.
Prompts ask for JSON only; every constraint is re-checked in code (rules.py)."""
import json

from . import config
from . import config
from .llm import chat_json

# ============================================================================ [0] enrichment
ENRICH_SYS = """You normalise vague smartphone/tablet complaints into precise technical support queries.
Return ONLY a JSON object:
{
 "canonical_query": "<one precise technical sentence describing the problem(s), device-agnostic>",
 "topic": "<2-4 word Title Case topic, e.g. Screen Flicker, Black Screen, Swipe Navigation>",
 "query_variations": ["<10 distinct paraphrases of the ORIGINAL complaint>"]
}
Rules for query_variations (exactly 10):
- Same problem and same details as the original; never add new symptoms.
- Mix registers: 2 formal, 2 casual, 2 keyword-only (e.g. "screen flicker after update"), 2 frustrated/emotional,
  2 with realistic typos or missing punctuation.
- Each must be clearly different in wording from the others. No URLs, no numbering."""


async def enrich(query: str) -> dict:
    return await chat_json(ENRICH_SYS, f"Complaint: {query}", model=config.LLM_ENRICH_MODEL, max_tokens=1500)


# ============================================================================ [1] extraction
EXTRACT_SYS = """You convert a customer complaint plus a numbered reference article into a structured troubleshooting plan.
You are an EXTRACTOR, not an author: every step must come from an instruction that is present in the reference.

Return ONLY a JSON object:
{
 "issues": [
  {
   "issue": "<the user's distinct problem, one short sentence>",
   "topic": "<2-4 word Title Case topic for this issue, e.g. Screen Flicker, Black Screen, Touchscreen Lag>",
   "goal_type": "Troubleshooting" | "Configuration",
   "title": "<2-3 word sentence-case title naming the core issue, e.g. Screen flicker fix, Black screen, Touchscreen lag>",
   "relevance": <0.0-1.0: how directly the reference's instructions address THIS issue>,
   "actions": [
    {
     "actionName": "<Title Case name of the ONE screen/feature this action happens on, 2-5 words, e.g. Adjust Screen Brightness>",
     "description": "<exactly 5-7 words, must start with 'It will', plain-language benefit, e.g. It will reduce flicker at low brightness>",
     "screen": "<navigation path of the final screen, e.g. Settings > Display > Navigation bar; empty string if not a Settings screen>",
     "kind": "setting" | "app_setting" | "restart" | "safe_mode" | "reset" | "software_update" | "clear_data" | "physical" | "service" | "other",
     "toggle": "enable" | "disable" | "open" | "none",
     "steps": [ {"text": "<imperative step, one physical interaction>", "src": [<sentence numbers>]} ]
    }
   ]
  }
 ]
}

Rules:
1. Grounding: use ONLY instructions found in the numbered sentences. "src" lists the sentence number(s) that contain the instruction.
   Never add steps, settings paths, apps, websites or phone numbers that are not in the reference.
2. Relevance: include actions that plausibly help the user with this issue - direct fixes, diagnostics, workarounds
   (e.g. accessing data when the screen is dead), protective steps (backup) and service/repair escalation all count.
   Skip sections about unrelated features. Score relevance with this scale:
     0.85-1.0 the article directly fixes this exact symptom;
     0.6-0.84 same symptom area, partial fix, workaround or diagnostic path;
     0.4-0.59 same device area, only generic checks (restart, inspect, service) apply;
     0.0-0.39 the article is about a different feature/problem (e.g. email server settings for a display fault)
              -> return "actions": [] for that issue.
2b. Completeness: within the relevant sections, include EVERY troubleshooting instruction in reference order -
   physical/liquid-damage checks, charging, power-on attempts, restarts, safe mode, updates, backups and service
   escalation. Do not skip checks just because they seem basic. Keep each instruction's specific details.
2c. Conditional instructions: when the reference says "if <condition>, do X", include X only if the condition is
   compatible with the complaint. Never include two actions that contradict each other (e.g. a user who fitted a
   screen protector gets "enable Touch sensitivity", not the "disable it when NOT using a protector" advice).
3. Multi-intent: create one issue per DISTINCT problem in the complaint (max 3). One problem = one issue.
4. One action = one screen: group the navigation taps leading to a screen with the steps done on that screen.
   A new destination screen or a different feature = a new action. Do not split one screen across actions.
5. Step style (follow exactly): when the reference navigates through Settings, start with
   "Navigate to and open Settings." (cite the sentence that mentions Settings), then "Tap on <item>.",
   "Select <option>.", "Toggle on <switch>." etc. One tap/interaction per step, each step ends with a period,
   max ~18 words, no URLs, no markdown, no numbering. Physical/service actions use plain imperatives
   (e.g. "Contact Customer Support or visit an authorized TechCorp Service Center.").
6. kind: "restart" for restart/reboot/force restart, "safe_mode" for safe mode, "reset" for factory/settings reset,
   "software_update" for software/firmware updates, "clear_data" for clearing app data/storage,
   "physical" for hands-on hardware actions (clean, remove case, charge, press buttons), "service" for contacting support/repair.
7. description: EXACTLY 5, 6 or 7 words, starting with "It will". Count the words.
8. Never write a step that taps the action's own name (e.g. "Tap on Force Restart Device.") - only real UI elements
   or buttons named in the reference.
9. title: 2 or 3 words only. goal_type "Configuration" only if the user wants to change/remove a feature rather than fix a fault."""


def number_sentences(sentences: list[str]) -> str:
    return "\n".join(f"[{i}] {s}" for i, s in enumerate(sentences, 1))


async def extract(query: str, sentences: list[str]) -> dict:
    user = f"Complaint: {query}\n\nReference article (numbered sentences):\n{number_sentences(sentences)}"
    return await chat_json(EXTRACT_SYS, user, max_tokens=6000)


REPAIR_SYS = """You fix fields of a troubleshooting plan so they satisfy strict format rules. Keep the meaning.
Return ONLY JSON: {"fixes": [{"i": <index>, "value": "<fixed text>"}]}"""


async def repair(kind: str, items: list[tuple[int, str, str]]) -> dict:
    rule = {
        "description": "Rewrite each text to EXACTLY 5, 6 or 7 words, starting with 'It will'. Count words carefully.",
        "title": "Rewrite each text as a 2 or 3 word sentence-case title naming the core issue.",
    }[kind]
    lines = "\n".join(f'{i}. "{text}" (context: {ctx})' for i, text, ctx in items)
    return await chat_json(REPAIR_SYS, f"Rule: {rule}\n\n{lines}", model=config.LLM_REPAIR_MODEL, max_tokens=800)


# ============================================================================ [2] deeplink selection
MAP_SYS = """You map troubleshooting actions to entries of a device Settings deeplink catalog.
For each action choose the ONE candidate whose target screen/function is exactly the screen where the action's steps happen.

Candidate types: onURL = turns a toggle ON, offURL = turns a toggle OFF, onClickURL = opens a settings page,
updateURL = changes a value (e.g. brightness level), other/null = diagnostic or status page.

Rules:
- Match the DEEPEST screen named in the steps, never a parent menu (e.g. "Navigation bar" beats "Display").
- Respect direction: an action that enables something needs onURL/onClickURL; one that disables needs offURL/onClickURL.
- If no candidate matches that specific screen/function, answer "NONE". Never guess loosely.
- If NONE but the steps clearly take place on a device Settings screen, also give "dummy_description" and
  "dummy_message": each 5-7 words naming that concrete screen (e.g. "Open navigation bar settings under Display").

Return ONLY JSON: {"choices": [{"action": <index>, "id": "<candidate id or NONE>", "dummy_description": "...", "dummy_message": "..."}]}"""


async def choose_deeplinks(blocks: list[dict]) -> dict:
    parts = []
    for b in blocks:
        cands = "\n".join(
            f'   - {c["id"]} | type={c.get("originalType")} | {c.get("message")} | {c.get("description")}'
            for c in b["candidates"]
        )
        parts.append(
            f'Action {b["index"]}: {b["actionName"]}\n   screen: {b["screen"] or "?"} | toggle: {b["toggle"]}\n'
            f'   steps: {" ".join(b["steps"])}\n   candidates:\n{cands}'
        )
    return await chat_json(MAP_SYS, "\n\n".join(parts), model=config.LLM_FAST_MODEL, max_tokens=1500)


# ============================================================================ baseline for ablation
FULL_LLM_MAP_SYS = """You map a troubleshooting action to a deeplink from the full catalog below.
Return ONLY JSON: {"id": "<catalog id or NONE>"}"""


async def full_llm_choose(action: dict, catalog_lines: str) -> dict:
    user = (f"Catalog:\n{catalog_lines}\n\nAction: {action['actionName']}\nscreen: {action.get('screen')}\n"
            f"steps: {' '.join(action['steps'])}")
    if config.BASELINE_API_KEY:
        return await chat_json(FULL_LLM_MAP_SYS, user, model=config.BASELINE_MODELS[0], max_tokens=300,
                               base_url=config.BASELINE_BASE_URL, api_key=config.BASELINE_API_KEY,
                               pool=config.BASELINE_MODELS)
    return await chat_json(FULL_LLM_MAP_SYS, user, model=config.LLM_ENRICH_MODEL, max_tokens=100)


def dumps(o) -> str:
    return json.dumps(o, ensure_ascii=False)
