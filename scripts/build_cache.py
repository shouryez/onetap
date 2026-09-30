"""Offline "scenario compiler": runs the cold pipeline over every provided scenario,
writes results.jsonl (one API response per line) and pre-warms the semantic cache.

    python -m scripts.build_cache            # uses cache if already warm
    python -m scripts.build_cache --fresh    # clear cache and recompile everything
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config  # noqa: E402
config.LLM_MAX_WAIT_S = 180  # batch job: be patient with rate limits
from app.cache import get_cache  # noqa: E402
from app.pipeline import troubleshoot  # noqa: E402
from app.retrieval import kb  # noqa: E402
from app.rules import check_goal  # noqa: E402
from app.retrieval import catalog  # noqa: E402


async def main(fresh: bool, concurrency: int, out_path: Path):
    cache = get_cache()
    if fresh:
        cache.clear()
        cache.save()
    rows = kb().rows
    sem = asyncio.Semaphore(concurrency)
    results = [None] * len(rows)

    async def run(i, r):
        async with sem:
            t = time.perf_counter()
            out = await troubleshoot(r["original_query"], r["siis_response"], use_cache=not fresh, write_cache=True)
            out["id"] = r["id"]
            results[i] = out
            n_act = sum(len(c["actions"]) for c in out["response"]["contexts"])
            errs = [e for c in out["response"]["contexts"] for e in check_goal(c, catalog().uris)]
            print(f'{r["id"]:>7} goals={len(out["response"]["contexts"])} actions={n_act:>2} '
                  f'{out["meta"]["latency_ms"]:>6}ms ${out["meta"]["cost_usd"]:.4f} '
                  f'fb={out["meta"].get("fallback", "-")} errs={errs or "-"}  ({time.perf_counter() - t:.1f}s)')

    await asyncio.gather(*(run(i, r) for i, r in enumerate(rows)))
    with out_path.open("w", encoding="utf-8") as f:
        for o in results:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")
    lat = sorted(o["meta"]["latency_ms"] for o in results)
    print(f"\nwrote {out_path} | cache entries={len(cache.entries)} vectors={len(cache.mat)} "
          f"| cold p50={lat[len(lat) // 2]}ms max={lat[-1]}ms | total ${sum(o['meta']['cost_usd'] for o in results):.4f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--out", default=str(config.ROOT / "results.jsonl"))
    a = ap.parse_args()
    asyncio.run(main(a.fresh, a.concurrency, Path(a.out)))
