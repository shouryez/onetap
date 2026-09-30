# OneTap: Build Plan (deadline 30 Sep 2026, 11:59 PM)

## Facts from the starter data (these drive the design)
| Finding | Consequence |
|---|---|
| `deeplinks.json`: 578 entries, scheme `voiceassist://masked/act/...`; types onURL/offURL (138 pairs), onClickURL 254, updateURL 36; every entry has `validation` (key, some with resultType/condition/value) | LLM **chooses a catalog ID** and code copies the URI + validation block verbatim. On/off twins are resolved from the step's verb (enable vs disable). |
| `DL-DUMMY` = `voiceassist://dummy_positive`: we write description/message (5–7 words) ourselves | Used only when an action opens a real Settings screen with no catalog match. |
| Catalog contains non-phone rows (refrigerator, air conditioner) and diagnostic rows | Retrieval filters on relevance; the depth-aware reranker prefers the leaf screen. |
| `siis_responses.json`: 20 rows `{id, original_query, siis_response:{title, content}}`; articles are often **off-topic** (e.g. "screen flashes" → *email server* article) | Relevance-aware extraction: only steps that address the complaint; otherwise `contexts: []` + `fallback: no_match`. |
| `input.txt`: 20 queries; some contain `1. … 2. … 3.` (multi-intent) | Multi-intent split → one `Goal` per symptom. |
| `sample_output.json`: steps style "Navigate to and open Settings." / "Tap on X."; manual action = service centre, deeplink `null` | Mirror this style. (Note: the sample's descriptions break the 5–7 word rule; we follow the written rule.) |
| All 20 queries are in the **Display** domain | The eval set is extended with paraphrases + adversarial/out-of-domain queries. |

## Architecture
```
POST /v1/troubleshoot {query, siis_response?}
  ├─ HOT: normalise → bge-small embed (≈5 ms) → exact/ANN lookup over paraphrase cloud
  │        → Symptom-Signature Guard (component/symptom/polarity) + SIIS-hash check → HIT (≈20–60 ms)
  └─ COLD (on miss):
       ├─ [parallel] Enrichment LLM: canonical query, topic, 8–10 variations
       ├─ [parallel] Extraction LLM: numbered SIIS sentences → goals/actions/steps + source IDs
       ├─ Grounding check (drop unsupported steps) → rules fixer (casing, word counts, URL scrub)
       ├─ Deeplink mapping: hybrid BM25+dense top-k → depth-aware rerank → 1 LLM call chooses IDs
       ├─ Categorise (auto/manual/critical) + disruption ordering (critical last)
       ├─ Pydantic validation (schema.py) → calibrated score → write-back to cache
       └─ meta {latency_ms, cache_hit, model, cost_usd, fallback?}
```

## Repo layout
```
app/        config · schema (given) · data · llm · embed · text (lexicon/signature/rules helpers)
            retrieval · enrich · extract · mapper · rules · cache · pipeline · main (FastAPI) · static/ (demo UI)
scripts/    build_cache.py (warm + results.jsonl) · make_eval.py · bench.py · compliance.py · judge.py · ablation.py · report.py
eval/       heldout_paraphrases.jsonl · adversarial.jsonl · human_paraphrases.jsonl (team-written)
data/       starter assets + cache store
```

## Timeline (today)
| Time | Work |
|---|---|
| Now → +4 h | Core pipeline end-to-end (LLM layer, extraction, mapping, rules, cache, API) |
| +4 → +7 h | Warm cache, results.jsonl, eval sets, bench + compliance + judge + ablation |
| +7 → +9 h | Demo UI, README, Dockerfile, metrics.md |
| 6 PM | **Code freeze** → video + deck |
| 9 PM | Tag `PRISM_GENAI_HACKATHON_Y2026`, submit form |

## Team tasks in parallel (no code needed)
1. **Human paraphrases:** write 3 paraphrases for each of the 20 queries in `eval/human_paraphrases.jsonl`: casual, typo-filled, Hinglish/frustrated. Format: `{"row": "row_2", "text": "..."}`
2. **Deck:** `CollegeName_TeamName_Submission_ppt`: Theme ID 02, title, team, problem, architecture, stack, innovations, results, limitations.
3. **Video script** (≤5 min): see OneTap_Product_Plan.md §7.
