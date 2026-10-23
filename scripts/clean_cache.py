"""Remove empty ("no match") plans and symptom-drifted rewordings from the saved memory.

    python -m scripts.clean_cache            # stop the server first; cleans data/cache_store.json + the clean snapshot
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.cache import SemanticCache  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data"


def clean(path: Path) -> None:
    if not path.exists():
        return
    d = json.loads(path.read_text(encoding="utf-8"))
    entries = d["entries"] if isinstance(d, dict) and "entries" in d else d
    kept, dropped_plans, dropped_aliases = [], 0, 0
    for e in entries:
        if not e["response"]["contexts"]:
            dropped_plans += 1
            continue
        good = [a for a in e.get("aliases", []) if SemanticCache.alias_fits(e, a)]
        dropped_aliases += len(e.get("aliases", [])) - len(good)
        e["aliases"] = good
        kept.append(e)
    if isinstance(d, dict) and "entries" in d:
        d["entries"] = kept
    else:
        d = kept
    path.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    print(f"{path.name}: kept {len(kept)} plans, removed {dropped_plans} empty plans and {dropped_aliases} drifted rewordings")


if __name__ == "__main__":
    for name in ("cache_store.json", "cache_store.clean.json"):
        clean(DATA / name)
