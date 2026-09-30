# OneTap: Smart Guided Troubleshooting Engine

**Samsung PRISM GenAI Hackathon 2026 · Theme 02: Guided Troubleshooting**

> Describe a phone problem in your own words and get a verified, ordered fix plan where every step is one tap away.
> About 10 ms from the semantic cache, a few seconds on a cold path, and every step is grounded in the support knowledge base.

OneTap is a REST API that turns vague device complaints ("screen keeps blinking then goes black when I unfold it")
into clean, ordered troubleshooting plans (JSON). Each Settings step is mapped to the exact in-app deeplink from the
catalog, non-invasive fixes come first and destructive ones last, and answers to previously seen problems come from a
guarded semantic cache in milliseconds.

---

## Highlights
| | |
|---|---|
| **Fast path** | Local bge-small embeddings (CPU, ~7 ms) + matrix search over a paraphrase cloud → cache hit P95 ≈ 10 ms (target ≤ 300 ms) |
| **Symptom-Signature Guard** | Rejects look-alike queries that need a different fix (e.g. Wi-Fi "keeps turning **on**" vs "**off**", same symptom in a different context): **44% → 10% false hits** at the same threshold |
| **Evidence-anchored extraction** | The LLM must cite the numbered reference sentence for every step; a grounding checker drops unsupported steps; when nothing relevant is left, the response is `contexts: []` + `fallback: no_match` |
| **Multi-intent** | "cracked where it folds + touch dead + can't see" → one Goal per distinct problem (identical plans merged) |
| **Deeplinks cannot be hallucinated** | An exact leaf-screen matcher, then hybrid BM25 + dense retrieval, depth-aware rerank, and a **closed-set** LLM choice (it returns a catalog ID, and code copies the URI). `validationDeeplink` is copied from the catalog |
| **Rules in code, not prompts** | Goal template, 2-3 word sentence-case title, Title Case action, 5-7 word "It will…" description, URL scrubbing, auto/manual/critical categories, critical last, schema gate (`schema.py`) |
| **Hedged LLM layer** | Any OpenAI-compatible provider; per-stage models; model-pool failover on 429/5xx; `retry-after` aware; prompt memoisation for deterministic reruns; per-request token cost in `meta` |

| **Catalog-grounded fallback** *(opt-in)* | No article covers the complaint? With `catalog_fallback=true` the LLM may only *pick* entries from the 577-entry Settings catalog; code writes every action/step from the entry itself (confidence capped at 0.70). Off by default, so the graded API contract is unchanged |
| **Self-healing cache** | `POST /v1/feedback {plan_id, helpful}`: a plan with more 👎 than 👍 is evicted and rebuilt from the source on the next request |
| **Guided mode + voice** | The demo UI walks users through one action at a time ("Didn't help → next", "✓ This fixed it"), with voice input (Web Speech API, `en-IN`) |
| **Paste any article** | Any help-page text works as `siis_response`, so the engine is not limited to the 20 provided scenarios |

Measured results are in **[metrics.md](metrics.md)**.

---

## Architecture
```
POST /v1/troubleshoot {query, siis_response?}
 │
 ├─ HOT PATH ── normalise (typos, Hinglish) → embed (bge-small, ONNX, CPU)
 │              → L0 exact  → L1 cosine over paraphrase cloud (τ = 0.87)
 │              → Symptom-Signature Guard (polarity · symptoms · trigger context) + same-article check
 │              → HIT: validated plan, $0, ~10 ms
 │
 └─ COLD PATH (miss)
      [0] Enrichment LLM ─┐ (parallel)   canonical query, topic, 8-10 query_variations
      [1] Extraction LLM ─┘              numbered SIIS sentences → issues → actions (one screen each) → steps + src ids
      [G] Grounding check                drop steps not supported by their cited sentences, self-referential steps, outcomes
      [C] Categorise                     auto / manual / critical (lexicon + kind), disruption ordering
      [2] Deeplink resolution            exact leaf match → hybrid BM25+dense → depth rerank → closed-set LLM choice
                                         → dummy_positive for real Settings screens without a catalog entry
      [R] Format repair                  batched LLM fix for word-count rules, deterministic fallback
      [V] Pydantic schema gate → calibrated score → write-back to cache (plan + paraphrase cloud)
```
If `siis_response` is omitted, OneTap first tries the cache and then the local SIIS knowledge base (hybrid retrieval).
If there is still no confident source, it returns `fallback: no_siis_context`.

### Score calibration
`score = 0.45·relevance + 0.25·grounded_step_ratio + 0.15·catalog_mapped_ratio + 0.15·source_similarity`,
which is explainable and not an LLM guess.

---

## Quick start

### Docker
```bash
cp .env.example .env         # add LLM_API_KEY (Groq) or GEMINI_API_KEY + LLM_BASE_URL
docker compose up --build
curl localhost:8000/health   # {"status":"ok"}
```

### Local (Python 3.10+)
```bash
pip install -r requirements.txt
cp .env.example .env         # add your key
python -m scripts.build_cache          # compile the 20 scenarios → results.jsonl + warm cache
uvicorn app.main:app --port 8000       # API + demo UI at http://localhost:8000
```

### API
```bash
curl -X POST localhost:8000/v1/troubleshoot -H "Content-Type: application/json" \
  -d '{"query": "phone swipe gestures wrong direction after app install", "siis_response": "<optional raw text>"}'
```
Response: `query`, `query_variations` (8-10), `response.contexts[Goal]`, `meta {latency_ms, cache_hit, model, cost_usd, fallback?}`.
Query flags: `debug=true` (pipeline trace), `nocache=true` (skip semantic cache), `fresh=true` (skip prompt memo),
`lookup_only=true` (cache probe), `catalog_fallback=true` (opt-in catalog-grounded plan when no article covers the complaint).
Every served or compiled plan carries `meta.plan_id`.

```bash
curl -X POST localhost:8000/v1/feedback -H "Content-Type: application/json" -d '{"plan_id": "<meta.plan_id>", "helpful": false}'
# -> {"plan_id": "...", "votes": {"up": 0, "down": 1}, "evicted": true}
```
Other endpoints: `GET /health`, `GET /v1/metrics`, `GET /v1/examples`, `GET /` (demo UI).

## Demo UI (http://127.0.0.1:8000)
* **Try a scenario**: 10 one-click cards, each showing one capability (cache hit, one-tap toggle, on/off direction, guard,
  multi-intent, Hinglish, catalog fallback, paste article, honest no-match, out-of-scope)
* **Phone**: complaint composer (Auto / Sample article / Paste article, voice input), step cards with one-tap buttons
  that open a simulated Settings screen and show the validation check, guided step-by-step mode, 👍/👎 feedback
* **Behind the scenes**: plain-English narration of what the engine did, a cache-similarity gauge with τ, guard
  rejections, a stage-timing waterfall (LLM vs local code), deeplink decisions, grounding results and the raw JSON.
  The "i" buttons explain each backend component

---

## Reproducing the evaluation
```bash
python -m scripts.build_cache --fresh      # results.jsonl (all provided scenarios, cold)
python -m scripts.make_eval                # held-out paraphrases (different model+prompt) + adversarial set
python -m scripts.eval_cache               # hit rate, false-hit rate, τ sweep, guard ablation
python -m scripts.bench --cold 30          # HTTP latency: exact hit, paraphrase hit, cold (server must be running)
python -m scripts.judge                    # LLM-judge accuracy + deeplink ablation (Baseline / A / B / ours)
python -m scripts.report                   # compliance audit + metrics.md
```

## Configuration (`.env`)
| Variable | Default | Purpose |
|---|---|---|
| `LLM_BASE_URL` / `LLM_API_KEY` | Groq | Any OpenAI-compatible endpoint |
| `LLM_MODEL` | `openai/gpt-oss-120b` | Phase 1 extraction |
| `LLM_ENRICH_MODEL` / `LLM_REPAIR_MODEL` | `qwen/qwen3.8-27b` | Enrichment and format repair |
| `LLM_FAST_MODEL` | `openai/gpt-oss-20b` | Closed-set deeplink choice |
| `LLM_MODEL_POOL` | the three above | Failover order on 429/5xx |
| `CACHE_TAU` | `0.87` | Semantic cache threshold (calibrated, see metrics.md) |
| `MIN_RELEVANCE` | `0.4` | Below this, an issue is answered with `no_match` |

## Repository layout
```
app/        main (FastAPI) · pipeline · stages (prompts) · rules · cache · retrieval · text · llm · embed · schema (given)
app/static/ demo UI (phone mock + live pipeline trace)
scripts/    build_cache · make_eval · eval_cache · bench · judge · report
eval/       held-out paraphrases, adversarial set, evaluation outputs
data/       provided starter assets (deeplinks, SIIS responses, queries) + persisted cache
docs/       PLAN.md
results.jsonl · metrics.md
```

## Limitations
See [metrics.md §6](metrics.md). In short: the signature lexicon is English + common Hinglish, the near-miss test set is
LLM-generated (so the false-hit rate is conservative), and cold latency depends on the provider tier.
