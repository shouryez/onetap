# System Performance Metrics & Evaluation Report

**Model(s):** Groq `openai/gpt-oss-120b` (Phase 1 extraction) · `qwen/qwen3.8-27b` (enrichment, repair) · `openai/gpt-oss-20b` (closed-set deeplink choice)
**Embeddings:** `BAAI/bge-small-en-v1.5` (ONNX via fastembed, CPU, 384-d)
**Environment:** Windows 11 · Python 3.14.5 · CPU-only · single process (uvicorn)
**Data:** 20 provided scenarios (`siis_responses.json`), 577-entry deeplink catalog, 97 held-out paraphrases,
40 near-miss + 10 out-of-domain adversarial queries (`eval/`)

---

## 1. Schema & Rule Compliance
Evaluated on `results.jsonl` (all 20 provided scenarios, 21 goals).

| Metric | Target | Measured Value |
| :--- | :--- | :--- |
| Schema-valid output lines | >= 99% | 100.0% |
| Rule compliance (Goal / Title / Description syntax) | >= 95% | 100.0% |
| Absolute URL leaks | 0 | 0 |
| Deeplink catalog validity (exact URI match) | 100% | 100.0% (7 deeplinks) |
| Auto actions carrying valid actionable deeplink | >= 90% | 100.0% (80.0% dedicated catalog entry, rest `dummy_positive`) |
| `query_variations` with 8-10 items | 100% | 100.0% |

Honest `no_match` responses (reference article does not address the complaint): 2 / 20.
Multi-intent complaints answered with more than one Goal: 3.

---

## 2. Accuracy Benchmarks
LLM-as-judge (Gemini Flash family, a different model family from the generator, strict rubric, reference article in context) over the 20 provided scenarios.

| Evaluation Metric | Scale / Anchor | Score |
| :--- | :--- | :--- |
| Step accuracy (completeness, correctness, ordering) | 0.0 - 3.0 | 2.25 |
| Deeplink relevance (exact target screen vs. parent menu) | 0.0 - 2.0 | 1.43 (n=7) |

---

## 3. Latency Benchmarks (N >= 30 requests per path)
Client-side wall clock over HTTP on localhost (server-side `meta.latency_ms` in brackets).

| Execution Path | Target (P95) | P50 (ms) | P95 (ms) |
| :--- | :--- | :--- | :--- |
| Cache hit - exact query match (N=40) | <= 300 ms | 0.9 [0] | 1.1 [0] |
| Cache hit - unseen semantic paraphrase (N=80) | <= 300 ms | 8.3 [7] | 10.4 [9] |
| Cold query - full pipeline extraction & mapping (N=30) | <= 8000 ms | 4085 [2026] | 5266 [3210] |

Cold requests were spaced 18 s apart (provider tokens-per-minute limit), so each opened a new HTTP connection to
`localhost`; on Windows that first tries IPv6 and adds ~2 s per new connection (measured: 2297 ms vs 218 ms via
`127.0.0.1`). The bracketed server-side numbers are the pipeline itself. `scripts/bench.py` now defaults to `127.0.0.1`.

Cache lookup alone (embedding + matrix search + guard, in-process): P50 6.84 ms · P95 8.82 ms.

---

## 4. Operational Cost & Cache Efficacy

| Metric Item | Target | Measured Value |
| :--- | :--- | :--- |
| Cold query average inference cost | Tracked | $0.00080 |
| Cache hit inference cost | $0.00 | $0.00 |
| Semantic cache hit rate (on unseen paraphrases) | >= 80% | 82.5% (correct-article hits 82.5%) |
| False-hit rate on adversarial near-miss / out-of-domain queries | (ours) | 10.0% (without Symptom-Signature Guard: 44.0%) |
| Cost derivation method | - | (prompt tokens x input rate + completion tokens x output rate) per model, summed per request |

Threshold sweep (query-only lookups, guard on):

| tau | hit rate | false-hit rate |
| :--- | :--- | :--- |
| 0.8 | 95.9% | 32.0% |
| 0.83 | 93.8% | 24.0% |
| 0.86 | 84.5% | 12.0% |
| 0.89 | 79.4% | 4.0% |
| 0.92 | 54.6% | 2.0% |

Operating point: tau = 0.87 (max hit rate subject to hit >= 80% and false hits <= 10%).

---

## 5. Architectural Ablation Analysis
Only the deeplink stage varies (identical extraction), mapping LLM calls made fresh. Latency / cost = mapping stage per query.

| Architecture Variant | Step Accuracy | Deeplink relevance (0-2) | Mapping latency P95 | Cost / Query | Key Observations |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Baseline: Full LLM Deeplink Mapping (whole catalog in prompt) | 2.25 | 1.17 (n=6, 3 catalog) | 16897 ms | $0.00091 | Large prompt per action; picks parent menus; slowest/most expensive |
| **OneTap: exact-leaf match + hybrid + depth rerank + closed-set LLM** | 2.25 | 1.43 (n=7, 6 catalog) | 633 ms | $0.00002 | Deterministic when the leaf screen is unambiguous; LLM only chooses among candidates |

**Ground-truth deeplink resolution benchmark** (`scripts/eval_deeplinks.py`): 24 catalog targets (open-page / enable /
disable, stratified). An LLM wrote a realistic action for each without the catalog wording; every variant must recover
the exact catalog entry.

| Variant | Accuracy@1 (exact entry) | Right screen, wrong on/off twin | No deeplink | Latency P50 / P95 | Cost / action |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Baseline: Full LLM Deeplink Mapping (whole catalog in prompt) | 62.5% | 8.3% | 16.7% | 1104 / 1381 ms | $0.00261 |
| Variant A: Hybrid BM25 + Dense Embedding Retrieval (top-1) | 91.7% | 8.3% | 0.0% | 1 / 8 ms | $0.00000 |
| Variant B: Pure Rules-Based Deeplink Mapping (BM25 keyword) | 91.7% | 4.2% | 0.0% | 1 / 1 ms | $0.00000 |
| **OneTap: exact-leaf match + hybrid + depth rerank + closed-set LLM** | 95.8% | 0.0% | 4.2% | 518 / 5438 ms | $0.00006 |

Symptom-Signature Guard ablation (same tau): hit rate 96.9% -> 82.5%,
false hits 44.0% -> 10.0%.

---

## 6. Known Edge Cases & System Limitations
* **Mismatched reference articles.** Several provided SIIS articles do not address the complaint (e.g. an email-server
  article for a display fault). OneTap extracts only relevant, grounded steps and otherwise returns
  `contexts: []` + `fallback: no_match`, which lowers coverage by design rather than inventing steps.
* **Adversarial near-miss set is LLM-generated.** Some "negatives" describe arguably the same fault, so the reported
  false-hit rate is conservative (an upper bound).
* **Lexicon-based signatures** (symptom / context / polarity) are English + common Hinglish/typos; unseen slang can miss
  the guard. A learned classifier is the natural next step.
* **Masked deeplinks.** Where the catalog has no dedicated screen, `voiceassist://dummy_positive` is used with a
  generated 5-7 word description; manual (physical/service) actions never carry deeplinks.
* **Provider rate limits.** Cold latency depends on the LLM provider tier. The benchmark above ran with quota available.
  In a later 10-request spot check, after the evaluation runs had used up Groq's *free-tier* daily token cap for
  `gpt-oss-120b` (200K tokens/day, 8K tokens/min), extraction fell back to smaller models and waited on per-minute limits:
  cold P50 rose to ~11 s. The serving path now waits at most 3 s before hedging to the next model; production should
  use a paid tier (limits ~30x higher, same ~$0.001/query).
* **Settings hierarchy variation** across One UI versions is not modelled; the reverse index deeplink -> plans supports
  targeted recompilation when the catalog changes.
