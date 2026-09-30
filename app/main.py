"""REST API: POST /v1/troubleshoot, GET /health (+ demo UI and live metrics)."""
import time
from collections import deque
from contextlib import asynccontextmanager
from typing import Any, Optional, Union

import numpy as np
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from . import config, embed
from .cache import get_cache
from .llm import BYPASS_DISK_CACHE
from .pipeline import troubleshoot
from .retrieval import catalog, kb

STATE = {"ready": False, "started": time.time()}
LAT = {"hit": deque(maxlen=2000), "miss": deque(maxlen=2000)}
COST = {"total_usd": 0.0, "requests": 0}


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


@app.post("/v1/troubleshoot")
async def post_troubleshoot(req: TroubleshootRequest, debug: bool = Query(False), nocache: bool = Query(False),
                            fresh: bool = Query(False), lookup_only: bool = Query(False),
                            catalog_fallback: bool = Query(False)):
    """nocache: skip the semantic cache (read+write). fresh: also skip the LLM prompt memo (true cold path)."""
    if not STATE["ready"]:
        raise HTTPException(503, "warming up")
    BYPASS_DISK_CACHE.set(fresh)
    out = await troubleshoot(req.query.strip(), req.siis_response, use_cache=not nocache, write_cache=not nocache,
                             debug=debug, lookup_only=lookup_only, catalog_fallback=catalog_fallback)
    m = out["meta"]
    (LAT["hit"] if m["cache_hit"] else LAT["miss"]).append(m["latency_ms"])
    COST["total_usd"] += m.get("cost_usd", 0.0)
    COST["requests"] += 1
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
