"""Deterministic post-processing: grounding check, categorisation, disruption ordering,
deeplink candidate reranking/assembly, format fixes, calibrated score and compliance checks."""
import re

from .text import (clean_step, content_tokens, has_url, scrub_urls, sentence_case, title_case, words)

# ============================================================================ grounding
GENERIC_STEPS = re.compile(r"^(navigate to and open settings|open settings|go to settings|navigate to settings)\.?$", re.I)


def is_self_referential(step: str, action_name: str) -> bool:
    """LLMs sometimes invent 'Tap on <Action Name>.' - a UI element that does not exist."""
    m = re.match(r"^(?:tap on|tap|select|open)\s+(.+?)\.?$", step.strip(), re.I)
    return bool(m and action_name and m.group(1).strip().lower() == action_name.strip().lower())


def ground_step(step: str, src: list, sentences: list[str], article_lower: str) -> tuple[bool, float]:
    """A step is kept only if its content words are supported by its cited sentence(s) (or close neighbours)."""
    if GENERIC_STEPS.match(step.strip()):
        # "Open Settings" is only grounded if a cited (or neighbouring) sentence actually goes through Settings
        ids = [int(i) for i in (src or []) if str(i).isdigit() and 1 <= int(i) <= len(sentences)]
        near = {j for i in ids for j in range(max(1, i - 1), min(len(sentences), i + 1) + 1)}
        return any("settings" in sentences[j - 1].lower() for j in near), 1.0
    st = content_tokens(step)
    if not st:
        return True, 1.0
    ids = [int(i) for i in (src or []) if str(i).isdigit() and 1 <= int(i) <= len(sentences)]
    cited = set()
    for i in ids:
        cited |= content_tokens(sentences[i - 1])
    cov = len(st & cited) / len(st)
    if cov >= 0.5:
        return True, cov
    # tolerate slightly-off citations: look at a window around cited ids (or whole article if none)
    window = range(len(sentences)) if not ids else range(max(0, min(ids) - 4), min(len(sentences), max(ids) + 3))
    best = max((len(st & content_tokens(sentences[j])) / len(st) for j in window), default=0.0)
    return best >= 0.6, best


# ============================================================================ categorisation & ordering
CRITICAL_RX = re.compile(r"\b(?:factory (?:data )?reset|reset all settings|reset settings|erase|wipe|safe mode|"
                         r"restart|reboot|force restart|software update|firmware|clear data|clear storage|power off)\b", re.I)
PHYSICAL_RX = re.compile(r"clean|remove the case|screen protector|charger|cable|press and hold|service cent|"
                         r"customer support|contact|repair|replace|technician|visit", re.I)

KIND_CAT = {"restart": "critical", "safe_mode": "critical", "reset": "critical", "software_update": "critical",
            "clear_data": "critical", "physical": "manual", "service": "manual",
            "setting": "auto", "app_setting": "auto"}
LEVEL = {"setting": 0, "app_setting": 1, "other": 2, "physical": 3, "service": 4,
         "restart": 5, "safe_mode": 6, "clear_data": 7, "software_update": 8, "reset": 9}


def categorise(action: dict) -> str:
    kind = action.get("kind") or "other"
    text = " ".join(action["steps"]) + " " + action.get("actionName", "")
    if kind in KIND_CAT:
        cat = KIND_CAT[kind]
    elif CRITICAL_RX.search(text):
        cat = "critical"
    elif re.search(r"settings", text, re.I):
        cat = "auto"
    else:
        cat = "manual"
    if kind == "clear_data" and not re.search(r"clear (?:data|storage)|delete|erase", text, re.I):
        cat = "auto"                                   # clearing cache is non-destructive
    if cat == "auto" and re.search(r"\b(?:factory (?:data )?reset|reset all settings|erase|wipe)\b", text, re.I):
        cat = "critical"
    return cat


def disruption_level(action: dict) -> float:
    lvl = LEVEL.get(action.get("kind") or "other", 2)
    t = " ".join(action["steps"]).lower()
    if "factory" in t:
        lvl = max(lvl, 9.5)
    if "clear cache" in t:
        lvl = max(lvl, 1.5)
    return lvl


CAT_RANK = {"auto": 0, "manual": 1, "critical": 2}


def order_actions(actions: list[dict]) -> list[dict]:
    """Non-invasive first, critical/destructive last; stable within ties (deterministic)."""
    return [a for _, a in sorted(enumerate(actions), key=lambda p: (CAT_RANK[p[1]["category"]],
                                                                        disruption_level(p[1]), p[0]))]


# ============================================================================ deeplink candidates
def leaf_of(action: dict) -> str:
    screen = (action.get("screen") or "").strip()
    if ">" in screen:
        return screen.split(">")[-1].strip()
    for s in reversed(action["steps"]):
        m = re.match(r"(?:tap on|tap|select|open|toggle (?:on|off)|turn (?:on|off))\s+(.+?)\.?$", s, re.I)
        if m:
            return m.group(1)
    return screen


def rerank(action: dict, cands: list[tuple[dict, float]]) -> list[tuple[dict, float]]:
    leaf = content_tokens(leaf_of(action))
    toggle = action.get("toggle", "none")
    out = []
    for e, sim in cands:
        txt = content_tokens(f"{e.get('message', '')} {e.get('description', '')}")
        s = sim
        if leaf:
            s += 0.25 * len(leaf & txt) / len(leaf)          # depth-aware: exact leaf screen wins over parent
        t = e.get("originalType")
        if toggle == "enable" and t == "offURL" or toggle == "disable" and t == "onURL":
            s -= 0.3
        if t is None and not e.get("qna_description"):           # status/diagnostic/appliance rows
            s -= 0.05
        out.append((e, s))
    return sorted(out, key=lambda x: -x[1])


def deeplink_obj(e: dict) -> dict:
    return {"deeplink": e["deeplink"], "description": e["description"], "message": e.get("message") or "",
            "originalType": e.get("originalType")}


def validation_obj(e: dict) -> dict | None:
    v = e.get("validation")
    if not v or not v.get("deeplink") or not v.get("key"):
        return None
    out = {"deeplink": v["deeplink"], "key": v["key"]}
    for k in ("resultType", "condition", "value"):
        if v.get(k) is not None:
            out[k] = v[k]
    return out


def fit_words(s: str, lo: int, hi: int, prefix: str | None = None) -> str | None:
    """Return s if it already satisfies the word window, else None (caller repairs)."""
    s = scrub_urls(s).strip().rstrip(".")
    if prefix and not s.lower().startswith(prefix.lower()):
        return None
    return s if lo <= len(words(s)) <= hi else None


TRAIL = {"and", "or", "to", "the", "a", "an", "of", "for", "with", "your", "on", "in", "by", "that"}


def compact_description(desc: str, action_name: str) -> str:
    """Deterministic 5-7 word 'It will ...' when LLM repair is unavailable."""
    body = re.sub(r"^it will\s+", "", scrub_urls(desc).strip().rstrip("."), flags=re.I)
    w = words(body)
    if w:
        v = w[0].lower()
        if v.endswith("es") and v[:-2].endswith(("ch", "sh", "ss", "x")):
            v = v[:-2]                                    # "reaches" -> "reach"
        elif v.endswith("s") and not v.endswith("ss"):
            v = v[:-1]                                    # "protects" -> "protect"
        w[0] = v
    for cut in (5, 4, 3):                                 # prefer ending before a preposition / conjunction
        if len(w) > cut and w[cut].lower() in TRAIL | {"when", "if", "so", "into", "under", "from"}:
            w = w[:cut]
            break
    w = w[:5]
    while len(w) > 3 and w[-1].lower() in TRAIL:
        w.pop()
    if 3 <= len(w) <= 5:
        return "It will " + " ".join(w)
    return force_words(f"It will help you {action_name.lower()}", 5, 7, prefix="It will", pad="easily")


def force_words(s: str, lo: int, hi: int, prefix: str | None = None, pad: str = "") -> str:
    """Last-resort deterministic fix when the LLM repair also fails."""
    s = scrub_urls(s).strip().rstrip(".")
    if prefix and not s.lower().startswith(prefix.lower()):
        s = f"{prefix} {s[0].lower() + s[1:] if s else ''}".strip()
    w = words(s)[:hi]
    while len(w) > lo and w[-1].lower() in TRAIL:
        w.pop()
    while len(w) < lo:
        w += pad.split()[: lo - len(w)] or ["issue"]
    return " ".join(w)


def fix_title(t: str) -> str:
    return sentence_case(scrub_urls(t))


def fix_action_name(n: str) -> str:
    return title_case(scrub_urls(n))


OUTCOME_RX = re.compile(r"^(?:your|the|this|it|that)\b.*\b(?:will|should|is|are)\b", re.I)


def clean_steps(steps: list[str]) -> list[str]:
    out = []
    for s in steps:
        s = clean_step(s)
        if OUTCOME_RX.match(s):
            continue                                   # an outcome ("Your phone will restart"), not an action
        if s and (not out or out[-1].lower() != s.lower()):
            out.append(s)
    return out


def goal_text(topic: str, goal_type: str) -> str:
    gt = "Configuration" if str(goal_type).lower().startswith("config") else "Troubleshooting"
    topic = title_case(re.sub(r"\b(troubleshooting|configuration)\b", "", topic, flags=re.I).strip() or "Device")
    return f"Follow these steps to perform this {topic} {gt}"


def calibrated_score(relevance: float, grounded_ratio: float, mapped_ratio: float, source_sim: float) -> float:
    ss = min(1.0, max(0.0, (source_sim - 0.5) / 0.35))
    s = 0.45 * relevance + 0.25 * grounded_ratio + 0.15 * mapped_ratio + 0.15 * ss
    return round(min(0.99, max(0.05, s)), 2)


# ============================================================================ compliance checks (used by tests + eval)
def check_goal(g: dict, catalog_uris: set) -> list[str]:
    errs = []
    if not re.fullmatch(r"Follow these steps to perform this .+ (Troubleshooting|Configuration)", g["goal"]):
        errs.append("goal_syntax")
    tw = words(g["title"])
    if not (2 <= len(tw) <= 3):
        errs.append("title_words")
    if g["title"] != sentence_case(g["title"]):
        errs.append("title_case")
    if not (0.0 <= g["score"] <= 1.0):
        errs.append("score_range")
    seen_critical = False
    for a in g["actions"]:
        if a["actionName"] != title_case(a["actionName"]):
            errs.append("action_title_case")
        dw = words(a["description"])
        if not (5 <= len(dw) <= 7) or not a["description"].startswith("It will"):
            errs.append("description_rule")
        if a["category"] == "critical":
            seen_critical = True
        elif seen_critical:
            errs.append("critical_not_last")
        for sg in a["stepGroups"]:
            if not sg["steps"]:
                errs.append("empty_steps")
            for s in sg["steps"]:
                if has_url(s):
                    errs.append("url_leak")
            dl = sg.get("actionableDeeplink")
            if a["category"] == "manual" and dl:
                errs.append("manual_has_deeplink")
            if dl and dl["deeplink"] not in catalog_uris:
                errs.append("deeplink_not_in_catalog")
    return errs


# ============================================================================ exact screen match (deterministic)
def _norm_leaf(x: str) -> str:
    x = re.sub(r"\(.*?\)", "", x.lower())
    x = re.sub(r"^(?:the|your)\s+", "", x.strip().rstrip("."))
    return x.replace("wifi", "wi-fi").strip()


def leaf_candidates(action: dict) -> list[tuple[str, str]]:
    """(phrase, direction) pairs describing the exact target of an action."""
    out = []
    for st in action["steps"]:
        m = re.match(r"(?:toggle|turn|switch)\s+(on|off)\s+(?:the\s+)?(.+?)(?:\s+switch|\s+option)?\.?$", st, re.I)
        if m:
            out.append((_norm_leaf(m.group(2)), "enable" if m.group(1).lower() == "on" else "disable"))
            continue
        m = re.match(r"(?:tap|toggle|flip|use)\s+(?:the\s+)?(?:switch|toggle)\s+(?:next to|for|beside)\s+(.+?)\.?$", st, re.I)
        if m:
            d = "disable" if re.search(r"\b(?:disable|turn off|off)\b", action.get("actionName", "") + " " +
                                       action.get("toggle", ""), re.I) else "enable"
            out.append((_norm_leaf(m.group(1)), d))
            continue
        m = re.match(r"(?:tap|toggle|flip)\s+(?:on\s+)?(?:the\s+)?(.+?)\s+(?:switch|toggle)\.?$", st, re.I)
        if m:
            d = "disable" if re.search(r"\b(?:disable|turn off|off)\b", action.get("actionName", "") + " " +
                                       action.get("toggle", ""), re.I) else "enable"
            out.append((_norm_leaf(m.group(1)), d))
    screen = action.get("screen") or ""
    if ">" in screen:
        out.append((_norm_leaf(screen.split(">")[-1]), "open"))
    elif screen:
        out.append((_norm_leaf(screen), "open"))
    return [(p, d) for p, d in out if 2 < len(p) < 40]


def exact_screen_match(action: dict, entries: list[dict]) -> dict | None:
    for phrase, direction in leaf_candidates(action):
        p = re.escape(phrase)
        rx_open = re.compile(rf"^opens the {p}(?: mode)? settings page\b")
        rx_on = re.compile(rf"^enables {p}(?: mode)? (?:via|in|on)\b")
        rx_off = re.compile(rf"^disables {p}(?: mode)? (?:via|in|on)\b")
        hits = []
        for e in entries:
            d = (e.get("description") or "").lower()
            if direction == "enable" and rx_on.search(d) or direction == "disable" and rx_off.search(d)                     or direction == "open" and rx_open.search(d):
                hits.append(e)
        if len(hits) == 1:
            return hits[0]
    return None
