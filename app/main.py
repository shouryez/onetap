"""REST API: POST /v1/troubleshoot, GET /health (+ demo UI and live metrics)."""
import asyncio
import json
import os
import random
import socket
import time
import uuid
from collections import deque
from contextlib import asynccontextmanager
from typing import Any, Optional, Union

import numpy as np
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi import Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from . import config, embed, indic
from .cache import get_cache
from .llm import BYPASS_DISK_CACHE
from .pipeline import troubleshoot
from .retrieval import catalog, kb

STATE = {"ready": False, "started": time.time()}
LAT = {"hit": deque(maxlen=2000), "miss": deque(maxlen=2000)}
COST = {"total_usd": 0.0, "requests": 0}
IMPACT = {"requests": 0, "hits": 0, "cold": 0, "no_answer": 0, "ai_cost_usd": 0.0, "engine_ms": 0, "since": time.time()}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    embed.warm()
    catalog()
    kb()
    get_cache()
    STATE["ready"] = True
    yield


app = FastAPI(title="OneTap – Smart Guided Troubleshooting Engine", version="1.0.0", lifespan=lifespan)


class TroubleshootRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    siis_response: Optional[Union[str, dict[str, Any]]] = None


async def _to_engine_language(query: str):
    """Complaint typed/spoken in an Indian script -> English for the engine. Returns (engine_query, info|None)."""
    if not (indic.enabled() and indic.has_indic(query)):
        return query, None
    t = time.perf_counter()
    try:
        en, lang = await indic.to_english(query)
    except indic.IndicError as e:
        return query, {"error": str(e)[:200]}
    return en, {"input_language": lang, "language_name": indic.LANG_NAMES.get(lang, lang), "translated_query": en,
                "ms": int((time.perf_counter() - t) * 1000)}


def _restore(out: dict, original: str, info) -> dict:
    if info and "translated_query" in info:
        out["query"] = original
        out["meta"].update({k: info[k] for k in ("input_language", "translated_query")})
        out["meta"]["latency_ms"] += info.get("ms", 0)
    return out


@app.post("/v1/troubleshoot")
async def post_troubleshoot(req: TroubleshootRequest, debug: bool = Query(False), nocache: bool = Query(False),
                            fresh: bool = Query(False), lookup_only: bool = Query(False),
                            catalog_fallback: bool = Query(False)):
    """nocache: skip the semantic cache (read+write). fresh: also skip the LLM prompt memo (true cold path)."""
    if not STATE["ready"]:
        raise HTTPException(503, "warming up")
    BYPASS_DISK_CACHE.set(fresh)
    original = req.query.strip()
    q, info = await _to_engine_language(original)
    out = await troubleshoot(q, req.siis_response, use_cache=not nocache, write_cache=not nocache,
                             debug=debug, lookup_only=lookup_only, catalog_fallback=catalog_fallback)
    out = _restore(out, original, info)
    _record(out)
    return JSONResponse(out)


class FeedbackRequest(BaseModel):
    plan_id: str = Field(..., min_length=4, max_length=64)
    helpful: bool


@app.post("/v1/feedback")
async def post_feedback(req: FeedbackRequest):
    """"Did this fix it?" - downvoted plans are evicted from the cache and recompiled on next request."""
    out = get_cache().feedback(req.plan_id, req.helpful)
    if not out.get("found"):
        raise HTTPException(404, "unknown plan_id")
    return out


# ---------------------------------------------------------------- live streaming (Feature B) + audience hub (Feature A)
class LiveHub:
    """Fan-out of pipeline events to every open /v1/live viewer (the projector mirrors phones in the audience)."""

    def __init__(self):
        self.subs: set[asyncio.Queue] = set()

    def publish(self, msg: dict) -> None:
        for q in list(self.subs):
            if q.qsize() < 500:
                q.put_nowait(msg)

    async def stream(self):
        q: asyncio.Queue = asyncio.Queue()
        self.subs.add(q)
        try:
            yield _sse("hello", {"viewers": len(self.subs)})
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=15)
                    yield _sse(msg["event"], msg["data"])
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            self.subs.discard(q)


HUB = LiveHub()


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _record(out: dict) -> None:
    m = out["meta"]
    (LAT["hit"] if m["cache_hit"] else LAT["miss"]).append(m["latency_ms"])
    COST["total_usd"] += m.get("cost_usd", 0.0)
    COST["requests"] += 1
    if m.get("fallback") == "cache_miss":          # lookup-only probes are not answers
        return
    IMPACT["requests"] += 1
    IMPACT["hits" if m["cache_hit"] else "cold"] += 1
    IMPACT["no_answer"] += int(not out["response"]["contexts"])
    IMPACT["ai_cost_usd"] += m.get("cost_usd", 0.0)
    IMPACT["engine_ms"] += m.get("latency_ms", 0)
    HUB.publish({"event": "impact", "data": impact_snapshot()})


def impact_snapshot() -> dict:
    """Live business impact. Baseline = manual triage time per complaint from the problem statement (15 min);
    agent cost and FX rate are stated assumptions, adjustable via .env."""
    n = IMPACT["requests"]
    manual_min = config.MANUAL_MINUTES_PER_COMPLAINT
    saved_min = max(0.0, n * manual_min - IMPACT["engine_ms"] / 60000)
    return {
        "requests": n, "cache_hits": IMPACT["hits"], "cold": IMPACT["cold"],
        "hit_rate": round(IMPACT["hits"] / n, 3) if n else None,
        "ai_cost_usd": round(IMPACT["ai_cost_usd"], 5), "ai_cost_inr": round(IMPACT["ai_cost_usd"] * config.USD_INR, 2),
        "avg_engine_ms": int(IMPACT["engine_ms"] / n) if n else None,
        "agent_minutes_saved": round(saved_min, 1),
        "agent_cost_saved_inr": round(saved_min / 60 * config.AGENT_INR_PER_HOUR, 0),
        "assumptions": {"manual_minutes_per_complaint": manual_min, "agent_inr_per_hour": config.AGENT_INR_PER_HOUR,
                        "usd_inr": config.USD_INR},
    }


@app.post("/v1/troubleshoot/stream")
async def post_troubleshoot_stream(req: TroubleshootRequest, request: Request, nocache: bool = Query(False),
                                   fresh: bool = Query(False), catalog_fallback: bool = Query(False),
                                   origin: str = Query("web")):
    """Same pipeline as /v1/troubleshoot, but every stage is pushed as a Server-Sent Event while it happens:
    cache -> source -> understood -> extracted -> grounded -> [reroute] -> actions -> deeplinks -> result."""
    if not STATE["ready"]:
        raise HTTPException(503, "warming up")
    rid = uuid.uuid4().hex[:8]
    queue: asyncio.Queue = asyncio.Queue()
    t0 = time.perf_counter()
    base = {"rid": rid, "origin": origin[:16], "query": req.query.strip()[:300]}

    async def emit(event, data):
        payload = {**base, "t_ms": int((time.perf_counter() - t0) * 1000), **(data or {})}
        await queue.put((event, payload))
        HUB.publish({"event": event, "data": payload})

    async def run():
        BYPASS_DISK_CACHE.set(fresh)
        try:
            await emit("start", {"siis": bool(req.siis_response)})
            original = req.query.strip()
            q, info = await _to_engine_language(original)
            if info:
                await emit("translated", info)
            out = await troubleshoot(q, req.siis_response, use_cache=not nocache,
                                     write_cache=not nocache, debug=True, catalog_fallback=catalog_fallback, emit=emit)
            out = _restore(out, original, info)
            _record(out)
            await emit("result", {"result": out})
        except Exception as e:  # surface failures to the viewer instead of hanging
            await emit("error", {"message": str(e)[:300]})
        finally:
            await queue.put(None)

    task = asyncio.create_task(run())

    async def gen():
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield _sse(*item)
        finally:
            if not task.done() and await request.is_disconnected():
                task.cancel()

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/v1/voice")
async def post_voice(file: UploadFile = File(...)):
    """A recorded complaint in any Indian language -> native transcript, detected language, English text."""
    if not indic.enabled():
        raise HTTPException(503, "Indian-language voice needs SARVAM_API_KEY in .env")
    audio = await file.read()
    if not audio or len(audio) > 5_000_000:
        raise HTTPException(400, "empty or too large recording (max ~30 s)")
    t = time.perf_counter()
    try:
        stt = await indic.speech_to_text(audio, file.filename or "speech.webm", file.content_type or "audio/webm")
        lang = stt["language_code"]
        english = stt["transcript"]
        if stt["transcript"] and lang not in ("en-IN", "unknown"):
            english, lang = await indic.to_english(stt["transcript"], lang)
    except indic.IndicError as e:
        raise HTTPException(502, str(e))
    return {"transcript": stt["transcript"], "language_code": lang, "language_name": indic.LANG_NAMES.get(lang, lang),
            "english": english, "ms": int((time.perf_counter() - t) * 1000)}


class TranslatePlanRequest(BaseModel):
    lang: str = Field(..., min_length=2, max_length=8)
    response: dict


@app.post("/v1/translate-plan")
async def post_translate_plan(req: TranslatePlanRequest):
    """Display-only translation of a plan into the user's language (the API contract itself stays English)."""
    if not indic.enabled():
        raise HTTPException(503, "needs SARVAM_API_KEY in .env")
    t = time.perf_counter()
    try:
        out = await indic.translate_plan(req.response, req.lang)
    except indic.IndicError as e:
        raise HTTPException(502, str(e))
    return {"response": out, "lang": req.lang, "ms": int((time.perf_counter() - t) * 1000)}


@app.get("/v1/config")
async def ui_config():
    """Feature flags the demo UI needs."""
    return {"indic": indic.enabled(), "languages": indic.LANG_NAMES}


@app.get("/v1/live")
async def live():
    """Projector view subscribes here and mirrors every streamed request (e.g. judges using their phones)."""
    return StreamingResponse(HUB.stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.get("/v1/impact")
async def impact():
    return impact_snapshot()


# ---------------------------------------------------------------- scale test (Feature D)
def _scale_queries(n: int) -> list[tuple[str, str]]:
    """Real complaint variants we hold: held-out paraphrases, adversarial look-alikes, and every stored
    rewording of every cached plan, shuffled (deterministic)."""
    pool = []
    ev = config.ROOT / "eval"
    for name in ("heldout_paraphrases.jsonl", "adversarial.jsonl", "human_paraphrases.jsonl"):
        p = ev / name
        if p.exists():
            pool += [json.loads(l)["text"] for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    for e in get_cache().entries.values():
        pool += [e["query"], *e.get("query_variations", [])]
    rnd = random.Random(7)
    rnd.shuffle(pool)
    out = []
    while len(out) < n and pool:
        out += [(q, "") for q in pool]
    return out[:n]


@app.post("/v1/scale-test")
async def scale_test(n: int = Query(1000, ge=50, le=5000)):
    """Fire n real complaint variants at the engine's memory (no AI calls), streaming progress as SSE, then
    project what compiling 10,000 scenarios would cost from the measured cold-path numbers."""
    cache = get_cache()
    queries = _scale_queries(n)
    queue: asyncio.Queue = asyncio.Queue()

    def work(loop):
        lat, hits, t0 = [], 0, time.perf_counter()
        for i, (q, siis) in enumerate(queries, 1):
            t = time.perf_counter()
            e, _ = cache.lookup(q, siis)
            lat.append((time.perf_counter() - t) * 1000)
            hits += bool(e)
            if i % 50 == 0 or i == len(queries):
                el = time.perf_counter() - t0
                srt = sorted(lat)
                loop.call_soon_threadsafe(queue.put_nowait, ("progress", {
                    "done": i, "total": len(queries), "hits": hits, "hit_rate": round(hits / i, 3),
                    "rps": round(i / el, 1), "p50_ms": round(srt[len(srt) // 2], 2),
                    "p95_ms": round(srt[int(0.95 * (len(srt) - 1))], 2)}))
        loop.call_soon_threadsafe(queue.put_nowait, None)

    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, work, loop)

    async def gen():
        last = None
        while True:
            item = await queue.get()
            if item is None:
                break
            last = item[1]
            yield _sse(*item)
        cold_cost = (IMPACT["ai_cost_usd"] / IMPACT["cold"]) if IMPACT["cold"] else config.EST_COLD_COST_USD
        cold_s = (IMPACT["engine_ms"] / max(1, IMPACT["requests"]) / 1000) if IMPACT["cold"] else config.EST_COLD_SECONDS
        yield _sse("summary", {**(last or {}), "projection_10k": {
            "compile_cost_usd": round(10_000 * cold_cost, 2), "compile_cost_inr": round(10_000 * cold_cost * config.USD_INR, 0),
            "compile_hours_at_8_parallel": round(10_000 * cold_s / 8 / 3600, 2),
            "cold_cost_per_scenario_usd": round(cold_cost, 5),
            "serving_capacity_per_day_millions": round((last or {}).get("rps", 0) * 86400 / 1e6, 1)}})

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


# ---------------------------------------------------------------- audience mode (Feature A)
def _lan_ips() -> list[str]:
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    return sorted(ip for ip in ips if not ip.startswith("127."))


@app.get("/v1/share")
async def share(request: Request):
    """URLs the audience can open: PUBLIC_URL (a tunnel, https - needed for phone microphones) first, then LAN."""
    port = request.url.port or 8000
    urls = []
    if config.PUBLIC_URL:
        urls.append(config.PUBLIC_URL.rstrip("/") + "/?audience=1")
    urls += [f"http://{ip}:{port}/?audience=1" for ip in _lan_ips()]
    return {"urls": urls, "viewers": len(HUB.subs)}


@app.get("/health")
async def health():
    c = get_cache() if STATE["ready"] else None
    ok = STATE["ready"] and embed.ready() and c is not None and bool(config.LLM_API_KEY)
    if not ok:
        return JSONResponse({"status": "starting", "llm_configured": bool(config.LLM_API_KEY)}, status_code=503)
    return {"status": "ok"}


def _pct(xs, p):
    return int(np.percentile(list(xs), p)) if xs else None


@app.get("/v1/metrics")
async def metrics():
    c = get_cache()
    return {
        "cache_entries": len(c.entries), "cache_vectors": int(len(c.mat)), "cache_stats": c.stats,
        "latency_ms": {k: {"n": len(v), "p50": _pct(v, 50), "p95": _pct(v, 95)} for k, v in LAT.items()},
        "cost": {"total_usd": round(COST["total_usd"], 6), "requests": COST["requests"]},
        "model": config.LLM_MODEL, "embedding": config.EMBED_MODEL, "catalog_size": len(catalog().entries),
    }


@app.get("/v1/examples")
async def examples():
    return [{"id": r["id"], "query": r["original_query"], "siis_response": r["siis_response"]} for r in kb().rows]


@app.get("/")
async def ui():
    return FileResponse(config.ROOT / "app" / "static" / "index.html")


@app.get("/static/{name}")
async def static_file(name: str):
    p = (config.ROOT / "app" / "static" / name).resolve()
    if p.parent != (config.ROOT / "app" / "static").resolve() or not p.is_file():
        raise HTTPException(404)
    return FileResponse(p)
