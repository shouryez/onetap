"""Orchestrates hot path (semantic cache) and cold path (enrich ∥ extract → ground → map → order → validate)."""
import asyncio
import re
import time

import numpy as np

from . import catalog_plan, config, rules, stages
from .cache import get_cache
from .embed import embed_one
from .llm import BYPASS_DISK_CACHE, LLMError, start_usage
from .retrieval import catalog, kb, siis_to_text
from .schema import ContextDeeplinkResponse
from .text import normalise, split_sentences, words

MAPPING_MODES = ("ours", "hybrid_only", "rules_only", "full_llm")


def _ms(t0: float) -> int:
    return int(round((time.perf_counter() - t0) * 1000))


def _fallback_variations(query: str) -> list[str]:
    return [query]


async def _emit(emit, event: str, data: dict) -> None:
    if emit is not None:
        try:
            await emit(event, data)
        except Exception:  # a disconnected viewer must never break the pipeline
            pass


async def troubleshoot(query: str, siis_response=None, *, use_cache: bool = True, write_cache: bool = True,
                       debug: bool = False, mapping_mode: str = "ours", lookup_only: bool = False,
                       fresh_mapping: bool = False, catalog_fallback: bool = False, emit=None) -> dict:
    """emit: optional async callback(event, data) used by the streaming endpoint to show each stage live."""
    t0 = time.perf_counter()
    usage = start_usage()
    trace: dict = {"stages": {}}
    siis_text = siis_to_text(siis_response)
    cache = get_cache()

    # ------------------------------------------------------------------ HOT PATH
    if use_cache:
        t = time.perf_counter()
        entry, info = cache.lookup(query, siis_text)
        trace["stages"]["cache_lookup_ms"] = _ms(t)
        trace["cache"] = info
        await _emit(emit, "cache", {**info, "hit": bool(entry), "ms": trace["stages"]["cache_lookup_ms"]})
        if entry:
            out = {
                "query": query,
                "query_variations": entry["query_variations"],
                "response": entry["response"],
                "meta": {"latency_ms": _ms(t0), "cache_hit": True, "model": entry.get("model") or config.LLM_MODEL,
                         "cost_usd": 0.0, "match": info.get("match"), "similarity": info.get("similarity"),
                         "plan_id": entry["id"], **({"source": entry["source"]} if entry.get("source") else {})},
            }
            if not entry["response"]["contexts"]:
                out["meta"]["fallback"] = "no_match"
            if debug:
                out["trace"] = trace
            return out

    if lookup_only:   # benchmarking / probing: never trigger the cold path
        return {"query": query, "query_variations": [], "response": {"contexts": []},
                "meta": {"latency_ms": _ms(t0), "cache_hit": False, "model": None, "cost_usd": 0.0,
                         "fallback": "cache_miss"}, **({"trace": trace} if debug else {})}

    # ------------------------------------------------------------------ source selection
    fallback = None
    source_sim = 1.0
    siis_provided = bool(siis_text)
    if not siis_text:
        art, sim = kb().best(normalise(query))
        trace["kb_retrieval"] = {"title": art["title"] if art else None, "similarity": round(sim, 3)}
        if art and sim >= config.KB_MIN_SIM:
            siis_text = f"{art['title']}\n{art['content']}"
            source_sim = sim
        else:
            siis_text = ""
    else:
        source_sim = float(embed_one(normalise(query)) @ embed_one(normalise(siis_text[:1500])))

    sentences = split_sentences(siis_text) if siis_text else []
    await _emit(emit, "source", {"kind": "given" if siis_provided else ("kb" if siis_text else "none"),
                                 "title": siis_text.split("\n", 1)[0][:120] if siis_text else None,
                                 "similarity": round(source_sim, 3), "sentences": len(sentences)})

    # ------------------------------------------------------------------ COLD PATH: enrich ∥ extract
    t = time.perf_counter()
    try:
        enrich_task = asyncio.create_task(stages.enrich(query))
        if emit is not None:
            def _on_enrich(tk):
                if not tk.cancelled() and tk.exception() is None:
                    r = tk.result() or {}
                    asyncio.ensure_future(_emit(emit, "understood", {"canonical_query": r.get("canonical_query"),
                                                                     "topic": r.get("topic"), "ms": _ms(t)}))
            enrich_task.add_done_callback(_on_enrich)
        if sentences:
            extract_res = await stages.extract(query, sentences)
        else:
            extract_res = {"issues": []}
            fallback = "no_siis_context"
        enrich_res = await enrich_task
    except LLMError as e:
        enrich_task.cancel()
        return _error_response(query, t0, usage, str(e))
    trace["stages"]["llm_enrich_extract_ms"] = _ms(t)
    await _emit(emit, "extracted", {"issues": len(extract_res.get("issues") or []),
                                    "steps": sum(len(a.get("steps") or []) for i in (extract_res.get("issues") or [])
                                                 for a in (i.get("actions") or [])),
                                    "ms": trace["stages"]["llm_enrich_extract_ms"]})
    trace["enrichment"] = {k: enrich_res.get(k) for k in ("canonical_query", "topic")}

    variations = _clean_variations(query, enrich_res.get("query_variations") or [])

    # ------------------------------------------------------------------ opt-in catalog-grounded fallback
    if not sentences and catalog_fallback:
        t = time.perf_counter()
        try:
            contexts, cinfo = await catalog_plan.build(query, enrich_res, config.LLM_MODEL)
        except LLMError as e:
            contexts, cinfo = [], {"error": str(e)[:200]}
        trace["catalog_fallback"] = cinfo
        await _emit(emit, "catalog", cinfo)
        trace["stages"]["catalog_plan_ms"] = _ms(t)
        response = {"contexts": contexts}
        ContextDeeplinkResponse(**response)
        meta = {"latency_ms": _ms(t0), "cache_hit": False, "model": "+".join(sorted(usage.models)) or config.LLM_MODEL,
                "cost_usd": usage.cost_usd, "llm_calls": usage.calls, "source": "catalog"}
        if not contexts:
            meta["fallback"] = "no_siis_context"
        elif write_cache:
            meta["plan_id"] = get_cache().put(query, variations, response, "", meta, source="catalog",
                                              aliases=_aliases(enrich_res))
            _grow_cloud(meta["plan_id"], query)
        out = {"query": query, "query_variations": variations, "response": response, "meta": meta}
        if debug:
            trace["stages"]["total_ms"] = meta["latency_ms"]
            out["trace"] = trace
        return out

    # ------------------------------------------------------------------ ground + normalise
    t = time.perf_counter()
    goals_work, grounding_log = _ground(extract_res, sentences, siis_text)
    trace["stages"]["grounding_ms"] = _ms(t)
    await _emit(emit, "grounded", {"kept": sum(len(a["steps"]) for g in goals_work for a in g["actions"]),
                                   "dropped": len(grounding_log), "examples": grounding_log[:3]})

    # ------------------------------------------------------------------ second reading before giving up on an article
    if sentences and not goals_work:
        t = time.perf_counter()
        try:
            res2 = await stages.extract(query, sentences, second_reading=True, model=config.LLM_RESCUE_MODEL)
            g2, log2 = _ground(res2, sentences, siis_text)
            rel2 = max((g["relevance"] for g in g2), default=0.0)
            trace["second_reading"] = {"goals": len(g2), "relevance": rel2, "ms": _ms(t)}
            if g2 and rel2 >= config.RESCUE_MIN_RELEVANCE:   # only a clearly relevant reading may rescue
                goals_work, grounding_log = g2, log2
                await _emit(emit, "grounded", {"kept": sum(len(a["steps"]) for g in g2 for a in g["actions"]),
                                               "dropped": len(log2), "second_reading": True})
        except LLMError as e:
            trace["second_reading"] = {"error": str(e)[:150]}

    # ------------------------------------------------------------------ re-route: the given article doesn't cover it
    source = None
    best_rel = max((g["relevance"] for g in goals_work), default=0.0)
    if sentences and best_rel < config.REROUTE_BELOW:          # attached OR auto-picked article too weak
        t = time.perf_counter()
        alt, alt_sim = kb().best(normalise(query), exclude_text=siis_text)
        info = {"given_article_relevance": round(best_rel, 2), "candidate": alt["title"] if alt else None,
                "similarity": round(alt_sim, 3), "used": False}
        if alt and alt_sim >= config.KB_MIN_SIM:
            alt_text = f"{alt['title']}\n{alt['content']}"
            alt_sentences = split_sentences(alt_text)
            try:
                alt_res = await stages.extract(query, alt_sentences, model=config.LLM_RESCUE_MODEL)
                alt_goals, alt_log = _ground(alt_res, alt_sentences, alt_text)
                alt_rel = max((g["relevance"] for g in alt_goals), default=0.0)
                info["candidate_relevance"] = round(alt_rel, 2)
                if alt_goals and alt_rel > best_rel and alt_rel >= config.RESCUE_MIN_RELEVANCE:
                    goals_work, grounding_log = alt_goals, alt_log + grounding_log
                    sentences, siis_text, source_sim, source = alt_sentences, alt_text, alt_sim, "kb_rerouted"
                    info["used"] = True
            except LLMError as e:
                info["error"] = str(e)[:150]
        trace["reroute"] = info
        await _emit(emit, "reroute", info)
        trace["stages"]["reroute_ms"] = _ms(t)
    trace["grounding"] = {"dropped": grounding_log}

    # ------------------------------------------------------------------ categorise + map deeplinks
    t = time.perf_counter()
    all_actions = [a for g in goals_work for a in g["actions"]]
    for a in all_actions:
        a["category"] = rules.categorise(a)
    await _emit(emit, "actions", {"goals": [{"topic": (g["issue"].get("topic") or ""), "actions": [
        {"actionName": a["actionName"], "category": a["category"], "steps": a["steps"]}
        for a in rules.order_actions(g["actions"])]} for g in goals_work]})
    _cost_before_map = usage.cost
    tok = BYPASS_DISK_CACHE.set(True) if fresh_mapping else None   # ablation: real mapping latency/cost
    try:
        await map_deeplinks(all_actions, mode=mapping_mode, trace=trace)
    except LLMError as e:
        out = _error_response(query, t0, usage, str(e))
        if debug:
            out["trace"] = trace
        return out
    finally:
        if tok is not None:
            BYPASS_DISK_CACHE.reset(tok)
    trace["stages"]["deeplink_mapping_ms"] = _ms(t)
    trace["mapping_cost_usd"] = round(usage.cost - _cost_before_map, 6)
    _drop_contradictions(goals_work, trace)
    await _emit(emit, "deeplinks", {"links": [{"action": a["actionName"], "message": (a.get("_dl") or {}).get("message"),
                                               "deeplink": (a.get("_dl") or {}).get("deeplink")}
                                              for g in goals_work for a in g["actions"] if a.get("_dl")],
                                    "ms": trace["stages"]["deeplink_mapping_ms"]})

    # ------------------------------------------------------------------ format repair (batched LLM, then deterministic)
    t = time.perf_counter()
    await _repair_fields(goals_work)
    trace["stages"]["repair_ms"] = _ms(t)

    # ------------------------------------------------------------------ assemble
    contexts = []
    for g in goals_work:
        issue = g["issue"]
        acts = rules.order_actions(g["actions"])
        auto = [a for a in acts if a["category"] != "manual"]
        mapped = sum(1 for a in auto if a.get("_dl") and a["_dl"]["deeplink"] != catalog().dummy["deeplink"])
        score = rules.calibrated_score(g["relevance"], g["grounded_ratio"], mapped / len(auto) if auto else 1.0,
                                       source_sim)
        contexts.append({
            "goal": rules.goal_text(issue.get("topic") or enrich_res.get("topic") or "Device", issue.get("goal_type")),
            "title": g["title"],
            "score": score,
            "actions": [{
                "actionName": a["actionName"],
                "description": a["description"],
                "stepGroups": [{"steps": a["steps"], "actionableDeeplink": a.get("_dl"),
                                "validationDeeplink": a.get("_val")}],
                "category": a["category"],
            } for a in acts],
        })
    # multi-intent can yield identical plans for sibling issues -> keep one
    seen_plans, deduped = set(), []
    for c in contexts:
        key = tuple(a["actionName"] for a in c["actions"])
        if key not in seen_plans:
            seen_plans.add(key)
            deduped.append(c)
    contexts = sorted(deduped, key=lambda c: -c["score"])
    response = {"contexts": contexts}
    ContextDeeplinkResponse(**response)  # hard schema gate (raises on violation)
    if not contexts and not fallback:
        fallback = "no_match"

    meta = {"latency_ms": _ms(t0), "cache_hit": False, "model": "+".join(sorted(usage.models)) or config.LLM_MODEL,
            "cost_usd": usage.cost_usd,
            "llm_calls": usage.calls, "tokens": {"prompt": usage.prompt_tokens, "completion": usage.completion_tokens}}
    if fallback:
        meta["fallback"] = fallback
    if source:
        meta["source"] = source
        meta["rerouted_to"] = siis_text.split("\n", 1)[0][:120]
    out = {"query": query, "query_variations": variations, "response": response, "meta": meta}
    if write_cache and fallback != "no_siis_context":
        meta["plan_id"] = get_cache().put(query, variations, response, siis_to_text(siis_response), meta,
                                          aliases=_aliases(enrich_res))
        _grow_cloud(meta["plan_id"], query)
    if debug:
        trace["stages"]["total_ms"] = meta["latency_ms"]
        out["trace"] = trace
    return out


def _aliases(enrich_res: dict) -> list[str]:
    """Extra texts stored only for cache matching (the response keeps exactly 8-10 variations)."""
    return [a for a in [enrich_res.get("canonical_query") or ""] if a.strip()]


_BG: set = set()


def _grow_cloud(eid: str, query: str) -> None:
    """After a plan is written back, add ~10 Indian-style rewordings to its cache entry in the background."""
    async def job():
        try:
            get_cache().add_aliases(eid, await stages.extra_variations(query))
        except Exception:
            pass
    task = asyncio.ensure_future(job())
    _BG.add(task)
    task.add_done_callback(_BG.discard)


async def drain() -> None:
    """Batch jobs: wait for background cache enrichment before exiting."""
    while _BG:
        await asyncio.gather(*list(_BG), return_exceptions=True)


def _drop_contradictions(goals_work: list[dict], trace: dict) -> None:
    """Two actions that flip the SAME setting in opposite directions (onURL vs offURL of one validation key)
    would cancel out; keep the first (the article's primary advice), drop the later one."""
    seen: dict[str, str] = {}
    dropped = []
    for g in goals_work:
        keep = []
        for a in g["actions"]:
            dl, val = a.get("_dl") or {}, a.get("_val") or {}
            key, typ = val.get("key"), dl.get("originalType")
            if key and typ in ("onURL", "offURL"):
                if seen.get(key) and seen[key] != typ:
                    dropped.append({"action": a["actionName"], "reason": f"contradicts earlier {seen[key]} on '{key}'"})
                    continue
                seen.setdefault(key, typ)
            keep.append(a)
        g["actions"] = keep
    if dropped:
        trace.setdefault("grounding", {}).setdefault("dropped", []).extend(
            {"step": d["action"], "reason": d["reason"]} for d in dropped)


def _ground(extract_res: dict, sentences: list[str], siis_text: str) -> tuple[list[dict], list[dict]]:
    """Keep only steps supported by their cited sentences; drop issues the article barely addresses."""
    article_lower = siis_text.lower()
    goals_work, grounding_log = [], []
    for issue in (extract_res.get("issues") or [])[:3]:
        rel = float(issue.get("relevance") or 0)
        kept_actions, total_steps, kept_steps = [], 0, 0
        for a in issue.get("actions") or []:
            steps_out = []
            for st in a.get("steps") or []:
                txt = st.get("text", "") if isinstance(st, dict) else str(st)
                src = st.get("src", []) if isinstance(st, dict) else []
                total_steps += 1
                if rules.is_self_referential(txt, a.get("actionName") or ""):
                    grounding_log.append({"step": txt, "reason": "self_referential"})
                    continue
                ok, cov = rules.ground_step(txt, src, sentences, article_lower)
                if ok:
                    steps_out.append(txt)
                    kept_steps += 1
                else:
                    grounding_log.append({"step": txt, "coverage": round(cov, 2)})
            steps_out = rules.clean_steps(steps_out)
            if not steps_out:
                continue
            kept_actions.append({
                "actionName": rules.fix_action_name(a.get("actionName") or "Follow Steps"),
                "description": a.get("description") or "",
                "screen": a.get("screen") or "",
                "kind": a.get("kind") or "other",
                "toggle": a.get("toggle") or "none",
                "steps": steps_out,
            })
        if not kept_actions or rel < config.MIN_RELEVANCE:
            grounding_log.append({"issue_dropped": issue.get("issue"), "relevance": rel})
            continue
        goals_work.append({"issue": issue, "relevance": rel, "actions": kept_actions,
                           "grounded_ratio": kept_steps / max(1, total_steps)})
    return goals_work, grounding_log


def _error_response(query: str, t0: float, usage, err: str) -> dict:
    return {"query": query, "query_variations": [query], "response": {"contexts": []},
            "meta": {"latency_ms": _ms(t0), "cache_hit": False, "model": config.LLM_MODEL,
                     "cost_usd": usage.cost_usd, "fallback": "engine_error", "error": err[:300]}}


def _clean_variations(query: str, vs: list[str]) -> list[str]:
    from .text import has_url, scrub_urls
    out, seen = [], {normalise(query)}
    for v in vs:
        v = scrub_urls(str(v)).strip().strip('"')
        n = normalise(v)
        if v and n not in seen and not has_url(v):
            seen.add(n)
            out.append(v)
    if len(out) < 8:
        # deterministic top-up so the 8-10 contract always holds
        extra = [f"{query} - how do I fix this?", f"Help: {query}", f"Troubleshoot: {normalise(query)}",
                 f"{normalise(query)} fix", f"How to solve: {query}", f"Issue - {query}", f"{query} Please help.",
                 f"Need help, {query[0].lower() + query[1:] if query else query}"]
        for e in extra:
            if len(out) >= 8:
                break
            if normalise(e) not in seen:
                seen.add(normalise(e)); out.append(e)
    return out[:10]


# ============================================================================ deeplink mapping
async def map_deeplinks(actions: list[dict], mode: str = "ours", trace: dict | None = None) -> None:
    cat = catalog()
    blocks = []
    for i, a in enumerate(actions):
        a["_dl"], a["_val"] = None, None
        if a["category"] == "manual":
            continue
        if not a.get("screen") and not any(re.search(r"settings|toggle|switch", st, re.I) for st in a["steps"]):
            continue  # not performed on a Settings screen -> nothing in the catalog can open it
        q = f"{a['actionName']}. {a['screen']}. {' '.join(a['steps'])}"
        if mode == "rules_only":
            cands = cat.bm25_top(q, 8)
            best = rules.rerank(a, [(e, 0.0) for e, _ in cands])
            if cands and cands[0][1] > 6.0:
                _assign(a, best[0][0])
            continue
        if mode == "ours":
            exact = rules.exact_screen_match(a, cat.search)
            if exact:                              # unambiguous leaf-screen match: no LLM needed
                _assign(a, exact)
                if trace is not None:
                    trace.setdefault("deeplinks", []).append({"action": a["actionName"], "chosen": exact["id"],
                                                              "method": "exact_leaf_match"})
                continue
        cands = cat.retrieve(q, 20)
        if mode == "hybrid_only":
            if cands and cands[0][1] >= 0.72:
                _assign(a, cands[0][0])
            continue
        ranked = rules.rerank(a, cands)[: config.DEEPLINK_TOPK]
        blocks.append({"index": i, "actionName": a["actionName"], "screen": a["screen"], "toggle": a["toggle"],
                       "steps": a["steps"], "candidates": [e for e, _ in ranked]})

    if mode == "full_llm":
        # compact catalog (id|type|message) so all 577 entries fit the provider's context/TPM budget
        lines = "\n".join(f'{e["id"]}|{e.get("originalType") or "-"}|{e.get("message")}' for e in cat.search)
        res = []
        for b in blocks:                                   # sequential: each call carries the whole catalog
            res.append(await stages.full_llm_choose(b, lines))
        for b, r in zip(blocks, res):
            e = cat.by_id.get(str(r.get("id")))
            if e:
                _assign(actions[b["index"]], e)
        _finalise_unmapped(actions)
        return

    if blocks:
        res = await stages.choose_deeplinks(blocks)
        by_action = {int(c.get("action", -1)): c for c in res.get("choices", []) if str(c.get("action", "")).lstrip("-").isdigit()}
        for b in blocks:
            a = actions[b["index"]]
            c = by_action.get(b["index"], {})
            allowed = {e["id"] for e in b["candidates"]}
            cid = str(c.get("id", "NONE"))
            if cid in allowed:                     # closed-set: only an offered candidate can be used
                _assign(a, cat.by_id[cid])
            else:
                a["_dummy_desc"] = c.get("dummy_description")
                a["_dummy_msg"] = c.get("dummy_message")
            if trace is not None:
                trace.setdefault("deeplinks", []).append({
                    "action": a["actionName"], "chosen": cid,
                    "candidates": [f'{e["id"]}: {e.get("message")}' for e in b["candidates"][:5]]})
    _finalise_unmapped(actions)


def _assign(a: dict, e: dict) -> None:
    a["_dl"] = rules.deeplink_obj(e)
    a["_val"] = rules.validation_obj(e)


def _finalise_unmapped(actions: list[dict]) -> None:
    """No catalog match: dummy_positive if the action really happens on a Settings screen, else manual."""
    dummy = catalog().dummy
    for a in actions:
        if a["category"] == "manual" or a.get("_dl"):
            continue
        on_settings = bool(a.get("screen")) or any("settings" in s.lower() for s in a["steps"])
        if on_settings and a["category"] == "auto":
            leaf = rules.leaf_of(a) or a["actionName"]
            desc = rules.fit_words(a.get("_dummy_desc") or "", 5, 7) or rules.force_words(f"Open {leaf} settings screen on device", 5, 7)
            msg = rules.fit_words(a.get("_dummy_msg") or "", 5, 7) or rules.force_words(f"Open the {leaf} settings screen", 5, 7, pad="now")
            a["_dl"] = {"deeplink": dummy["deeplink"], "description": desc, "message": msg,
                        "originalType": dummy.get("originalType")}
        elif a["category"] == "auto":
            a["category"] = "manual"


# ============================================================================ format repair
async def _repair_fields(goals_work: list[dict]) -> None:
    desc_bad, title_bad = [], []
    for gi, g in enumerate(goals_work):
        issue = g["issue"]
        t = rules.fix_title(issue.get("title") or issue.get("topic") or "Device issue")
        g["title"] = t
        if not (2 <= len(words(t)) <= 3):
            title_bad.append((gi, t, issue.get("issue") or ""))
        for a in g["actions"]:
            d = rules.fit_words(a["description"], 5, 7, prefix="It will")
            if d:
                a["description"] = d
            else:
                desc_bad.append((len(desc_bad), a["description"], a["actionName"], a))
    try:
        jobs = []
        if desc_bad:
            jobs.append(stages.repair("description", [(i, d, n) for i, d, n, _ in desc_bad]))
        if title_bad:
            jobs.append(stages.repair("title", [(i, t, c) for i, t, c in title_bad]))
        res = await asyncio.gather(*jobs) if jobs else []
    except LLMError:
        res = []
    ri = 0
    if desc_bad:
        fixes = {int(f["i"]): f["value"] for f in (res[ri].get("fixes", []) if ri < len(res) else []) if "i" in f}
        ri += 1
        for i, d, _n, a in desc_bad:
            a["description"] = rules.fit_words(fixes.get(i, ""), 5, 7, prefix="It will") or \
                rules.compact_description(d, a["actionName"])
    if title_bad:
        fixes = {int(f["i"]): f["value"] for f in (res[ri].get("fixes", []) if ri < len(res) else []) if "i" in f}
        for gi, t, _c in title_bad:
            nt = rules.fix_title(fixes.get(gi, ""))
            goals_work[gi]["title"] = nt if 2 <= len(words(nt)) <= 3 else rules.fix_title(
                rules.force_words(t, 2, 3, pad="issue"))
    for g in goals_work:
        for a in g["actions"]:
            a["description"] = a["description"].rstrip(".")
            if not a["description"].startswith("It will"):
                a["description"] = "It will" + a["description"][7:]
