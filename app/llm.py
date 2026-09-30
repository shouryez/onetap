"""Thin async client for any OpenAI-compatible chat endpoint (Gemini by default).

- JSON-mode responses, temperature 0 + seed for determinism
- token-based cost accounting per request (contextvar)
- disk memoisation of identical prompts (reproducible runs, $0 re-runs)
"""
import asyncio
import contextvars
import hashlib
import json
import re
import time
from dataclasses import dataclass, field

import httpx

from . import config

_cost: contextvars.ContextVar["Usage"] = contextvars.ContextVar("llm_usage")
BYPASS_DISK_CACHE: contextvars.ContextVar[bool] = contextvars.ContextVar("bypass_llm_disk_cache", default=False)


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    calls: int = 0
    cached_calls: int = 0
    models: set = field(default_factory=set)

    cost: float = 0.0

    @property
    def cost_usd(self) -> float:
        return round(self.cost, 6)

    def add(self, model: str, p: int, c: int) -> None:
        pin, pout = config.PRICES.get(model, (config.PRICE_IN_PER_M, config.PRICE_OUT_PER_M))
        self.prompt_tokens += p
        self.completion_tokens += c
        self.calls += 1
        self.models.add(model)
        self.cost += p / 1e6 * pin + c / 1e6 * pout


def start_usage() -> Usage:
    u = Usage()
    _cost.set(u)
    return u


def _usage() -> Usage:
    try:
        return _cost.get()
    except LookupError:
        return start_usage()


class LLMError(RuntimeError):
    pass


_client: httpx.AsyncClient | None = None
_calls: dict[str, list[float]] = {}
_tlock = asyncio.Lock()


async def _throttle(model: str) -> None:
    """Client-side requests-per-minute limiter (LLM_RPM=0 disables)."""
    if config.LLM_RPM <= 0:
        return
    async with _tlock:
        now = time.monotonic()
        win = [t for t in _calls.get(model, []) if now - t < 60]
        if len(win) >= config.LLM_RPM:
            await asyncio.sleep(60 - (now - win[0]) + 0.05)
            now = time.monotonic()
            win = [t for t in win if now - t < 60]
        win.append(now)
        _calls[model] = win


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=config.LLM_TIMEOUT_S)
    return _client


def _extract_json(text: str):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            return json.loads(m.group(0))
        raise


async def chat_json(system: str, user: str, *, model: str | None = None, temperature: float = 0.0,
                    max_tokens: int = 4096, retries: int = 2, base_url: str | None = None,
                    api_key: str | None = None, pool: list[str] | None = None) -> dict:
    model = model or config.LLM_MODEL
    key = hashlib.sha256(json.dumps([model, system, user, temperature]).encode()).hexdigest()[:32]
    cache_file = config.LLM_CACHE_DIR / f"{key}.json"
    u = _usage()
    if config.LLM_DISK_CACHE and not BYPASS_DISK_CACHE.get() and cache_file.exists():
        u.cached_calls += 1
        u.models.add(model)
        return json.loads(cache_file.read_text(encoding="utf-8"))["data"]
    api_key = api_key or config.LLM_API_KEY
    if not api_key:
        raise LLMError("LLM_API_KEY is not set (see .env.example)")

    base = base_url or config.LLM_BASE_URL
    url = base.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    # model pool: requested model first, then fallbacks; models out of daily quota are skipped
    pool = [model] + [m for m in (config.LLM_MODEL_POOL if pool is None else pool) if m != model]
    last = None
    for m in pool:
        if _exhausted(m):
            continue
        body = {
            "model": m,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "max_tokens": max_tokens,
        }
        eff = config.reasoning_effort(m)
        if eff:
            body["reasoning_effort"] = eff
        if "generativelanguage" not in base:
            body["seed"] = 7
        waited, attempt = 0.0, 0
        while attempt <= retries:
            try:
                await _throttle(m)
                r = await _get_client().post(url, json=body, headers=headers)
                if r.status_code == 429:
                    last = LLMError(f"HTTP 429 ({m}): {r.text[:200]}")
                    if "PerDay" in r.text or "per day" in r.text.lower():
                        _mark_exhausted(m)
                        break                                  # next model in pool
                    mm = re.search(r"(?:retry|try again) in (?:(\d+)m)?([\d.]+)s", r.text)
                    ra = r.headers.get("retry-after")
                    if mm:
                        delay = int(mm.group(1) or 0) * 60 + float(mm.group(2)) + 0.3
                    elif ra and ra.replace(".", "").isdigit():
                        delay = float(ra) + 0.3
                    else:
                        delay = 1.0 + attempt
                    delay = min(delay, 30.0)
                    if waited + delay > config.LLM_MAX_WAIT_S:
                        break
                    waited += delay
                    await asyncio.sleep(delay)
                    continue
                if r.status_code >= 500:
                    last = LLMError(f"HTTP {r.status_code} ({m}): {r.text[:200]}")
                    break                                      # overloaded: hedge to next model immediately
                if r.status_code != 200:
                    last = LLMError(f"HTTP {r.status_code} ({m}): {r.text[:300]}")
                    break
                j = r.json()
                usage = j.get("usage") or {}
                u.add(m, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))
                data = _extract_json(j["choices"][0]["message"].get("content") or "")
                if config.LLM_DISK_CACHE:
                    config.LLM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
                    cache_file.write_text(json.dumps({"data": data, "model": m}, ensure_ascii=False),
                                          encoding="utf-8")
                return data
            except (httpx.HTTPError, json.JSONDecodeError, KeyError, IndexError) as e:
                last = e
                attempt += 1
                await asyncio.sleep(0.5 * attempt)
    raise LLMError(f"LLM call failed on all models: {last}")


_EXHAUSTED_FILE = config.DATA_DIR / "llm_quota_state.json"
_COOLDOWN_S = 20 * 60   # provider daily caps are rolling windows: retry a capped model after a cooldown


def _load_exhausted() -> dict:
    try:
        d = json.loads(_EXHAUSTED_FILE.read_text(encoding="utf-8"))
        return d if isinstance(d.get("until"), dict) else {"until": {}}
    except Exception:
        return {"until": {}}


def _exhausted(m: str) -> bool:
    return _load_exhausted()["until"].get(m, 0) > time.time()


def _mark_exhausted(m: str) -> None:
    d = _load_exhausted()
    d["until"][m] = time.time() + _COOLDOWN_S
    _EXHAUSTED_FILE.write_text(json.dumps(d), encoding="utf-8")
