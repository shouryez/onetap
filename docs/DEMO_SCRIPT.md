# OneTap Demo Video: Technical Recording Script (≈ 4:55, hard limit 5:00)

~720 spoken words. Speak at a steady, clear pace; trim AI waiting time in editing.

## A. Setup (10 minutes before recording)
1. Terminal in `Desktop\samsung\onetap`:
   ```bash
   git restore data/cache_store.json
   python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```
   Wait for `Application startup complete`.
2. Chrome → `http://127.0.0.1:8000` → **F11** → **Ctrl + minus** to 80–90% so the phone AND the right panel fit.
3. **◐** → light theme. On the phone: tick **fresh AI**, leave **bypass cache** unticked, keep **catalog** ticked.
4. PowerPoint deck in slideshow (**F5**), ready on slide 1. Switch with **Alt + Tab**.
5. Recorder: **Win + Alt + R** or OBS. Test the mic.
6. Do **not** click scenario cards before the real take (it fills the cache). If you practise, redo step 1.

---

## B. Timeline

### 0:00 – 0:15 · Slide 1 (title)
**Do:** show the slide.
**Say:** "Hi, we're Team Aloo Paratha from MSRIT. This is OneTap, a Smart Guided Troubleshooting Engine for Theme 2: a REST API that turns a vague device complaint into a verified, ordered troubleshooting plan, with every settings step one tap away."

### 0:15 – 0:40 · Slide 2 (problem)
**Do:** point at "15 min", then the four reasons, then the orange "Our framing" box.
**Say:** "Today an agent spends about fifteen minutes per complaint: decoding the customer's words, finding the SIIS article, rewriting it as steps and dictating settings paths. We treated this as a compiler problem. The input is the complaint plus a reference article; the output is Samsung's exact JSON contract: goal, ordered actions, steps and deeplinks, with latency, cache-hit and cost metadata."

### 0:40 – 1:15 · Slide 4 (architecture)
**Do:** trace the green row, then the orange row, then point at the "write-back" arrow.
**Say:** "There are two paths. The hot path cleans the text, including typos and Hinglish, and converts it into a 384-number meaning vector with a small bge-small embedding model that runs on the CPU in about seven milliseconds. We compare it with every stored rewording of past problems; if cosine similarity is at least 0.87 and our guard agrees, we return the saved plan with no AI call. On a miss, the cold path runs two LLM calls in parallel on Groq: one writes ten rewordings for future matching, the other extracts steps from the article. Then come grounding, categorisation and deeplink resolution, and a Pydantic schema gate. The result is written back, so the next similar question is instant."

### 1:15 – 1:55 · Chrome → card "Enable the right switch" (ONE-TAP TOGGLE)
**Do:** Alt+Tab to Chrome. Click the card. While it thinks, point at the bubble. When done, point at the right panel: the narration, the **timing chart** (orange = AI), then the **Grounding check** section. Scroll the phone briefly: green AUTO at the top, red CRITICAL at the bottom.
**Say:** "Here's the live system with Samsung's touchscreen article: 'touch stopped working after I put on a screen protector'. It's new, so the full pipeline runs. To stop hallucination, we split the article into numbered sentences, and the model must cite the sentence behind every step. Our code then checks that the step's key words really appear in that sentence, and drops invented buttons, outcome sentences and contradictory steps. Actions are then categorised: auto settings first, manual checks next, and critical ones like restart or factory reset always last."

### 1:55 – 2:15 · Tap ⚡ Enable Touch sensitivity
**Do:** click the orange button → Settings screen slides in, the switch turns **on**, the green **verified** line appears → click **‹ Back to OneTap**.
**Say:** "Each settings step carries a deeplink from Samsung's 577-entry catalog. This is an 'onURL' entry, so it switches the setting on, and its validation deeplink checks that 'Touch sensitivity equals True' afterwards."

### 2:15 – 2:40 · Right panel → Deeplink resolution
**Do:** point at the green "exact screen match" tags, then at an orange "AI picked from candidates" row if present.
**Say:** "The model never writes a link. First we try an exact match on the deepest screen named in the steps. Otherwise BM25 keyword search and embedding search are fused, a reranker prefers the leaf screen and the right on/off direction, and a small model picks one catalog ID from a shortlist. Code copies the link verbatim, so every link is guaranteed real: 95.8% exact on our ground-truth test, versus 62.5% when the whole catalog goes into one prompt."

### 2:40 – 2:55 · Card "…or the opposite one" (DIRECTION)
**Do:** click; point at **Disable Touch Sensitivity** on the phone.
**Say:** "Same article, opposite complaint: phantom touches and no screen guard. The conditional instruction flips, and now it maps to the 'offURL' twin. It reads the complaint, not just the article."

### 2:55 – 3:15 · Card "Instant answer" (CACHE HIT)
**Do:** click; point at CACHE HIT, the latency, $0.0000, and the gauge needle past the 0.87 line.
**Say:** "Now a reworded known problem. Each stored plan keeps about ten paraphrases as vectors, so this new wording scores 0.88 against one of them. That's a cache hit in milliseconds: no LLM, zero cost. On 97 unseen rewordings written by a different model, 82.5% hit the cache, with a P95 lookup of 8.8 milliseconds."

### 3:15 – 3:45 · Card "Look-alike, different fix" (GUARD)
**Do:** click; point at the struck-through cached complaint and the red **context mismatch** tag.
**Say:** "Pure similarity is dangerous. 'Wi-Fi keeps turning on' and 'turning off' score 0.96 but need opposite fixes. So our Symptom-Signature Guard extracts on/off polarity, the symptom set and the trigger context, like charging, camera, Gmail or browsing, and checks the source article. Here, a 0.88 match is rejected because it's browsing, not email. On adversarial look-alikes this cut wrong cache answers from 44% to 10% at the same threshold."

### 3:45 – 4:00 · Cards "Three problems" then "Refuses to guess"
**Do:** click MULTI-INTENT → show two plan titles; then click NO MATCH → point at "No verified fix found".
**Say:** "Complaints with several problems are split into separate goals. And if the article doesn't address the complaint, a relevance gate returns an empty plan with a 'no_match' fallback, exactly as the spec requires, instead of guessing."

### 4:00 – 4:15 · Slide 8 (rules in code)
**Do:** Alt+Tab → go to slide 8. Point at the table, then the AUTO → MANUAL → CRITICAL blocks.
**Say:** "Every format rule is enforced in code, not just requested in the prompt: the goal template, 2-to-3-word titles, 5-to-7-word 'It will' descriptions, URL scrubbing, catalog-only links, and the provided schema as a hard gate."

### 4:15 – 4:40 · Slides 10 → 11 → 12 (results + ablation)
**Do:** about 8 s per slide.
**Say:** "On all twenty scenarios: 100% schema and rule compliance, zero URL leaks, 100% real deeplinks. P95 latency is 10 milliseconds for reworded known problems and 3.2 seconds cold, against targets of 300 milliseconds and 8 seconds, at about $0.0008 per new question. The ablation shows each design choice beats its alternative."

### 4:40 – 4:55 · Slide 16 (scale), then slide 18 (thank you)
**Do:** show slide 16 for ~6 s, then slide 18.
**Say:** "To scale to ten thousand scenarios, plans compile offline, and user feedback evicts plans that don't help. OneTap: describe it in your own words, get a verified fix, one tap away. Thank you."

---

## C. If something goes wrong
| Problem | Fix |
|---|---|
| A "new question" card shows CACHE HIT | It was run before: redo setup step 1, reload, restart the take. |
| "AI provider is busy" | Wait 30 s and click again, or cut it in editing. |
| A question takes > 10 s | Keep talking; trim the wait in editing. |
| Running over 5:00 | Cut the "Three problems" card first, then shorten the slide 8 line. |

## D. Words to pronounce comfortably
* **bge-small**: "B-G-E small" · **cosine**: "co-sign" · **Pydantic**: "pie-DAN-tic" · **BM25**: "B-M twenty-five"
* **Groq**: "grok" · **deeplink**: "deep link" · **τ / tau**: "tau" (rhymes with "cow"), or just say "threshold"
