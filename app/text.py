"""Deterministic text utilities: normalisation, Hinglish/typo lexicon, symptom signatures,
casing / word-count helpers and URL scrubbing. No ML here: everything is fast and predictable."""
import re
import unicodedata

# ----------------------------------------------------------------------------- normalisation
_HINGLISH = {
    "garam": "hot", "garm": "hot", "kaala": "black", "kaali": "black", "kala": "black", "kali": "black",
    "toota": "cracked", "tuta": "cracked", "tooti": "cracked", "tuti": "cracked", "tut": "cracked",
    "nahi": "not", "nahin": "not", "nhi": "not", "chal": "working", "chalta": "working", "raha": "",
    "rahi": "", "hai": "", "ho": "", "gaya": "", "gayi": "", "gya": "", "bahut": "very", "bohot": "very",
    "jaldi": "fast", "khatam": "drains", "band": "off", "dikh": "visible", "dikhta": "visible",
    "dikhai": "visible", "de": "", "raha,": "", "phir": "again", "baar": "repeatedly", "mera": "my",
    "meri": "my", "mere": "my", "ka": "", "ki": "", "ke": "", "pe": "while", "par": "while",
    "screen": "screen", "atak": "freeze", "atakta": "freezes", "hang": "freezes", "kaam": "work",
    "karta": "", "karti": "", "kar": "", "jaata": "", "jaati": "", "jata": "", "jati": "",
}
_TYPOS = {
    "scren": "screen", "screan": "screen", "sreen": "screen", "dispaly": "display", "diplay": "display",
    "batery": "battery", "battry": "battery", "baterry": "battery", "flikering": "flickering",
    "flickring": "flickering", "flicering": "flickering", "flikers": "flickers", "blnk": "blank",
    "balck": "black", "blak": "black", "chargin": "charging", "charing": "charging", "phn": "phone",
    "fone": "phone", "wont": "won't", "doesnt": "doesn't", "dosent": "doesn't", "cant": "can't",
    "isnt": "isn't", "didnt": "didn't", "rotaion": "rotation", "roate": "rotate", "tuch": "touch",
    "tauch": "touch", "crakced": "cracked", "craked": "cracked", "wifi": "wi-fi", "w-fi": "wi-fi",
    "blutooth": "bluetooth", "bluetoth": "bluetooth", "setings": "settings", "settngs": "settings",
    "u": "you", "ur": "your", "pls": "please", "plz": "please", "r": "are",
}
_TOKEN = re.compile(r"[a-z0-9\-']+")


def normalise(q: str) -> str:
    """Lower-case, strip enumerations/quotes, fix common typos and map Hinglish tokens."""
    q = unicodedata.normalize("NFKC", q).replace("—", " ").replace("–", " ")
    q = q.lower().strip()
    q = re.sub(r"(^|\s)\d+\.\s*", " ", q)            # "1. ..." enumerations
    q = re.sub(r"[\"“”‘’`]", "", q)
    out = []
    for t in _TOKEN.findall(q):
        t = _TYPOS.get(t, t)
        t = _HINGLISH.get(t, t)
        if t:
            out.append(t)
    return " ".join(out)


# ----------------------------------------------------------------------------- signatures
_COMPONENTS = {
    "display": r"screen|display|monitor|lcd|amoled|panel|brightness",
    "touch": r"touch|touchscreen|tap|taps|swipe|swip",
    "battery": r"battery|batt",
    "charging": r"charg\w*|plug\w*|cable|adapter|port",
    "wifi": r"wi-fi|wlan|hotspot",
    "bluetooth": r"bluetooth|earbuds|headphones",
    "camera": r"camera|photo|video|lens",
    "audio": r"sound|audio|speaker|volume|mic|microphone",
    "network": r"network|signal|mobile data|sim|carrier|calls?",
    "storage": r"storage|memory",
    "email": r"e-?mail|gmail|mail",
    "transfer": r"data transfer|smart switch|transfer",
    "fold": r"fold|foldable|inner screen|cover screen|hinge",
    "navigation": r"navigation|gesture|nav bar|navigation bar",
    "browse": r"web ?page|browser|browsing|scroll\w*|website|internet",
    "video": r"video|youtube|movie|streaming|watch\w*",
    "game": r"gam(?:e|es|ing)",
    "boot": r"boot\w*|start ?up|power(?:ing)? on|turn(?:ing)? it on|logo",
}
# Context tags: WHEN/WHERE the fault happens. Two complaints in different contexts need different fixes.
_CONTEXT_KEYS = {"charging", "wifi", "bluetooth", "camera", "audio", "network", "email", "transfer", "browse",
                 "video", "game", "navigation", "boot"}
_SYMPTOMS = {
    "flicker": r"flicker\w*|flash\w*|blink\w*|strob\w*|flutter\w*",
    "dim": r"dim\w*|low[- ]?contrast|hard to read|faded|washed[- ]out|too dark to read",
    "blank": r"blank|black|dark|white screen|no image|nothing (?:shows|appears|displays)|no display|not visible|can't see",
    "crack": r"crack\w*|shatter\w*|broken glass|bleed\w*",
    "lag": r"lag\w*|delay\w*|slow\w*|sluggish",
    "unresponsive": r"unresponsive|not respond\w*|doesn't respond|don't respond|won't respond|not working|stopped working|freez\w*",
    "drain": r"drain\w*|dies fast|dying fast|runs out",
    "overheat": r"hot|heat\w*|overheat\w*|warm",
    "rotate": r"rotat\w*",
    "distort": r"distort\w*|lines|pixel\w*|glitch\w*",
    "size": r"small|doesn't fill|not full|shrunk|zoom\w*",
    "floating": r"floating|bubble|circle|assistant menu",
    "noboot": r"won't (?:start|boot|turn on)|not (?:booting|turning on)|boot ?loop|stuck on logo|won't power",
    "noconnect": r"(?:won't|can't|not|doesn't) connect\w*|disconnect\w*|drops?",
}
_POLARITY_ON = r"(?:keeps?|kept|always|automatically|itself|randomly)\s+(?:turn|switch)\w*\s+on|(?:turn|switch)\w*\s+on\s+(?:by itself|automatically|randomly|on its own)"
_POLARITY_OFF = r"(?:keeps?|kept|always|automatically|itself|randomly)\s+(?:turn|switch)\w*\s+off|(?:turn|switch)\w*\s+off\s+(?:by itself|automatically|randomly|on its own)"

_COMP_RX = {k: re.compile(rf"\b(?:{v})\b") for k, v in _COMPONENTS.items()}
_SYM_RX = {k: re.compile(rf"\b(?:{v})\b") for k, v in _SYMPTOMS.items()}
_ON_RX, _OFF_RX = re.compile(_POLARITY_ON), re.compile(_POLARITY_OFF)


# "no cracks or drops", "without any damage" -> negated mentions are not symptoms
_NEGATED = re.compile(r"\b(?:no|without|never|not)\s+(?:any\s+|visible\s+|physical\s+|signs? of\s+)?"
                      r"(?:cracks?|cracked|damage|drops?|dropped|liquid|water|scratches?)"
                      r"(?:\s+(?:or|and|nor)\s+(?:cracks?|damage|drops?|liquid|water|scratches?))*\b")
# contexts that change the fix (a flicker WHILE CHARGING is a different case than a flicker in general)
TRIGGER_CONTEXTS = {"charging", "email", "transfer", "camera", "browse", "video", "game", "wifi", "bluetooth"}


def signature(q_norm: str) -> dict:
    q_sym = _NEGATED.sub(" ", q_norm)
    comps = sorted(k for k, rx in _COMP_RX.items() if rx.search(q_norm))
    syms = sorted(k for k, rx in _SYM_RX.items() if rx.search(q_sym))
    pol = "on" if _ON_RX.search(q_norm) else "off" if _OFF_RX.search(q_norm) else None
    return {"components": comps, "symptoms": syms, "polarity": pol}


def signature_compatible(a: dict, b: dict, check_symptoms: bool = True) -> tuple[bool, str]:
    """Guard against high-cosine-but-different-problem cache hits (a = query, b = cached).
    - opposite polarity ("keeps turning ON" vs "OFF")               -> reject
    - different symptom sets (flicker+blank vs dim)                  -> reject (no symptoms detected = no evidence)
    - cached plan is tied to a trigger context the query lacks,
      or both name different trigger contexts                        -> reject"""
    if a.get("polarity") and b.get("polarity") and a["polarity"] != b["polarity"]:
        return False, "polarity_mismatch"
    sa, sb = set(a.get("symptoms", [])), set(b.get("symptoms", []))
    if check_symptoms and sa and sb and sa != sb:
        return False, "symptom_mismatch"
    ca = set(a.get("components", [])) & TRIGGER_CONTEXTS
    cb = set(b.get("components", [])) & TRIGGER_CONTEXTS
    if cb and not (ca & cb):
        return False, "context_mismatch"
    return True, "ok"


# ----------------------------------------------------------------------------- output hygiene
URL_RX = re.compile(
    r"\[([^\]]+)\]\([^)]*\)"                       # markdown link -> keep text (group 1)
    r"|https?://\S+|www\.\S+"
    r"|\b[\w-]+\.(?:com|org|net|io|in|co|gov)(?:/\S*)?\b",
    re.I,
)


_ASCII = str.maketrans({"‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-",
                        "‘": "'", "’": "'", "“": '"', "”": '"', " ": " ",
                        "…": "...", " ": " "})


def ascii_punct(s: str) -> str:
    return s.translate(_ASCII)


def scrub_urls(s: str) -> str:
    s = ascii_punct(s)
    s = URL_RX.sub(lambda m: m.group(1) or "", s)
    s = re.sub(r"\(\s*\)", "", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    s = re.sub(r"\s+([.,;:])", r"\1", s)
    return s


def has_url(s: str) -> bool:
    return bool(re.search(r"https?://|www\.|\]\(|\b[\w-]+\.(?:com|org|net|io|gov)\b", s, re.I))


SMALL = {"a", "an", "the", "and", "or", "for", "to", "of", "on", "in", "with", "at", "by", "via", "from", "nor", "as"}


def _keep_case(w: str) -> bool:
    core = w.strip(".,:;()")
    return (any(c.isupper() for c in core[1:]) or core.isupper() and len(core) > 1
            or bool(re.search(r"\d", core)))


def title_case(s: str) -> str:
    words = s.strip().rstrip(".").split()
    out = []
    for i, w in enumerate(words):
        if _keep_case(w):
            out.append(w)
        elif i and i < len(words) - 1 and w.lower() in SMALL:
            out.append(w.lower())
        else:
            out.append("-".join(p[:1].upper() + p[1:].lower() for p in w.split("-")))
    return " ".join(out)


PROPER = {"techcorp": "TechCorp", "wi-fi": "Wi-Fi", "bluetooth": "Bluetooth", "nexa": "Nexa",
          "android": "Android", "google": "Google", "gmail": "Gmail", "tv": "TV", "usb": "USB",
          "sim": "SIM", "qr": "QR", "gps": "GPS", "nfc": "NFC", "ui": "UI", "5g": "5G", "4g": "4G"}


def sentence_case(s: str) -> str:
    words = s.strip().rstrip(".").split()
    out = []
    for i, w in enumerate(words):
        lw = w.lower()
        if lw in PROPER:
            out.append(PROPER[lw])
        elif _keep_case(w) and not w.isupper():
            out.append(w)
        elif i == 0:
            out.append(w[:1].upper() + w[1:].lower())
        else:
            out.append(lw)
    return " ".join(out)


def words(s: str) -> list[str]:
    return [w for w in re.split(r"\s+", s.strip()) if w]


def clean_step(s: str) -> str:
    s = scrub_urls(s)
    s = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", s).strip()
    s = s.replace("**", "").replace("`", "")
    if not s:
        return s
    s = s[0].upper() + s[1:]
    if s[-1] not in ".!?":
        s += "."
    return s


# ----------------------------------------------------------------------------- SIIS sentence numbering
def split_sentences(content: str) -> list[str]:
    out: list[str] = []
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            out.append(line.lstrip("# ").strip() + ":")
            continue
        parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\"(])|(?<=[a-z])\.(?=[A-Z])", line)
        out.extend(p.strip() for p in parts if p.strip())
    return out


STOP = set("""a an the and or to of on in with at by for from is are be your you it this that then
if as can will may tap select open go navigate settings setting screen step steps into onto up down
please make sure also just""".split())


def content_tokens(s: str) -> set[str]:
    toks = re.findall(r"[a-z0-9]+", s.lower())
    return {t[:-1] if t.endswith("s") and len(t) > 3 else t for t in toks if t not in STOP and len(t) > 1}
