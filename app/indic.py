"""Indian-language input/output via Sarvam AI (Feature E).

- speech_to_text: a recorded complaint in any of 22 Indian languages -> native transcript + detected language
- to_english: complaint typed/spoken in an Indian language -> English for the engine (the API contract stays English)
- translate_plan: the finished plan's visible text -> the user's language, for display only
"""
import asyncio
import re

import httpx

from . import config

BASE = "https://api.sarvam.ai"
_INDIC = re.compile(r"[ऀ-෿]")          # Devanagari .. Sinhala blocks (all Indic scripts)
LANG_NAMES = {"hi-IN": "Hindi", "kn-IN": "Kannada", "ta-IN": "Tamil", "te-IN": "Telugu", "ml-IN": "Malayalam",
              "mr-IN": "Marathi", "bn-IN": "Bengali", "gu-IN": "Gujarati", "pa-IN": "Punjabi", "od-IN": "Odia",
              "en-IN": "English"}
_client: httpx.AsyncClient | None = None


class IndicError(RuntimeError):
    pass


def enabled() -> bool:
    return bool(config.SARVAM_API_KEY)


def has_indic(text: str) -> bool:
    return bool(_INDIC.search(text or ""))


def _http() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(base_url=BASE, timeout=30,
                                    headers={"api-subscription-key": config.SARVAM_API_KEY})
    return _client


async def _post(path: str, **kw) -> dict:
    if not enabled():
        raise IndicError("SARVAM_API_KEY is not set in .env")
    r = await _http().post(path, **kw)
    if r.status_code != 200:
        raise IndicError(f"Sarvam {path} HTTP {r.status_code}: {r.text[:200]}")
    return r.json()


async def speech_to_text(audio: bytes, filename: str = "speech.webm", content_type: str = "audio/webm") -> dict:
    """-> {"transcript": native text, "language_code": "hi-IN"|...}"""
    j = await _post("/speech-to-text", files={"file": (filename, audio, content_type)},
                    data={"model": "saaras:v3", "mode": "transcribe", "language_code": "unknown"})
    return {"transcript": (j.get("transcript") or "").strip(), "language_code": j.get("language_code") or "unknown"}


async def to_english(text: str, source: str = "auto") -> tuple[str, str]:
    """-> (english text, detected source language code)."""
    if source == "en-IN":
        return text, source
    j = await _post("/translate", json={"input": text[:1000], "source_language_code": source,
                                        "target_language_code": "en-IN", "model": "mayura:v1", "mode": "formal"})
    return (j.get("translated_text") or text).strip(), j.get("source_language_code") or source


async def _from_english(text: str, target: str) -> str:
    j = await _post("/translate", json={"input": text[:2000], "source_language_code": "en-IN",
                                        "target_language_code": target, "model": "sarvam-translate:v1",
                                        "mode": "formal"})
    return (j.get("translated_text") or text).strip()


async def translate_plan(response: dict, target: str) -> dict:
    """Translate goal titles, action names, descriptions and steps for display. One request per action keeps
    each input well under the API's character limit; requests run concurrently."""
    if target in ("en-IN", "unknown", "", None):
        return response
    out = {"contexts": []}
    jobs, slots = [], []
    for g in response.get("contexts", []):
        ng = {**g, "actions": []}
        out["contexts"].append(ng)
        jobs.append(_from_english(g["title"], target))
        slots.append(("title", ng, None))
        for a in g["actions"]:
            na = {**a, "stepGroups": [{**sg} for sg in a["stepGroups"]]}
            ng["actions"].append(na)
            sg = na["stepGroups"][0]
            block = "\n".join([a["actionName"], a["description"], *sg["steps"]])
            jobs.append(_from_english(block, target))
            slots.append(("action", na, len(sg["steps"])))
    sem = asyncio.Semaphore(6)

    async def run(j):
        async with sem:
            return await j

    results = await asyncio.gather(*(run(j) for j in jobs), return_exceptions=True)
    for (kind, obj, n), res in zip(slots, results):
        if isinstance(res, Exception):
            continue
        if kind == "title":
            obj["title"] = res
        else:
            lines = [l.strip() for l in res.split("\n") if l.strip()]
            if len(lines) == n + 2:      # translation kept the line structure -> safe to map back
                obj["actionName"], obj["description"] = lines[0], lines[1]
                obj["stepGroups"][0]["steps"] = lines[2:]
    return out
