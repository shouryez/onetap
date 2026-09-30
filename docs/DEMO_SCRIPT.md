# Demo Video Script (≤ 5:00)

Setup: `uvicorn app.main:app --port 8000`, open http://localhost:8000 in a browser at full screen, and keep `metrics.md` open in a second tab.
Record with OBS or Xbox Game Bar (Win+Alt+R). Speak slowly; the numbers matter more than the words.

| Time | Screen | Say |
|---|---|---|
| 0:00-0:25 | Title slide | "Support agents spend about 15 minutes turning a vague complaint like *'my screen flickers and goes black'* into steps, and users then still dig through Settings. OneTap does it in milliseconds, and every step is one tap away." |
| 0:25-1:00 | Architecture slide | "Two paths. **Hot path:** a guarded semantic cache, about 10 ms and zero cost. **Cold path:** the LLM extracts steps *only* from the knowledge-base article and has to cite the sentence for each step. Deeplinks are picked from the catalog, never generated, and every rule is enforced in code." |
| 1:00-1:40 | UI: pick article `row_4 Blank or black display`, tick **bypass cache** + **fresh LLM**, click a row_4 chip | Cold path: point at the stage bars (enrichment ∥ extraction, grounding, mapping), the **cost** (~$0.0008), the ordered cards (manual checks first, **critical: Force restart last**) and the "all steps grounded" note. |
| 1:40-2:05 | Untick both boxes, type *"screen went black after a month, can't even turn it on"* | "Same problem, new wording, served from the **cache in ~10 ms for $0**." Point at the similarity and the matched complaint. |
| 2:05-2:35 | Type *"My Wi-Fi keeps turning ON by itself"*, then *"…OFF by itself"* | "Embeddings rate these **0.96 similar**, but they need opposite fixes. Our **Symptom-Signature Guard** checks polarity, symptoms and context, and cuts wrong cache answers from **44% to 10%**." Show the *guard rejected* row. |
| 2:35-3:00 | Row_21 chip (touch lag), fresh | Show the **⚡ Enable Touch sensitivity** button (catalog deeplink + validation check *Touch sensitivity = True*) and the Navigation bar deeplink found by **exact leaf-screen match**, not the parent "Display" menu. |
| 3:00-3:20 | Row_1 chip (email-server article for a display complaint) *or* type "my car won't start" | "When the knowledge base doesn't cover the problem, we don't invent steps. We return **no_match**, as the spec requires." |
| 3:20-3:35 | Hinglish chip "phone screen bahut flicker kar raha hai…" | "It handles Hinglish and typos, which matters for Indian users." |
| 3:35-4:30 | metrics.md | Walk the table: 100% schema / rule compliance, 0 URL leaks, 100% catalog-valid deeplinks · hit P95 vs 300 ms · cold P95 vs 8 s · hit rate on unseen paraphrases ≥ 80% · **ablation**: ours vs full-LLM / hybrid / rules. |
| 4:30-5:00 | Closing slide | "Scaling to 10k+ scenarios: an offline compiler warms the cache, stage outputs are cached separately, and a deeplink-to-plan index means a One UI update recompiles only the affected plans. It's a REST API that is Dockerized and model-agnostic. Thank you." |

## Slide checklist (deck `CollegeName_TeamName_Submission_ppt`)
1. Title: Theme 02 · OneTap · team names
2. Problem in our own words
3. Solution + architecture diagram (README "Architecture")
4. Innovations: grounding with citations · Symptom-Signature Guard · closed-set + exact-leaf deeplinks · multi-intent · hedged LLM layer
5. Tech stack: FastAPI · Groq (gpt-oss-120b / gpt-oss-20b / qwen3.8-27b) · bge-small ONNX (CPU) · NumPy BM25 + dense · Pydantic · Docker
6. Results: metrics.md tables (compliance, latency, cache, ablation)
7. Limitations + next steps (metrics.md §6)
8. Demo video link + GitHub link
