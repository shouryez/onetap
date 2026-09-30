// Builds MSRIT_AlooParatha_Submission_ppt.pptx  (node deck/build_deck.js)
const path = require("path");
const fs = require("fs");
const pptxgen = require("pptxgenjs");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const sharp = require("sharp");
const fa = require("react-icons/fa");

const ROOT = path.resolve(__dirname, "..");
const IMG = (f) => path.join(ROOT, "docs", "img", f);
const OUT = path.join(ROOT, "MSRIT_AlooParatha_Submission_ppt.pptx");

// ---------------------------------------------------------------- design tokens (same identity as the web UI)
const C = {
  ink: "17140F", ink2: "4A453C", muted: "8A8375", paper: "F7F5F0", paper2: "EBE6DA", rule: "D9D2C3", white: "FFFFFF",
  signal: "FF5A1F", signalSoft: "FFE4D6", signalInk: "B93A0B", ok: "1D7A52", okSoft: "DCEFE4",
  man: "2F47D6", manSoft: "E2E6FB", crit: "B8321A", critSoft: "F7E0DA", darkText: "F4F1EA", darkMuted: "A8A091",
};
const F = { head: "Cambria", body: "Calibri", mono: "Courier New" };
const TOTAL = 18;

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9"; // 10 x 5.625 in
pres.author = "Team Aloo Paratha (MSRIT)";
pres.title = "OneTap - Smart Guided Troubleshooting Engine";

async function icon(Comp, color = "#FFFFFF", size = 256) {
  const svg = renderToStaticMarkup(React.createElement(Comp, { color, size }));
  const buf = await sharp(Buffer.from(svg)).png().toBuffer();
  return "image/png;base64," + buf.toString("base64");
}

// ---------------------------------------------------------------- helpers
function txt(slide, text, o) { slide.addText(text, { isTextBox: true, margin: 0, fontFace: F.body, color: C.ink, valign: "top", ...o }); }

function frame(slide, n, kicker, title, opts = {}) {
  slide.background = { color: C.paper };
  slide.addShape(pres.shapes.OVAL, { x: 0.5, y: 0.38, w: 0.09, h: 0.09, fill: { color: C.signal }, line: { type: "none" } });
  txt(slide, kicker, { x: 0.68, y: 0.3, w: 8.5, h: 0.25, fontFace: F.mono, fontSize: 9, color: C.muted, charSpacing: 2 });
  txt(slide, title, { x: 0.5, y: 0.58, w: 9, h: opts.titleH || 0.62, fontFace: F.head, fontSize: opts.titleSize || 26, bold: true, color: C.ink, valign: "top" });
  txt(slide, `OneTap  ·  Team Aloo Paratha  ·  ${String(n).padStart(2, "0")} / ${TOTAL}`,
    { x: 5.5, y: 5.28, w: 4, h: 0.2, fontFace: F.mono, fontSize: 7.5, color: C.muted, align: "right" });
}

function card(slide, x, y, w, h, fill = C.white, line = C.rule) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, fill: { color: fill }, line: { color: line, width: 0.75 }, rectRadius: 0.08 });
}

function pill(slide, x, y, w, text, fill, color, size = 8) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h: 0.24, fill: { color: fill }, line: { type: "none" }, rectRadius: 0.05 });
  txt(slide, text, { x, y, w, h: 0.24, fontFace: F.mono, fontSize: size, color, align: "center", valign: "middle", bold: true });
}

function numDot(slide, x, y, n, fill = C.ink, color = C.white, d = 0.32) {
  slide.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: fill }, line: { type: "none" } });
  txt(slide, String(n), { x, y, w: d, h: d, fontFace: F.mono, fontSize: 10, bold: true, color, align: "center", valign: "middle" });
}

function arrow(slide, x1, y1, x2, y2, color = C.ink2, dash) {
  slide.addShape(pres.shapes.LINE, { x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.abs(x2 - x1) || 0.001, h: Math.abs(y2 - y1) || 0.001,
    flipH: x2 < x1, flipV: y2 < y1, line: { color, width: 1.25, endArrowType: "triangle", dashType: dash || "solid" } });
}

function stat(slide, x, y, w, value, label, sub, color = C.ink, vsize = 30) {
  txt(slide, value, { x, y, w, h: 0.55, fontFace: F.mono, fontSize: vsize, bold: true, color, valign: "bottom" });
  txt(slide, label, { x, y: y + 0.58, w, h: 0.4, fontSize: 11, color: C.ink, bold: true, valign: "top" });
  if (sub) txt(slide, sub, { x, y: y + 0.9, w, h: 0.4, fontSize: 9.5, color: C.muted, valign: "top" });
}

(async () => {
  const ic = {
    shield: await icon(fa.FaShieldAlt), quote: await icon(fa.FaQuoteRight), link: await icon(fa.FaLink),
    book: await icon(fa.FaBook), sync: await icon(fa.FaSyncAlt), random: await icon(fa.FaRandom),
    mic: await icon(fa.FaMicrophone), list: await icon(fa.FaListOl), paste: await icon(fa.FaPaste),
    hand: await icon(fa.FaHandPointer), thumbs: await icon(fa.FaThumbsUp), eye: await icon(fa.FaEye),
    bolt: await icon(fa.FaBolt, "#FF5A1F"), check: await icon(fa.FaCheck, "#1D7A52"), times: await icon(fa.FaTimes, "#B8321A"),
  };

  // ============================================================ 1. TITLE
  {
    const s = pres.addSlide();
    s.background = { color: C.ink };
    s.addShape(pres.shapes.OVAL, { x: 0.5, y: 0.47, w: 0.1, h: 0.1, fill: { color: C.signal }, line: { type: "none" } });
    txt(s, "PRISM GENAI HACKATHON 2026  ·  THEME 02", { x: 0.7, y: 0.38, w: 5.5, h: 0.28, fontFace: F.mono, fontSize: 9, color: C.darkMuted, charSpacing: 2 });
    txt(s, [{ text: "One", options: { bold: true } }, { text: "Tap", options: { italic: true } }],
      { x: 0.5, y: 1.05, w: 5.4, h: 1.15, fontFace: F.head, fontSize: 66, color: C.darkText, valign: "bottom" });
    txt(s, "Smart Guided Troubleshooting Engine", { x: 0.5, y: 2.25, w: 5.6, h: 0.45, fontFace: F.head, fontSize: 21, italic: true, color: C.darkText });
    txt(s, "A vague complaint goes in; a verified, ordered fix plan comes out, and every Settings step is one tap away.",
      { x: 0.5, y: 2.78, w: 5.2, h: 0.6, fontSize: 13, color: "C9C1B2" });
    const st = [["~10 ms", "answer from the guarded cache"], ["~3 s", "full grounded pipeline"], ["$0.0008", "per new complaint"]];
    st.forEach(([v, l], i) => {
      txt(s, v, { x: 0.5 + i * 1.8, y: 3.6, w: 1.7, h: 0.42, fontFace: F.mono, fontSize: 20, bold: true, color: C.signal });
      txt(s, l, { x: 0.5 + i * 1.8, y: 4.02, w: 1.65, h: 0.4, fontSize: 9.5, color: C.darkMuted });
    });
    txt(s, "Shourya Chouhan  ·  Shreya Singh Chouhan  ·  Yash Mittal  ·  Vrunda Hatwar",
      { x: 0.5, y: 4.62, w: 6, h: 0.28, fontSize: 11.5, bold: true, color: C.darkText });
    txt(s, "Team Aloo Paratha  ·  M S Ramaiah Institute of Technology (MSRIT), Bengaluru  ·  Theme ID 02",
      { x: 0.5, y: 4.95, w: 6, h: 0.3, fontSize: 10, color: C.darkMuted });
    // phone mock
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 6.55, y: 0.45, w: 2.85, h: 4.75, fill: { color: "0B0A09" }, line: { color: "2A2622", width: 1 }, rectRadius: 0.35 });
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 6.67, y: 0.57, w: 2.61, h: 4.51, fill: { color: C.paper }, line: { type: "none" }, rectRadius: 0.28 });
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 7.62, y: 0.66, w: 0.7, h: 0.17, fill: { color: "000000" }, line: { type: "none" }, rectRadius: 0.08 });
    txt(s, [{ text: "One", options: { bold: true } }, { text: "Tap", options: { italic: true } }], { x: 6.85, y: 0.95, w: 1.4, h: 0.3, fontFace: F.head, fontSize: 14 });
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 7.35, y: 1.32, w: 1.8, h: 0.52, fill: { color: C.ink }, line: { type: "none" }, rectRadius: 0.1 });
    txt(s, "screen keeps blinking then goes black when I unfold it", { x: 7.43, y: 1.35, w: 1.66, h: 0.46, fontSize: 7.5, color: C.darkText, valign: "middle" });
    txt(s, "Screen flicker fix", { x: 6.85, y: 1.98, w: 2.3, h: 0.28, fontFace: F.head, fontSize: 13, bold: true });
    card(s, 6.82, 2.3, 2.31, 1.05);
    txt(s, "Adjust Navigation Bar", { x: 6.95, y: 2.36, w: 1.6, h: 0.22, fontSize: 8.5, bold: true });
    pill(s, 8.52, 2.37, 0.5, "AUTO", C.okSoft, C.ok, 6);
    txt(s, "1  Navigate to and open Settings.\n2  Tap Display.\n3  Tap Navigation bar.", { x: 6.95, y: 2.6, w: 2.1, h: 0.5, fontSize: 7, color: C.ink2 });
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 6.92, y: 3.08, w: 2.1, h: 0.22, fill: { color: C.signal }, line: { type: "none" }, rectRadius: 0.05 });
    txt(s, "⚡ View Navigation bar        one tap →", { x: 6.98, y: 3.08, w: 2.0, h: 0.22, fontSize: 7, bold: true, color: C.white, valign: "middle" });
    card(s, 6.82, 3.45, 2.31, 0.62);
    txt(s, "Force Restart", { x: 6.95, y: 3.5, w: 1.5, h: 0.22, fontSize: 8.5, bold: true });
    pill(s, 8.37, 3.51, 0.65, "CRITICAL", C.critSoft, C.crit, 6);
    txt(s, "always ordered last", { x: 6.95, y: 3.75, w: 1.8, h: 0.2, fontSize: 7, italic: true, color: C.muted });
    txt(s, "Did this fix it?   👍   👎", { x: 6.9, y: 4.25, w: 2.2, h: 0.25, fontSize: 8, color: C.ink2 });
    s.addNotes("Hi, we're Team Aloo Paratha from MSRIT. Our Theme 02 project is OneTap. You describe a phone problem in your own words and get back a verified, ordered troubleshooting plan, where each Settings step is a one-tap deeplink. Known problems come back from a guarded semantic cache in about 10 milliseconds. New problems go through a grounded AI pipeline in about 3 seconds, for less than a tenth of a cent.");
  }

  // ============================================================ 2. PROBLEM
  {
    const s = pres.addSlide();
    frame(s, 2, "01 · THE PROBLEM IN OUR OWN WORDS", "Customers describe symptoms, not fixes");
    txt(s, "15 min", { x: 0.5, y: 1.35, w: 3.6, h: 0.8, fontFace: F.mono, fontSize: 50, bold: true, color: C.signal });
    txt(s, "of manual agent work per complaint scenario, repeated across millions of support calls. Then the user still hunts through Settings.",
      { x: 0.5, y: 2.2, w: 3.6, h: 0.75, fontSize: 11.5, color: C.ink2 });
    const quotes = ["“Screen flickers and the battery dies fast”", "“My phone got slow after the update”", "“Swipe gestures go the wrong way after installing an app”"];
    quotes.forEach((q, i) => {
      card(s, 0.5, 3.1 + i * 0.6, 3.6, 0.5, C.white);
      txt(s, q, { x: 0.65, y: 3.1 + i * 0.6, w: 3.4, h: 0.5, fontFace: F.head, italic: true, fontSize: 11, color: C.ink, valign: "middle" });
    });
    txt(s, "Why it's hard", { x: 4.7, y: 1.35, w: 4.5, h: 0.35, fontFace: F.head, fontSize: 16, bold: true });
    const rows = [
      ["Vague, colloquial language", "“blinking”, “goes dark”, typos, Hinglish: none of it matches support-article wording."],
      ["Several problems in one message", "Flicker + battery drain need different fixes, and a single answer gets both wrong."],
      ["Fixes hide deep in Settings", "Settings › Display › Navigation bar: users give up before they reach the switch."],
      ["The reference may not fit", "The paired article can be about a different fault, and guessing there is dangerous."],
    ];
    rows.forEach(([h, d], i) => {
      const y = 1.82 + i * 0.66;
      numDot(s, 4.7, y + 0.02, i + 1);
      txt(s, h, { x: 5.15, y, w: 4.3, h: 0.25, fontSize: 12, bold: true });
      txt(s, d, { x: 5.15, y: y + 0.26, w: 4.3, h: 0.36, fontSize: 10, color: C.ink2 });
    });
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 4.7, y: 4.5, w: 4.8, h: 0.55, fill: { color: C.signalSoft }, line: { type: "none" }, rectRadius: 0.08 });
    txt(s, [{ text: "Our framing: ", options: { bold: true } }, { text: "a compiler. Complaint + knowledge article → validated, deeplinked JSON plan, and every rule is checked by code." }],
      { x: 4.85, y: 4.5, w: 4.55, h: 0.55, fontSize: 10.5, color: C.signalInk, valign: "middle" });
    s.addNotes("Today an agent reads a vague complaint, finds a knowledge-base article, rewrites the steps and dictates Settings paths. That takes about 15 minutes per scenario, across millions of calls. Four things make it hard: vague language, several problems in one message, fixes buried deep in Settings, and reference articles that sometimes don't even match the fault. We treated it as a compiler problem: complaint plus article in, validated deeplinked JSON out.");
  }

  // ============================================================ 3. WHAT ONETAP DOES
  {
    const s = pres.addSlide();
    frame(s, 3, "02 · WHAT ONETAP DOES", "One call: vague complaint in, one-tap plan out");
    // IN
    card(s, 0.5, 1.4, 2.6, 2.7);
    pill(s, 0.65, 1.52, 0.55, "IN", C.paper2, C.ink2);
    txt(s, "POST /v1/troubleshoot", { x: 0.65, y: 1.85, w: 2.4, h: 0.25, fontFace: F.mono, fontSize: 9, color: C.muted });
    txt(s, "“my screen keeps blinking and goes black when I unfold it”", { x: 0.65, y: 2.15, w: 2.3, h: 0.9, fontFace: F.head, italic: true, fontSize: 13 });
    txt(s, "+ optional SIIS article (or any pasted help text)", { x: 0.65, y: 3.2, w: 2.3, h: 0.6, fontSize: 10, color: C.ink2 });
    arrow(s, 3.15, 2.75, 3.55, 2.75, C.ink);
    // ENGINE
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 3.6, y: 1.4, w: 2.4, h: 2.7, fill: { color: C.ink }, line: { type: "none" }, rectRadius: 0.1 });
    txt(s, [{ text: "One", options: { bold: true } }, { text: "Tap", options: { italic: true } }], { x: 3.75, y: 1.55, w: 2, h: 0.4, fontFace: F.head, fontSize: 20, color: C.darkText });
    [["Guarded semantic cache", C.okSoft, C.ok], ["Grounded AI extraction", C.signalSoft, C.signalInk], ["Closed-set deeplinks", C.manSoft, C.man], ["Rules enforced in code", C.paper2, C.ink]]
      .forEach(([t, f, c], i) => pill(s, 3.78, 2.1 + i * 0.44, 2.05, t, f, c, 8));
    arrow(s, 6.05, 2.75, 6.45, 2.75, C.ink);
    // OUT
    card(s, 6.5, 1.4, 3.0, 2.7);
    pill(s, 6.65, 1.52, 0.6, "OUT", C.paper2, C.ink2);
    txt(s, '{ "goal": "Follow these steps to\n   perform this Screen Flicker\n   Troubleshooting",\n  "title": "Screen flicker fix",\n  "actions": [ { "category": "auto",\n    "stepGroups": [ { "steps": [...],\n      "actionableDeeplink":\n        "voiceassist://masked/act/…" } ] } ],\n  "meta": { "latency_ms": 9,\n            "cache_hit": true, "cost_usd": 0 } }',
      { x: 6.65, y: 1.85, w: 2.8, h: 2.2, fontFace: F.mono, fontSize: 7.5, color: C.ink2 });
    const promises = ["Every step cited from the article", "Links copied from the catalog, never generated", "Safe fixes first, destructive last", "No source → honest no_match"];
    promises.forEach((p, i) => {
      card(s, 0.5 + i * 2.3, 4.35, 2.15, 0.62, C.white);
      s.addImage({ data: ic.check, x: 0.62 + i * 2.3, y: 4.53, w: 0.2, h: 0.2 });
      txt(s, p, { x: 0.9 + i * 2.3, y: 4.35, w: 1.7, h: 0.62, fontSize: 9.5, bold: true, valign: "middle" });
    });
    s.addNotes("The whole product is one REST call. In goes the customer's words, plus the SIIS article if there is one. Out comes the exact JSON contract from the problem statement: goal, title, ordered actions, steps and deeplinks, with latency, cache-hit and cost metadata. Four promises hold for every response, shown along the bottom.");
  }

  // ============================================================ 4. ARCHITECTURE
  {
    const s = pres.addSlide();
    frame(s, 4, "03 · ARCHITECTURE", "Two paths: remember fast, reason carefully");
    const lane = (y, label, fill, color, boxes, llmSet) => {
      pill(s, 0.5, y - 0.36, 2.6, label, fill, color, 8);
      boxes.forEach((b, i) => {
        const x = 0.5 + i * 1.84, llm = llmSet.includes(i);
        s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: 1.6, h: 0.8, fill: { color: llm ? C.signalSoft : C.white }, line: { color: llm ? C.signal : C.ink, width: 1 }, rectRadius: 0.08 });
        txt(s, b[0], { x: x + 0.08, y: y + 0.06, w: 1.44, h: 0.3, fontSize: 9.5, bold: true, color: llm ? C.signalInk : C.ink });
        txt(s, b[1], { x: x + 0.08, y: y + 0.34, w: 1.44, h: 0.42, fontSize: 8, color: C.ink2 });
        if (i < boxes.length - 1) arrow(s, x + 1.62, y + 0.4, x + 1.82, y + 0.4, C.ink2);
      });
    };
    lane(1.65, "HOT PATH  ·  ~10 ms  ·  $0", C.okSoft, C.ok, [
      ["Normalise", "typos, Hinglish, enumerations"], ["Embed", "bge-small, ONNX, CPU (~7 ms)"], ["Match", "cosine over paraphrase cloud, τ = 0.87"],
      ["Guard", "polarity · symptoms · context · source"], ["Serve plan", "validated at compile time"]], []);
    lane(3.2, "COLD PATH  ·  ~3 s  ·  ~$0.001", C.signalSoft, C.signalInk, [
      ["Enrich ∥ Extract", "LLM: 8-10 rewordings; cited steps"], ["Ground", "drop unsupported, invented, outcome steps"], ["Categorise", "auto / manual / critical, disruption order"],
      ["Deeplinks", "exact leaf → hybrid → closed-set LLM"], ["Repair + gate", "word rules, Pydantic schema, score"]], [0, 3]);
    arrow(s, 3.5, 2.5, 3.5, 3.15, C.ink2, "dash");
    txt(s, "miss", { x: 3.58, y: 2.68, w: 0.6, h: 0.25, fontFace: F.mono, fontSize: 8, color: C.muted });
    arrow(s, 8.2, 3.15, 8.2, 2.5, C.ok, "dash");
    txt(s, "write-back", { x: 8.27, y: 2.68, w: 1.0, h: 0.25, fontFace: F.mono, fontSize: 8, color: C.ok });
    s.addShape(pres.shapes.RECTANGLE, { x: 0.5, y: 4.3, w: 0.16, h: 0.16, fill: { color: C.signalSoft }, line: { color: C.signal, width: 1 } });
    txt(s, "calls a language model", { x: 0.72, y: 4.26, w: 1.9, h: 0.24, fontSize: 9, color: C.ink2 });
    s.addShape(pres.shapes.RECTANGLE, { x: 2.6, y: 4.3, w: 0.16, h: 0.16, fill: { color: C.white }, line: { color: C.ink, width: 1 } });
    txt(s, "local, deterministic code", { x: 2.82, y: 4.26, w: 2, h: 0.24, fontSize: 9, color: C.ink2 });
    txt(s, "No article? Knowledge-base retrieval → opt-in catalog-grounded plan → otherwise honest no_siis_context.\nEndpoints: POST /v1/troubleshoot · POST /v1/feedback · GET /health · GET /v1/metrics",
      { x: 0.5, y: 4.6, w: 9, h: 0.5, fontSize: 9.5, color: C.ink2 });
    s.addNotes("Two paths. The hot path normalises the text, embeds it on the CPU, compares it with every stored rewording, and passes the match through our Symptom-Signature Guard. That's about 10 ms with no AI call. On a miss, the cold path runs enrichment and extraction in parallel, then grounding, categorisation, deeplink resolution, and repair plus a schema gate. Only two stages call a language model; everything else is deterministic code. The result is written back, so the next similar complaint is instant.");
  }

  // ============================================================ 5. HOT PATH / GUARD
  {
    const s = pres.addSlide();
    frame(s, 5, "04 · REMEMBER · SEMANTIC CACHE + SYMPTOM-SIGNATURE GUARD", "Similar words aren't the same problem");
    txt(s, "Every compiled plan is stored with ~10 rewordings as vectors. A new complaint is served from the cache only if it is close enough AND the guard agrees it is the same problem.",
      { x: 0.5, y: 1.3, w: 5.4, h: 0.6, fontSize: 11, color: C.ink2 });
    const ex = (y, a, b, sim, why) => {
      card(s, 0.5, y, 2.35, 0.62); txt(s, a, { x: 0.62, y, w: 2.15, h: 0.62, fontFace: F.head, italic: true, fontSize: 10, valign: "middle" });
      card(s, 3.55, y, 2.35, 0.62); txt(s, b, { x: 3.67, y, w: 2.15, h: 0.62, fontFace: F.head, italic: true, fontSize: 10, valign: "middle" });
      txt(s, sim, { x: 2.86, y: y + 0.05, w: 0.68, h: 0.25, fontFace: F.mono, fontSize: 9, bold: true, align: "center" });
      txt(s, "cosine", { x: 2.86, y: y + 0.3, w: 0.68, h: 0.2, fontFace: F.mono, fontSize: 7, color: C.muted, align: "center" });
      s.addImage({ data: ic.times, x: 0.5, y: y + 0.7, w: 0.16, h: 0.16 });
      txt(s, why, { x: 0.72, y: y + 0.66, w: 5.2, h: 0.24, fontSize: 9.5, bold: true, color: C.crit });
    };
    ex(2.0, "“Wi-Fi keeps turning ON by itself”", "“Wi-Fi keeps turning OFF by itself”", "0.96", "guard: polarity mismatch → not served (opposite fixes)");
    ex(3.05, "“flashes and goes blank when I scroll a web page”", "“flashes and goes blank when I open an email in Gmail”", "0.88", "guard: context mismatch (browse ≠ email) → full pipeline");
    txt(s, "The guard compares:  on/off polarity  ·  symptom set  ·  trigger context (charging, camera, Gmail, browsing…)  ·  same source article",
      { x: 0.5, y: 4.2, w: 5.4, h: 0.5, fontSize: 9.5, color: C.ink2 });
    card(s, 6.3, 1.3, 3.2, 3.6, C.white);
    stat(s, 6.5, 1.35, 2.9, "82.5%", "hit rate on 97 unseen rewordings", "written by a different model · target ≥ 80%", C.ok, 28);
    stat(s, 6.5, 2.5, 2.9, "44% → 10%", "false hits on look-alike traps", "same τ, guard off vs on (−77%)", C.signal, 24);
    stat(s, 6.5, 3.62, 2.9, "8.8 ms", "P95 cache lookup", "embed + search + guard · target ≤ 300 ms", C.ink, 28);
    s.addNotes("Embeddings think 'Wi-Fi keeps turning ON' and 'turning OFF' are 96% the same, but they need opposite fixes. So on top of cosine similarity we compare a small symptom signature: on/off polarity, the symptom set, the trigger context, and whether the plan came from the same article. On 97 unseen rewordings written by a different model, we hit 82.5%. On adversarial look-alikes, the guard cuts wrong answers from 44% to 10% at the same threshold, and the lookup itself takes 8.8 ms at P95.");
  }

  // ============================================================ 6. GROUNDED EXTRACTION
  {
    const s = pres.addSlide();
    frame(s, 6, "05 · READ · EVIDENCE-ANCHORED EXTRACTION", "Every step must cite the sentence it came from");
    card(s, 0.5, 1.35, 4.6, 2.15, C.white);
    txt(s, "SIIS article → numbered sentences", { x: 0.65, y: 1.43, w: 4.3, h: 0.25, fontFace: F.mono, fontSize: 8, color: C.muted });
    txt(s, "[12] If you wish to keep your screen protector on, you can try enabling the Touch sensitivity option.", { x: 0.65, y: 1.72, w: 4.3, h: 0.48, fontFace: F.mono, fontSize: 8.5, color: C.ink2 });
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y: 2.22, w: 4.4, h: 0.55, fill: { color: C.signalSoft }, line: { type: "none" }, rectRadius: 0.05 });
    txt(s, "[13] To do this, go to Settings, tap Display, and then tap the switch next to Touch sensitivity.", { x: 0.65, y: 2.24, w: 4.3, h: 0.52, fontFace: F.mono, fontSize: 8.5, color: C.signalInk, bold: true });
    txt(s, "[14] Usage Habits: The touchscreen might not work correctly if you're wearing gloves…", { x: 0.65, y: 2.85, w: 4.3, h: 0.5, fontFace: F.mono, fontSize: 8.5, color: C.muted });
    arrow(s, 2.8, 3.55, 2.8, 3.8, C.ink);
    card(s, 0.5, 3.85, 4.6, 0.72, C.white, C.ok);
    s.addImage({ data: ic.check, x: 0.65, y: 4.08, w: 0.22, h: 0.22 });
    txt(s, [{ text: "“Tap the switch next to Touch sensitivity.”   ", options: { bold: true } }, { text: "src: [13] → key words found → kept", options: { color: C.ok, fontFace: F.mono, fontSize: 9 } }],
      { x: 0.98, y: 3.85, w: 4.05, h: 0.72, fontSize: 10.5, valign: "middle" });
    const checks = [
      ["Grounding check", "a step's key words must appear in its cited sentence (or a neighbour), otherwise it is dropped"],
      ["No invented UI", "'Tap on Force Restart Device' and outcome sentences like 'Your phone will restart' are removed"],
      ["Conditions respected", "'if you're NOT using a protector…' steps only appear when the condition fits"],
      ["Relevance gate", "article doesn't address the complaint → contexts: [] + fallback: no_match"],
      ["Multi-intent", "one Goal per distinct problem; identical plans are merged"],
    ];
    checks.forEach(([h, d], i) => {
      const y = 1.35 + i * 0.6;
      numDot(s, 5.45, y + 0.02, i + 1, C.signal);
      txt(s, h, { x: 5.9, y, w: 3.6, h: 0.24, fontSize: 11, bold: true });
      txt(s, d, { x: 5.9, y: y + 0.24, w: 3.6, h: 0.34, fontSize: 9, color: C.ink2 });
    });
    txt(s, "On the 20 provided scenarios:  18 grounded plans  ·  2 honest no_match  ·  3 multi-goal answers",
      { x: 5.45, y: 4.45, w: 4.1, h: 0.4, fontSize: 9.5, bold: true, color: C.ink });
    s.addNotes("This is how we stop hallucinated steps. The article is split into numbered sentences, and the model must return, for every step, the sentence number it came from. Code then checks that the step's key words really appear there, otherwise the step is dropped. We also remove invented UI elements and outcome sentences, respect conditional instructions, and return an honest no_match when the article doesn't cover the complaint. Complaints with several problems get one goal per problem.");
  }

  // ============================================================ 7. DEEPLINKS
  {
    const s = pres.addSlide();
    frame(s, 7, "06 · CONNECT · DEEPLINK RESOLUTION", "Links are chosen from the catalog, never generated");
    const steps = [
      ["Exact leaf-screen match", "deterministic: “Navigation bar”, not its parent “Display”"],
      ["Hybrid retrieval", "BM25 + bge-small dense over 577 entries, RRF fusion"],
      ["Depth-aware rerank", "leaf-token bonus; enable → onURL, disable → offURL"],
      ["Closed-set choice", "small LLM returns a catalog ID or NONE; code copies URI + validation"],
    ];
    steps.forEach(([h, d], i) => {
      const y = 1.35 + i * 0.78;
      card(s, 0.5, y, 4.3, 0.66, C.white);
      numDot(s, 0.65, y + 0.17, i + 1, i === 3 ? C.signal : C.ink);
      txt(s, h, { x: 1.1, y: y + 0.06, w: 3.6, h: 0.26, fontSize: 11, bold: true });
      txt(s, d, { x: 1.1, y: y + 0.32, w: 3.6, h: 0.3, fontSize: 9, color: C.ink2 });
    });
    txt(s, "dummy_positive only for a real Settings screen with no catalog entry · manual actions never carry a link",
      { x: 0.5, y: 4.5, w: 4.3, h: 0.45, fontSize: 9, italic: true, color: C.muted });
    s.addChart(pres.charts.BAR, [{ name: "Accuracy@1", labels: ["OneTap (ours)", "Hybrid only", "Rules only", "Full catalog in LLM"], values: [95.8, 91.7, 91.7, 62.5] }], {
      x: 5.1, y: 1.3, w: 4.4, h: 3.0, barDir: "bar", chartColors: [C.signal, "8A8375", "8A8375", "C9C1B2"],
      showTitle: true, title: "Exact catalog entry recovered (24 ground-truth actions)", titleFontFace: F.body, titleFontSize: 10, titleColor: C.ink,
      showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 9, dataLabelFormatCode: '0.0"%"', dataLabelColor: C.ink,
      valAxisMaxVal: 112, valAxisMinVal: 0, valAxisHidden: true, valGridLine: { style: "none" }, catGridLine: { style: "none" },
      catAxisLabelColor: C.ink2, catAxisLabelFontSize: 9, catAxisOrientation: "maxMin", showLegend: false, barGapWidthPct: 60,
    });
    txt(s, "0% wrong on/off twin (hybrid: 8.3%)  ·  full-catalog LLM costs 43× more per action\n100% of emitted links exist in the catalog: by construction, not by prompt",
      { x: 5.1, y: 4.38, w: 4.4, h: 0.6, fontSize: 9.5, color: C.ink2 });
    s.addNotes("Deeplinks can never be hallucinated in OneTap, because the model never writes one. First we try an exact match on the deepest screen named in the steps. Otherwise hybrid retrieval finds candidates, a depth-aware reranker prefers the leaf screen and the right on/off direction, and a small model picks a catalog ID or NONE. Code copies the URI and its validation link verbatim. On 24 ground-truth actions we recover the exact entry 95.8% of the time, with zero on/off mistakes. Putting the whole catalog in the prompt gets only 62.5%, at 43 times the cost.");
  }

  // ============================================================ 8. RULES IN CODE
  {
    const s = pres.addSlide();
    frame(s, 8, "07 · CHECK · RULES IN CODE, NOT PROMPTS", "The contract is enforced by code on every response");
    const rows = [
      ["Rule", "How OneTap enforces it"],
      ["goal", "built from a template: “Follow these steps to perform this <Topic> Troubleshooting”"],
      ["title", "2-3 words, sentence case: validator + LLM repair + deterministic fallback"],
      ["actionName", "Title Case; one action = one screen (segmentation in extraction prompt)"],
      ["description", "5-7 words starting “It will”: word-count check, batched repair"],
      ["steps", "one interaction each; URLs & markdown scrubbed from every field"],
      ["deeplinks", "must exist in catalog; manual actions never carry one"],
      ["query_variations", "8-10 distinct rewordings; deterministic top-up"],
      ["schema", "Pydantic gate on the provided schema.py before any response"],
    ];
    s.addTable(rows.map((r, i) => r.map((c, j) => ({
      text: c, options: { bold: i === 0 || j === 0, fontFace: j === 0 && i > 0 ? F.mono : F.body, fontSize: i === 0 ? 10 : 9.5,
        color: i === 0 ? C.white : C.ink, fill: { color: i === 0 ? C.ink : (i % 2 ? C.white : C.paper) } } }))),
      { x: 0.5, y: 1.35, w: 5.6, colW: [1.6, 4.0], rowH: 0.36, border: { type: "solid", pt: 0.5, color: C.rule }, valign: "middle", margin: [0.03, 0.08, 0.03, 0.08] });
    txt(s, "Ordering contract", { x: 6.5, y: 1.35, w: 3, h: 0.3, fontFace: F.head, fontSize: 14, bold: true });
    const blocks = [["AUTO", "Settings toggles & pages", "one-tap deeplink", C.okSoft, C.ok], ["MANUAL", "inspect, charge, contact service", "never a deeplink", C.manSoft, C.man], ["CRITICAL", "restart, safe mode, reset, updates", "always last", C.critSoft, C.crit]];
    blocks.forEach(([t, d, n, f, c], i) => {
      const y = 1.78 + i * 0.95;
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 6.5, y, w: 3.0, h: 0.72, fill: { color: f }, line: { type: "none" }, rectRadius: 0.08 });
      txt(s, t, { x: 6.65, y: y + 0.07, w: 1.3, h: 0.24, fontFace: F.mono, fontSize: 10, bold: true, color: c });
      txt(s, n, { x: 7.9, y: y + 0.07, w: 1.5, h: 0.24, fontSize: 8.5, italic: true, color: c, align: "right" });
      txt(s, d, { x: 6.65, y: y + 0.36, w: 2.8, h: 0.3, fontSize: 9.5, color: C.ink });
      if (i < 2) arrow(s, 8.0, y + 0.74, 8.0, y + 0.93, C.ink2);
    });
    txt(s, "Within a block: disruption level, then reference order. Deterministic: same input, same plan.",
      { x: 6.5, y: 4.65, w: 3.0, h: 0.4, fontSize: 9, color: C.ink2 });
    s.addNotes("The problem statement warns that prompt-only constraints are unreliable, so every rule is enforced in code. The goal is built from a template, titles and descriptions are word-counted and repaired, URLs are scrubbed from every field, links must exist in the catalog, and the provided schema.py is a hard gate. Ordering is fixed: auto Settings actions first, manual checks next, critical actions like restart or reset always last.");
  }

  // ============================================================ 9. INNOVATIONS
  {
    const s = pres.addSlide();
    frame(s, 9, "08 · INNOVATION", "What's new in OneTap");
    const items = [
      [ic.shield, C.crit, "Symptom-Signature Guard", "Polarity, symptom set, trigger context and source check on top of cosine: 44% → 10% wrong cache answers."],
      [ic.quote, C.signal, "Evidence-anchored extraction", "Every step cites a sentence; code verifies it. Unsupported, invented and contradictory steps are dropped."],
      [ic.link, C.man, "Exact-leaf + closed-set deeplinks", "Deterministic leaf match, then the LLM may only pick an ID. 95.8% exact, 0 fabricated links."],
      [ic.book, C.ok, "Catalog-grounded fallback", "No article? The AI may only pick real Settings from the catalog; code writes the steps (opt-in)."],
      [ic.sync, C.ink, "Self-healing cache", "👍 / 👎 on every plan; a plan with more 👎 than 👍 is evicted and rebuilt from the source."],
      [ic.random, C.signalInk, "Hedged, model-agnostic LLM layer", "Per-stage models, pool failover on 429/5xx, retry-after aware, prompt memo, per-request cost."],
    ];
    items.forEach(([img, col, h, d], i) => {
      const x = 0.5 + (i % 3) * 3.05, y = 1.35 + Math.floor(i / 3) * 1.8;
      card(s, x, y, 2.85, 1.62, C.white);
      s.addShape(pres.shapes.OVAL, { x: x + 0.18, y: y + 0.18, w: 0.46, h: 0.46, fill: { color: col }, line: { type: "none" } });
      s.addImage({ data: img, x: x + 0.3, y: y + 0.3, w: 0.22, h: 0.22 });
      txt(s, h, { x: x + 0.78, y: y + 0.18, w: 1.95, h: 0.46, fontSize: 11, bold: true, valign: "middle" });
      txt(s, d, { x: x + 0.18, y: y + 0.75, w: 2.5, h: 0.8, fontSize: 9, color: C.ink2, valign: "top" });
    });
    txt(s, "Also: Hinglish + typo normalisation  ·  guided step-by-step mode  ·  voice input (en-IN)  ·  paste-any-article  ·  explainable UI",
      { x: 0.5, y: 4.95, w: 9, h: 0.25, fontSize: 9, italic: true, color: C.muted });
    s.addNotes("Six innovations, each aimed at a pitfall the problem statement lists. The guard fixes semantic false hits. Evidence-anchored extraction fixes hallucinated steps. Exact-leaf plus closed-set choice fixes parent-menu matching and fabricated links. The catalog fallback answers complaints no article covers without inventing anything. The feedback loop makes the cache self-healing. And a hedged LLM layer keeps the service up when a provider is rate-limited.");
  }

  // ============================================================ 10. RESULTS: COMPLIANCE
  {
    const s = pres.addSlide();
    frame(s, 10, "09 · RESULTS · CONTRACT COMPLIANCE (results.jsonl, all 20 scenarios)", "100% on every automated gate");
    const tiles = [
      ["100%", "schema-valid output", "target ≥ 99%"], ["100%", "rule compliance", "goal · title · description · target ≥ 95%"], ["0", "URL leaks", "target 0"],
      ["100%", "deeplinks exist in catalog", "exact URI match · target 100%"], ["100%", "auto actions with a deeplink", "target ≥ 90%"], ["100%", "8-10 query_variations", "every response"],
    ];
    tiles.forEach(([v, l, t], i) => {
      const x = 0.5 + (i % 3) * 3.05, y = 1.4 + Math.floor(i / 3) * 1.7;
      card(s, x, y, 2.85, 1.5, C.white);
      txt(s, v, { x: x + 0.2, y: y + 0.15, w: 2.5, h: 0.65, fontFace: F.mono, fontSize: 36, bold: true, color: i === 2 ? C.ok : C.ink });
      txt(s, l, { x: x + 0.2, y: y + 0.82, w: 2.5, h: 0.3, fontSize: 11.5, bold: true });
      txt(s, t, { x: x + 0.2, y: y + 1.1, w: 2.5, h: 0.28, fontSize: 9, color: C.muted });
    });
    txt(s, "Audited by scripts/report.py on every build: Pydantic schema + 12 rule checks per goal.", { x: 0.5, y: 4.85, w: 9, h: 0.3, fontSize: 9.5, color: C.ink2 });
    s.addNotes("Against the automated gates in the problem statement we are at 100% everywhere: schema-valid output, rule compliance, zero URL leaks, every deeplink exists in the catalog, every auto action carries a deeplink, and every response has 8 to 10 query variations. This is audited by a script on every build, not checked by hand.");
  }

  // ============================================================ 11. RESULTS: SPEED, COST, ACCURACY
  {
    const s = pres.addSlide();
    frame(s, 11, "10 · RESULTS · SPEED, COST & ACCURACY", "Speed, cost and accuracy at a glance");
    const lat = [["1.1 ms", "exact cache hit · P95", "N = 40 · budget 300 ms", 0.004], ["10.4 ms", "unseen rewording · P95", "N = 80 · budget 300 ms", 0.035], ["3.2 s", "full cold pipeline · P95", "N = 30 · budget 8 s", 0.40]];
    lat.forEach(([v, l, n, frac], i) => {
      const x = 0.5 + i * 3.05;
      card(s, x, 1.35, 2.85, 1.6, C.white);
      txt(s, v, { x: x + 0.2, y: 1.45, w: 2.5, h: 0.6, fontFace: F.mono, fontSize: 30, bold: true, color: i < 2 ? C.ok : C.signal });
      txt(s, l, { x: x + 0.2, y: 2.05, w: 2.5, h: 0.26, fontSize: 11, bold: true });
      s.addShape(pres.shapes.RECTANGLE, { x: x + 0.2, y: 2.42, w: 2.45, h: 0.1, fill: { color: C.paper2 }, line: { type: "none" } });
      s.addShape(pres.shapes.RECTANGLE, { x: x + 0.2, y: 2.42, w: Math.max(0.04, 2.45 * frac), h: 0.1, fill: { color: i < 2 ? C.ok : C.signal }, line: { type: "none" } });
      txt(s, `${n} · ${Math.max(1, Math.round(frac * 100))}% of budget used`.replace("1% of", "<1% of"), { x: x + 0.2, y: 2.58, w: 2.5, h: 0.26, fontSize: 8.5, color: C.muted });
    });
    const bottom = [["$0.0008", "average cost per cold query", "$0 on every cache hit"], ["2.25 / 3", "step accuracy", "LLM judge from a different model family"], ["1.43 / 2", "deeplink relevance", "on the provided scenarios"]];
    bottom.forEach(([v, l, n], i) => {
      const x = 0.5 + i * 3.05;
      txt(s, v, { x, y: 3.25, w: 2.8, h: 0.55, fontFace: F.mono, fontSize: 24, bold: true, color: C.ink });
      txt(s, l, { x, y: 3.82, w: 2.8, h: 0.26, fontSize: 11, bold: true });
      txt(s, n, { x, y: 4.08, w: 2.8, h: 0.26, fontSize: 9, color: C.muted });
    });
    txt(s, "Cold latency is server-side, measured with provider quota available; free-tier rate limits can add seconds (see limitations).",
      { x: 0.5, y: 4.7, w: 9, h: 0.3, fontSize: 9, italic: true, color: C.muted });
    s.addNotes("Speed: an exact repeat takes 1.1 ms, an unseen rewording 10.4 ms at P95, both far inside the 300 ms budget. A brand-new complaint takes 3.2 seconds at P95 against an 8-second budget. Cost is about eight hundredths of a cent per new complaint and zero on a hit. Accuracy was judged by a model from a different family than ours: 2.25 out of 3 for steps, and 1.43 out of 2 for deeplink relevance.");
  }

  // ============================================================ 12. ABLATION
  {
    const s = pres.addSlide();
    frame(s, 12, "11 · ABLATION", "Why this design: measured against the alternatives");
    const rows = [["Deeplink variant", "Acc@1", "Wrong twin", "No link", "$ / action"],
      ["Full catalog in LLM (baseline)", "62.5%", "8.3%", "16.7%", "0.00261"],
      ["A: Hybrid BM25 + dense", "91.7%", "8.3%", "0%", "0"],
      ["B: Pure rules (BM25)", "91.7%", "4.2%", "0%", "0"],
      ["OneTap: leaf + hybrid + rerank + closed-set", "95.8%", "0%", "4.2%", "0.00006"]];
    s.addTable(rows.map((r, i) => r.map((c, j) => ({ text: c, options: {
      bold: i === 0 || i === 4, fontSize: 9, fontFace: j > 0 && i > 0 ? F.mono : F.body, align: j === 0 ? "left" : "center",
      color: i === 0 ? C.white : (i === 4 ? C.signalInk : C.ink), fill: { color: i === 0 ? C.ink : (i === 4 ? C.signalSoft : C.white) } } }))),
      { x: 0.5, y: 1.35, w: 5.2, colW: [2.2, 0.72, 0.8, 0.7, 0.78], rowH: 0.42, border: { type: "solid", pt: 0.5, color: C.rule }, valign: "middle", margin: [0.03, 0.06, 0.03, 0.06] });
    txt(s, "Guard ablation (same τ = 0.87)", { x: 0.5, y: 3.65, w: 5.2, h: 0.3, fontFace: F.head, fontSize: 13, bold: true });
    txt(s, [{ text: "Guard off:  ", options: { bold: true } }, { text: "96.9% hit · 44% false hits\n" }, { text: "Guard on:   ", options: { bold: true, color: C.ok } }, { text: "82.5% hit · 10% false hits  (−77% wrong answers, still ≥ 80% target)", options: { color: C.ok } }],
      { x: 0.5, y: 4.0, w: 5.2, h: 0.6, fontSize: 10.5, fontFace: F.body });
    s.addChart(pres.charts.LINE, [
      { name: "Hit rate on unseen rewordings", labels: ["0.80", "0.83", "0.86", "0.89", "0.92"], values: [95.9, 93.8, 84.5, 79.4, 54.6] },
      { name: "False-hit rate on look-alikes", labels: ["0.80", "0.83", "0.86", "0.89", "0.92"], values: [32, 24, 12, 4, 2] }], {
      x: 6.0, y: 1.3, w: 3.5, h: 3.3, chartColors: [C.ok, C.signal], lineSize: 2, lineDataSymbolSize: 6,
      showTitle: true, title: "Cache threshold sweep τ (guard on), %", titleFontSize: 10, titleColor: C.ink, titleFontFace: F.body,
      showLegend: true, legendPos: "b", legendFontSize: 8, catAxisLabelFontSize: 8, valAxisLabelFontSize: 8, valAxisMaxVal: 100, valAxisMinVal: 0,
      valGridLine: { color: "E6E0D4", size: 0.5 }, catGridLine: { style: "none" }, catAxisLabelColor: C.ink2, valAxisLabelColor: C.ink2 });
    txt(s, "We chose τ = 0.87: the highest hit rate that keeps false hits ≈ 10% and hits ≥ 80%.", { x: 6.0, y: 4.65, w: 3.5, h: 0.45, fontSize: 9, color: C.ink2 });
    s.addNotes("The problem statement asks for an ablation, and we measured each design choice. For deeplinks, putting the full catalog in the prompt is the worst option: 62.5% accuracy at the highest cost. Our combination is the most accurate and never picks the wrong on/off twin. For the cache we swept the threshold: lower thresholds hit more but serve more wrong answers. We picked 0.87, and the guard is what keeps false hits at 10% instead of 44%.");
  }

  // ============================================================ 13. PRODUCT (UI)
  {
    const s = pres.addSlide();
    frame(s, 13, "12 · THE PRODUCT", "See what the engine did, and why");
    s.addImage({ path: IMG("ui_hero.jpg"), x: 0.5, y: 1.3, w: 5.4, h: 3.41 });
    s.addShape(pres.shapes.RECTANGLE, { x: 0.5, y: 1.3, w: 5.4, h: 3.41, fill: { type: "none" }, line: { color: C.rule, width: 0.75 } });
    s.addImage({ path: IMG("ui_guard.jpg"), x: 6.1, y: 1.3, w: 3.4, h: 2.125 });
    s.addShape(pres.shapes.RECTANGLE, { x: 6.1, y: 1.3, w: 3.4, h: 2.125, fill: { type: "none" }, line: { color: C.rule, width: 0.75 } });
    txt(s, "Guard in action: 0.88 similar to a cached Gmail case, rejected for context mismatch, and the plain-English narration explains why.",
      { x: 6.1, y: 3.5, w: 3.4, h: 0.62, fontSize: 9, color: C.ink2 });
    txt(s, "How-it-works strip lights up the path each request took · 10 one-click scenario cards · phone + live instrument panel",
      { x: 0.5, y: 4.8, w: 9, h: 0.3, fontSize: 9.5, italic: true, color: C.muted });
    s.addNotes("The demo UI is built to explain the backend. The strip at the top lights up the path each request took. Ten scenario cards each show one capability. On the right, a narration panel explains in plain English what happened. Here the guard rejected a 0.88-similar cached answer because the context was different.");
  }

  // ============================================================ 14. BUILT FOR USERS
  {
    const s = pres.addSlide();
    frame(s, 14, "13 · BUILT FOR REAL USERS", "From answer to fixed: guided, spoken, one tap");
    s.addImage({ path: IMG("ui_guided.jpg"), x: 5.1, y: 1.3, w: 4.4, h: 2.75 });
    s.addShape(pres.shapes.RECTANGLE, { x: 5.1, y: 1.3, w: 4.4, h: 2.75, fill: { type: "none" }, line: { color: C.rule, width: 0.75 } });
    txt(s, "Guided mode: one action at a time, tickable steps, the one-tap link, then “Didn't help →” or “✓ This fixed it”.",
      { x: 5.1, y: 4.12, w: 4.4, h: 0.5, fontSize: 9, color: C.ink2 });
    const feats = [
      [ic.hand, "One-tap Settings", "the deeplink opens a simulated Settings screen, the toggle flips and the validation check confirms"],
      [ic.list, "Guided step-by-step", "progress bar, confetti when fixed, support hand-off when every step failed"],
      [ic.mic, "Voice input", "speak the complaint (Web Speech API, en-IN), including Hinglish"],
      [ic.paste, "Paste any article", "any help page becomes a grounded plan, not limited to the dataset"],
      [ic.thumbs, "Feedback", "👍 / 👎 feeds the self-healing cache"],
      [ic.eye, "Explainable", "“i” explainers, similarity gauge, stage waterfall, raw JSON"],
    ];
    feats.forEach(([img, h, d], i) => {
      const y = 1.3 + i * 0.6;
      s.addShape(pres.shapes.OVAL, { x: 0.5, y: y + 0.03, w: 0.38, h: 0.38, fill: { color: C.ink }, line: { type: "none" } });
      s.addImage({ data: img, x: 0.595, y: y + 0.125, w: 0.19, h: 0.19 });
      txt(s, h, { x: 1.02, y, w: 3.9, h: 0.24, fontSize: 11, bold: true });
      txt(s, d, { x: 1.02, y: y + 0.24, w: 3.9, h: 0.32, fontSize: 9, color: C.ink2 });
    });
    s.addNotes("For real users, a plan is only useful if it gets them to 'fixed'. Guided mode walks through one action at a time. The one-tap button opens the Settings screen, and the validation deeplink confirms the toggle changed. Users can speak the complaint, paste any help article, and give thumbs up or down, which feeds the self-healing cache.");
  }

  // ============================================================ 15. TECH STACK
  {
    const s = pres.addSlide();
    frame(s, 15, "14 · TECH STACK", "CPU-friendly, cheap, provider-agnostic");
    const groups = [
      ["API & runtime", ["FastAPI + Uvicorn", "Pydantic (schema.py gate)", "Docker + compose", "JSON-only responses"]],
      ["Language models", ["Groq gpt-oss-120b: extraction", "gpt-oss-20b: deeplink choice", "qwen3.8-27b: enrichment / repair", "any OpenAI-compatible API"]],
      ["Retrieval & cache", ["bge-small-en-v1.5 (ONNX, CPU)", "NumPy BM25 + RRF fusion", "paraphrase-cloud vector cache", "symptom-signature lexicon"]],
      ["Evaluation", ["97 held-out rewordings", "50 adversarial look-alikes", "24-action deeplink ground truth", "LLM judge (Gemini) · HTTP bench"]],
      ["Frontend", ["vanilla HTML / CSS / JS", "Web Speech API (voice)", "light + dark, mobile-ready", "no framework, one file"]],
    ];
    groups.forEach(([h, items], i) => {
      const x = 0.5 + i * 1.84;
      card(s, x, 1.35, 1.7, 3.3, C.white);
      txt(s, h, { x: x + 0.12, y: 1.45, w: 1.5, h: 0.45, fontFace: F.head, fontSize: 12, bold: true, valign: "top" });
      items.forEach((it, k) => {
        s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: x + 0.1, y: 2.0 + k * 0.62, w: 1.5, h: 0.52, fill: { color: k === 0 ? C.signalSoft : C.paper }, line: { type: "none" }, rectRadius: 0.06 });
        txt(s, it, { x: x + 0.16, y: 2.0 + k * 0.62, w: 1.38, h: 0.52, fontSize: 8.5, color: C.ink, valign: "middle" });
      });
    });
    txt(s, "Runs on CPU only · swap the LLM provider with two .env lines · every stage's model is configurable", { x: 0.5, y: 4.8, w: 9, h: 0.3, fontSize: 9.5, italic: true, color: C.muted });
    s.addNotes("The stack is deliberately light. FastAPI with a Pydantic gate, CPU-only ONNX embeddings, a NumPy BM25, and fast open models on Groq, with each stage on its own model. Any OpenAI-compatible provider works via two .env lines. The frontend is a single HTML file with no framework.");
  }

  // ============================================================ 16. SCALE / WORKLET
  {
    const s = pres.addSlide();
    frame(s, 16, "15 · FROM HACKATHON TO WORKLET", "Built to scale to 10k+ scenarios");
    const road = [
      ["Offline scenario compiler", "batch-compile every KB article + query into validated plans and paraphrase clouds (scripts/build_cache.py)"],
      ["Stage-level caching", "extraction and mapping cached separately; a reverse index deeplink → plans recompiles only what a catalog change touches"],
      ["Feedback-driven quality", "👍/👎 evicts weak plans; dashboards on hit rate, false hits and cost per query (GET /v1/metrics)"],
      ["On-device + assistant", "CPU embeddings fit on-device; hand plans to the voice assistant for truly hands-free fixes"],
    ];
    road.forEach(([h, d], i) => {
      const x = 0.5 + i * 2.3;
      numDot(s, x, 1.4, i + 1, i === 0 ? C.signal : C.ink, C.white, 0.42);
      if (i < 3) s.addShape(pres.shapes.LINE, { x: x + 0.47, y: 1.61, w: 1.78, h: 0, line: { color: C.rule, width: 1.5, dashType: "dash" } });
      txt(s, h, { x, y: 1.95, w: 2.1, h: 0.5, fontSize: 11.5, bold: true, valign: "top" });
      txt(s, d, { x, y: 2.45, w: 2.1, h: 1.05, fontSize: 9, color: C.ink2, valign: "top" });
    });
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.5, y: 3.7, w: 9, h: 1.25, fill: { color: C.ink }, line: { type: "none" }, rectRadius: 0.1 });
    txt(s, "Back-of-envelope at 1M complaints / day", { x: 0.75, y: 3.8, w: 5, h: 0.3, fontFace: F.head, fontSize: 13, bold: true, color: C.darkText });
    txt(s, [{ text: "~80% served from cache (measured hit rate)  →  ~200k cold compiles × ~$0.001  ≈  ", options: {} }, { text: "$200 / day", options: { bold: true, color: C.signal } },
      { text: "\nvs. 15 min of manual agent triage per scenario  ≈  250,000 agent-hours / day", options: { color: C.darkMuted } }],
      { x: 0.75, y: 4.15, w: 8.5, h: 0.7, fontSize: 11, color: C.darkText, fontFace: F.body });
    s.addNotes("Scaling to 10 thousand plus scenarios is mostly offline work. Compile every article in batch, cache stage outputs separately, and keep a reverse index from each deeplink to the plans that use it, so a One UI update only recompiles affected plans. At a million complaints a day, with our measured hit rate, the AI bill is roughly 200 dollars a day, against 250 thousand agent-hours of manual triage.");
  }

  // ============================================================ 17. LIMITATIONS
  {
    const s = pres.addSlide();
    frame(s, 17, "16 · HONEST LIMITATIONS", "What we know isn't perfect yet, and what's next");
    const lim = [
      ["Mismatched reference articles", "3 of 20 scenarios were judged off-topic yet answered.", "stricter relevance + article re-retrieval"],
      ["LLM-generated look-alike set", "some “negatives” are arguably the same fault, so 10% false hits is conservative.", "human-labelled adversarial set"],
      ["Lexicon-based signatures", "English + common Hinglish/typos; unseen slang can slip past the guard.", "learned symptom classifier"],
      ["Provider tier affects cold latency", "free-tier daily caps pushed a spot check to ~11 s P50.", "paid tier; model-pool hedging (in place)"],
      ["Catalog fallback is advisory", "a catalog entry says what a setting does, not that it fixes this fault.", "confidence capped at 0.70; opt-in only"],
      ["One UI hierarchy changes", "screen paths move between versions.", "reverse index deeplink → plans for targeted recompiles"],
    ];
    lim.forEach(([h, d, nx], i) => {
      const x = 0.5 + (i % 2) * 4.6, y = 1.3 + Math.floor(i / 2) * 1.2;
      card(s, x, y, 4.4, 1.05, C.white);
      txt(s, h, { x: x + 0.18, y: y + 0.08, w: 4.1, h: 0.26, fontSize: 11, bold: true });
      txt(s, d, { x: x + 0.18, y: y + 0.34, w: 4.1, h: 0.36, fontSize: 9, color: C.ink2 });
      txt(s, [{ text: "next → ", options: { bold: true, color: C.signalInk } }, { text: nx, options: { color: C.signalInk } }], { x: x + 0.18, y: y + 0.7, w: 4.1, h: 0.28, fontSize: 9 });
    });
    s.addNotes("We want to be upfront about the limits. Some provided articles don't match their complaints. Our look-alike test set was generated by an LLM, so the false-hit number is conservative. Signatures are lexicon-based. Cold latency depends on the provider tier. The catalog fallback is advisory, which is why it's opt-in and capped. Each limitation already has a concrete next step.");
  }

  // ============================================================ 18. CLOSING
  {
    const s = pres.addSlide();
    s.background = { color: C.ink };
    s.addShape(pres.shapes.OVAL, { x: 0.5, y: 0.47, w: 0.1, h: 0.1, fill: { color: C.signal }, line: { type: "none" } });
    txt(s, "THEME 02 · SMART GUIDED TROUBLESHOOTING ENGINE", { x: 0.7, y: 0.38, w: 6, h: 0.28, fontFace: F.mono, fontSize: 9, color: C.darkMuted, charSpacing: 2 });
    txt(s, "Thank you", { x: 0.5, y: 1.1, w: 9, h: 1.0, fontFace: F.head, fontSize: 54, italic: true, color: C.darkText });
    txt(s, "Describe it in your own words. Get a verified fix, one tap away.", { x: 0.5, y: 2.1, w: 9, h: 0.45, fontSize: 16, color: "C9C1B2" });
    const nums = [["100%", "contract compliance"], ["10.4 ms", "P95 on unseen rewordings"], ["3.2 s", "P95 cold pipeline"], ["95.8%", "exact deeplinks"], ["44→10%", "wrong cache answers"]];
    nums.forEach(([v, l], i) => {
      txt(s, v, { x: 0.5 + i * 1.82, y: 2.95, w: 1.75, h: 0.5, fontFace: F.mono, fontSize: 21, bold: true, color: C.signal });
      txt(s, l, { x: 0.5 + i * 1.82, y: 3.45, w: 1.7, h: 0.4, fontSize: 9.5, color: C.darkMuted });
    });
    txt(s, "github.com/shouryez/onetap  (tag PRISM_GENAI_HACKATHON_Y2026)   ·   demo: youtu.be/oJ5d5VblRTA",
      { x: 0.5, y: 4.2, w: 9, h: 0.3, fontFace: F.mono, fontSize: 10.5, color: C.signal });
    txt(s, "Shourya Chouhan  ·  Shreya Singh Chouhan  ·  Yash Mittal  ·  Vrunda Hatwar", { x: 0.5, y: 4.72, w: 9, h: 0.28, fontSize: 11, bold: true, color: C.darkText });
    txt(s, "Team Aloo Paratha  ·  M S Ramaiah Institute of Technology (MSRIT), Bengaluru", { x: 0.5, y: 5.02, w: 9, h: 0.28, fontFace: F.mono, fontSize: 9, color: C.darkMuted });
    s.addNotes("To sum up: 100% contract compliance, around 10 ms for known problems, 3 seconds for new ones, 95.8% exact deeplinks, and a guard that cuts wrong cache answers from 44 to 10 percent. The code, metrics and demo video are linked in the submission. Thank you, and we're happy to take questions.");
  }

  await pres.writeFile({ fileName: OUT });
  console.log("wrote", OUT);
})();
