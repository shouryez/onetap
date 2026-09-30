"""Compliance audit of results.jsonl + assembles metrics.md (Appendix C template) from eval/*.json."""
import json
import platform
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config  # noqa: E402
from app.retrieval import catalog  # noqa: E402
from app.rules import check_goal  # noqa: E402
from app.schema import ContextDeeplinkResponse  # noqa: E402
from app.text import has_url  # noqa: E402

EVAL = config.ROOT / "eval"


def jload(name):
    p = EVAL / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def compliance(results_path: Path) -> dict:
    lines = [json.loads(l) for l in results_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    uris = catalog().uris
    n = len(lines)
    schema_ok = goals = goals_ok = url_leaks = dl_total = dl_valid = auto = auto_dl = auto_real = 0
    var_ok = 0
    errors = {}
    for o in lines:
        try:
            ContextDeeplinkResponse(**o["response"])
            schema_ok += 1
        except Exception:
            pass
        var_ok += 8 <= len(o.get("query_variations", [])) <= 10
        blob = json.dumps(o["response"], ensure_ascii=False)
        for g in o["response"]["contexts"]:
            goals += 1
            errs = check_goal(g, uris)
            goals_ok += not errs
            for e in errs:
                errors[e] = errors.get(e, 0) + 1
            for a in g["actions"]:
                for sg in a["stepGroups"]:
                    for s in sg["steps"] + [a["actionName"], a["description"], g["title"], g["goal"]]:
                        url_leaks += has_url(s)
                    dl = sg.get("actionableDeeplink")
                    if dl:
                        dl_total += 1
                        dl_valid += dl["deeplink"] in uris
                    if a["category"] == "auto":
                        auto += 1
                        auto_dl += bool(dl and dl["deeplink"] in uris)
                        auto_real += bool(dl and dl["deeplink"] in uris and "dummy" not in dl["deeplink"])
        assert "```" not in blob
    return {"lines": n, "schema_valid_pct": 100 * schema_ok / n, "goals": goals,
            "rule_compliant_pct": 100 * goals_ok / max(1, goals), "rule_errors": errors, "url_leaks": url_leaks,
            "deeplink_validity_pct": 100 * dl_valid / max(1, dl_total), "deeplinks": dl_total,
            "auto_actions": auto, "auto_with_dl_pct": 100 * auto_dl / max(1, auto),
            "auto_with_real_catalog_dl_pct": 100 * auto_real / max(1, auto),
            "variations_8_10_pct": 100 * var_ok / n,
            "no_match": sum(1 for o in lines if o["meta"].get("fallback") == "no_match"),
            "multi_goal": sum(1 for o in lines if len(o["response"]["contexts"]) > 1),
            "cold_cost_avg": sum(o["meta"]["cost_usd"] for o in lines) / n}


def f(x, d=1, suf=""):
    return "n/a" if x is None else f"{x:.{d}f}{suf}"


def main():
    c = compliance(config.ROOT / "results.jsonl")
    cache, bench, abl, judge = jload("cache_eval.json"), jload("bench.json"), jload("ablation.json"), jload("judge.json")
    ours_c = cache.get("ours_with_siis", {})
    ng = cache.get("no_guard_query_only", {})
    b_ex, b_pa, b_cold = bench.get("cache_hit_exact", {}), bench.get("cache_hit_paraphrase", {}), bench.get("cold", {})
    steps = [j["step_score"] for j in judge] if judge else []
    dls = [s for j in judge for s in j["dl_scores"]] if judge else []
    md = f"""# System Performance Metrics & Evaluation Report

**Model(s):** Groq `{config.LLM_MODEL}` (Phase 1 extraction) · `{config.LLM_ENRICH_MODEL}` (enrichment, repair) · `{config.LLM_FAST_MODEL}` (closed-set deeplink choice)
**Embeddings:** `{config.EMBED_MODEL}` (ONNX via fastembed, CPU, 384-d)
**Environment:** {platform.system()} {platform.release()} · Python {platform.python_version()} · CPU-only · single process (uvicorn)
**Data:** 20 provided scenarios (`siis_responses.json`), 577-entry deeplink catalog, 97 held-out paraphrases,
40 near-miss + 10 out-of-domain adversarial queries (`eval/`)

---

## 1. Schema & Rule Compliance
Evaluated on `results.jsonl` (all {c['lines']} provided scenarios, {c['goals']} goals).

| Metric | Target | Measured Value |
| :--- | :--- | :--- |
| Schema-valid output lines | >= 99% | {f(c['schema_valid_pct'])}% |
| Rule compliance (Goal / Title / Description syntax) | >= 95% | {f(c['rule_compliant_pct'])}% |
| Absolute URL leaks | 0 | {c['url_leaks']} |
| Deeplink catalog validity (exact URI match) | 100% | {f(c['deeplink_validity_pct'])}% ({c['deeplinks']} deeplinks) |
| Auto actions carrying valid actionable deeplink | >= 90% | {f(c['auto_with_dl_pct'])}% ({f(c['auto_with_real_catalog_dl_pct'])}% dedicated catalog entry, rest `dummy_positive`) |
| `query_variations` with 8-10 items | 100% | {f(c['variations_8_10_pct'])}% |

Honest `no_match` responses (reference article does not address the complaint): {c['no_match']} / {c['lines']}.
Multi-intent complaints answered with more than one Goal: {c['multi_goal']}.

---

## 2. Accuracy Benchmarks
LLM-as-judge (Gemini Flash family, a different model family from the generator, strict rubric, reference article in context) over the {len(judge) or 'n/a'} provided scenarios.

| Evaluation Metric | Scale / Anchor | Score |
| :--- | :--- | :--- |
| Step accuracy (completeness, correctness, ordering) | 0.0 - 3.0 | {f(sum(steps) / len(steps), 2) if steps else 'n/a'} |
| Deeplink relevance (exact target screen vs. parent menu) | 0.0 - 2.0 | {f(sum(dls) / len(dls), 2) if dls else 'n/a'} (n={len(dls)}) |

---

## 3. Latency Benchmarks (N >= 30 requests per path)
Client-side wall clock over HTTP on localhost (server-side `meta.latency_ms` in brackets).

| Execution Path | Target (P95) | P50 (ms) | P95 (ms) |
| :--- | :--- | :--- | :--- |
| Cache hit - exact query match (N={b_ex.get('n', 'n/a')}) | <= 300 ms | {f(b_ex.get('p50_ms'))} [{f(b_ex.get('server_p50_ms'), 0)}] | {f(b_ex.get('p95_ms'))} [{f(b_ex.get('server_p95_ms'), 0)}] |
| Cache hit - unseen semantic paraphrase (N={b_pa.get('n', 'n/a')}) | <= 300 ms | {f(b_pa.get('p50_ms'))} [{f(b_pa.get('server_p50_ms'), 0)}] | {f(b_pa.get('p95_ms'))} [{f(b_pa.get('server_p95_ms'), 0)}] |
| Cold query - full pipeline extraction & mapping (N={b_cold.get('n', 'n/a')}) | <= 8000 ms | {f(b_cold.get('p50_ms'), 0)} [{f(b_cold.get('server_p50_ms'), 0)}] | {f(b_cold.get('p95_ms'), 0)} [{f(b_cold.get('server_p95_ms'), 0)}] |

Cold requests were spaced 18 s apart (provider tokens-per-minute limit), so each opened a new HTTP connection to
`localhost`; on Windows that first tries IPv6 and adds ~2 s per new connection (measured: 2297 ms vs 218 ms via
`127.0.0.1`). The bracketed server-side numbers are the pipeline itself. `scripts/bench.py` now defaults to `127.0.0.1`.

Cache lookup alone (embedding + matrix search + guard, in-process): P50 {ours_c.get('lookup_ms_p50', 'n/a')} ms · P95 {ours_c.get('lookup_ms_p95', 'n/a')} ms.

---

## 4. Operational Cost & Cache Efficacy

| Metric Item | Target | Measured Value |
| :--- | :--- | :--- |
| Cold query average inference cost | Tracked | ${f(b_cold.get('avg_cost_usd') or c['cold_cost_avg'], 5)} |
| Cache hit inference cost | $0.00 | $0.00 |
| Semantic cache hit rate (on unseen paraphrases) | >= 80% | {f(100 * ours_c.get('hit_rate', 0))}% (correct-article hits {f(100 * ours_c.get('correct_hit_rate', 0))}%) |
| False-hit rate on adversarial near-miss / out-of-domain queries | (ours) | {f(100 * ours_c.get('false_hit_rate', 0))}% (without Symptom-Signature Guard: {f(100 * ng.get('false_hit_rate', 0))}%) |
| Cost derivation method | - | (prompt tokens x input rate + completion tokens x output rate) per model, summed per request |

Threshold sweep (query-only lookups, guard on):

| tau | hit rate | false-hit rate |
| :--- | :--- | :--- |
""" + "\n".join(f"| {s['tau']} | {100 * s['hit_rate']:.1f}% | {100 * s['false_hit_rate']:.1f}% |"
                for s in cache.get("threshold_sweep_query_only", [])) + f"""

Operating point: tau = {config.CACHE_TAU} (max hit rate subject to hit >= 80% and false hits <= 10%).

---

## 5. Architectural Ablation Analysis
Only the deeplink stage varies (identical extraction), mapping LLM calls made fresh. Latency / cost = mapping stage per query.

| Architecture Variant | Step Accuracy | Deeplink relevance (0-2) | Mapping latency P95 | Cost / Query | Key Observations |
| :--- | :--- | :--- | :--- | :--- | :--- |
"""
    names = {"full_llm": "Baseline: Full LLM Deeplink Mapping (whole catalog in prompt)",
             "hybrid_only": "Variant A: Hybrid BM25 + Dense Embedding Retrieval (top-1)",
             "rules_only": "Variant B: Pure Rules-Based Deeplink Mapping (BM25 keyword)",
             "ours": "**OneTap: exact-leaf match + hybrid + depth rerank + closed-set LLM**"}
    notes = {"full_llm": "Large prompt per action; picks parent menus; slowest/most expensive",
             "hybrid_only": "Fast, free; confuses on/off twins and parent screens",
             "rules_only": "Fast, free; brittle to wording, low coverage",
             "ours": "Deterministic when the leaf screen is unambiguous; LLM only chooses among candidates"}
    step_ours = abl.get("ours", {}).get("step_accuracy_avg_0_3")
    for k in ("full_llm", "hybrid_only", "rules_only", "ours"):
        v = abl.get(k)
        if not v:
            continue
        md += (f"| {names[k]} | {f(step_ours, 2) if step_ours is not None else 'n/a'} | "
               f"{f(v['deeplink_relevance_avg_0_2'], 2)} (n={v['n_deeplinks']}, {v['real_catalog_deeplinks']} catalog) | "
               f"{f(v['mapping_latency_p95_ms'], 0)} ms | ${f(v['mapping_cost_per_query_usd'], 5)} | {notes[k]} |\n")
    dle = jload("deeplink_eval.json")
    if dle:
        md += """
**Ground-truth deeplink resolution benchmark** (`scripts/eval_deeplinks.py`): 24 catalog targets (open-page / enable /
disable, stratified). An LLM wrote a realistic action for each without the catalog wording; every variant must recover
the exact catalog entry.

| Variant | Accuracy@1 (exact entry) | Right screen, wrong on/off twin | No deeplink | Latency P50 / P95 | Cost / action |
| :--- | :--- | :--- | :--- | :--- | :--- |
"""
        for k in ("full_llm", "hybrid_only", "rules_only", "ours"):
            v = dle.get(k)
            if v:
                md += (f"| {names[k]} | {100 * v['accuracy_at_1']:.1f}% | {100 * v['same_screen_wrong_direction']:.1f}% | "
                       f"{100 * v['no_deeplink']:.1f}% | {v['latency_p50_ms']:.0f} / {v['latency_p95_ms']:.0f} ms | "
                       f"${v['cost_per_action_usd']:.5f} |\n")
    md += f"""
Symptom-Signature Guard ablation (same tau): hit rate {f(100 * ng.get('hit_rate', 0))}% -> {f(100 * ours_c.get('hit_rate', 0))}%,
false hits {f(100 * ng.get('false_hit_rate', 0))}% -> {f(100 * ours_c.get('false_hit_rate', 0))}%.

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
"""
    (config.ROOT / "metrics.md").write_text(md, encoding="utf-8")
    print(json.dumps(c, indent=1))
    print("wrote metrics.md")


if __name__ == "__main__":
    main()
