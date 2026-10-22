"""Demo-safe mode: run every scenario card (and the demo's extra questions) once through the full pipeline with the
semantic cache bypassed, so each AI stage's answer is memoised on disk. On stage the same questions then run the
real pipeline (every stage, every check) in about a second, even with a flaky network or provider rate limits.

    python -m scripts.prewarm_demo                 # server must be running on 127.0.0.1:8000
"""
import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
rows = {r["id"]: r for r in json.loads((ROOT / "data" / "siis_responses.json").read_text(encoding="utf-8"))["responses"]}

BATTERY = """Fix battery draining quickly on your phone
If your battery drains faster than expected, try these steps.
Check battery usage: Navigate to Settings, tap Battery, then tap Battery usage to see which apps use the most power.
Turn on Power saving: Navigate to Settings, tap Battery, and then tap the switch next to Power saving.
Lower screen brightness: Swipe down to open the Quick panel and drag the brightness slider to the left.
Update your apps and software: Navigate to Settings, tap Software update, and then tap Download and install.
Restart your phone: Press and hold the Side button, then tap Restart.
If the problem continues, contact customer support or visit a service center."""

DEMO = [
    ("touch stopped working properly after I put on a new screen protector", "row_21"),
    ("my screen registers touches I didn't make and I don't use any screen guard", "row_21"),
    ("My tablet screen flashes and then goes blank whenever I scroll a web page in the browser", None),
    ("my battery drains really fast even overnight", None),
    ("battery dies super fast even when I'm not using the phone", "PASTE"),
    ("my battery drains really fast", "row_21"),
    ("my car won't start in the morning", None),
    ("phone screen bahut flicker kar raha hai aur black ho jata hai", None),
    ("my screen went black after a month and it won't even turn on", None),
    ("touch feels slow and laggy when I type", "row_21"),
]


def main(base="http://127.0.0.1:8000"):
    c = httpx.Client(base_url=base, timeout=180)
    assert c.get("/health").json().get("status") == "ok", "start the server first"
    for q, src in DEMO:
        body = {"query": q}
        if src == "PASTE":
            body["siis_response"] = BATTERY
        elif src:
            body["siis_response"] = rows[src]["siis_response"]
        t = time.perf_counter()
        o = c.post("/v1/troubleshoot", params={"nocache": "true", "catalog_fallback": "true"}, json=body).json()
        m = o["meta"]
        print(f"{(time.perf_counter() - t):5.1f}s  goals={len(o['response']['contexts'])} "
              f"fb={m.get('fallback', '-'):16s} {q[:60]}")
    print("pre-warm done: these questions now run the full pipeline in ~1 s")


if __name__ == "__main__":
    main(*(sys.argv[1:2]))
