"""Reset the semantic cache to the clean 20-scenario state before a demo (stop the server first, restart after).

    python -m scripts.reset_demo
"""
import shutil
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
shutil.copyfile(DATA / "cache_store.clean.json", DATA / "cache_store.json")
print("cache reset to the clean 20-scenario state - now (re)start the server")
