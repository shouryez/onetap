"""Central configuration, read from environment / .env."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


def _load_dotenv() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()


def _f(name: str, default: float) -> float:
    return float(os.getenv(name, default))


# ---- LLM (any OpenAI-compatible endpoint; default = Gemini) ----
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("GROQ_API_KEY") or os.getenv("GEMINI_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")            # Phase 1 extraction (quality-critical)
LLM_ENRICH_MODEL = os.getenv("LLM_ENRICH_MODEL", "qwen/qwen3.8-27b")  # query enrichment + paraphrases
# Fast model for the simple closed-set stages (deeplink choice, format repair)
LLM_FAST_MODEL = os.getenv("LLM_FAST_MODEL", "openai/gpt-oss-20b")        # closed-set deeplink choice
LLM_REPAIR_MODEL = os.getenv("LLM_REPAIR_MODEL", "qwen/qwen3.8-27b")
# Hedging pool: tried in order when a model is overloaded (5xx) or out of quota (429)
LLM_MODEL_POOL = [m.strip() for m in os.getenv("LLM_MODEL_POOL", "openai/gpt-oss-120b,qwen/qwen3.8-27b,openai/gpt-oss-20b").split(",") if m.strip()]
# Secondary model used only offline for held-out paraphrases / judging (different prompt+temp; ideally other family)
LLM_EVAL_MODEL = os.getenv("LLM_EVAL_MODEL", LLM_MODEL)
LLM_TIMEOUT_S = _f("LLM_TIMEOUT_S", 25)
LLM_RPM = int(os.getenv("LLM_RPM", 0))            # client-side limiter; set 5 for Gemini free tier
LLM_MAX_WAIT_S = _f("LLM_MAX_WAIT_S", 3)          # serving: hedge to the next model fast; batch scripts raise this
# USD per 1M tokens (input, output) - Groq on-demand list prices; unknown models use PRICE_*_PER_M
PRICES = {
    "openai/gpt-oss-120b": (0.15, 0.60), "openai/gpt-oss-20b": (0.075, 0.30), "qwen/qwen3.8-27b": (0.29, 0.59),
    "gemini-2.5-flash": (0.30, 2.50), "gemini-2.5-flash-lite": (0.10, 0.40),
}
PRICE_IN_PER_M = _f("PRICE_IN_PER_M", 0.30)
PRICE_OUT_PER_M = _f("PRICE_OUT_PER_M", 1.00)


def reasoning_effort(model: str) -> str | None:
    if "gpt-oss" in model:
        return "low"
    if "qwen3" in model or "gemini-2.5" in model:
        return "none"
    return None
LLM_DISK_CACHE = os.getenv("LLM_DISK_CACHE", "1") == "1"  # memoise identical prompts -> determinism

# Ablation baseline "full catalog in the prompt" needs a long-context model (Groq free tier caps request size)
BASELINE_BASE_URL = os.getenv("BASELINE_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
BASELINE_API_KEY = os.getenv("BASELINE_API_KEY") or os.getenv("GEMINI_API_KEY", "")
BASELINE_MODELS = [m.strip() for m in os.getenv("BASELINE_MODELS", "gemini-3.5-flash,gemini-3.6-flash,gemini-flash-lite-latest,gemini-3.5-flash-lite").split(",") if m.strip()]

# ---- Embeddings ----
EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5")

# ---- Semantic cache ----
CACHE_PATH = Path(os.getenv("CACHE_PATH", DATA_DIR / "cache_store.json"))
CACHE_TAU = _f("CACHE_TAU", 0.87)        # accept at/above this cosine (if guard passes)
CACHE_TAU_LOW = _f("CACHE_TAU_LOW", 0.87)  # < CACHE_TAU enables a borderline band (needs exact symptom match); off by default

# ---- Retrieval ----
KB_MIN_SIM = _f("KB_MIN_SIM", 0.62)  # min similarity to use a KB article when siis_response omitted
MIN_RELEVANCE = _f("MIN_RELEVANCE", 0.4)  # issues the article barely addresses -> no_match
DEEPLINK_TOPK = int(os.getenv("DEEPLINK_TOPK", 8))

DEEPLINKS_PATH = DATA_DIR / "deeplinks.json"
SIIS_PATH = DATA_DIR / "siis_responses.json"
INPUT_PATH = DATA_DIR / "input.txt"
LLM_CACHE_DIR = DATA_DIR / "llm_cache"
