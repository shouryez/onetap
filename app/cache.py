"""Fast-path semantic cache.

L0  exact match on the normalised query            (~0.1 ms)
L1  cosine over every stored paraphrase embedding   (~5 ms embed + <1 ms matmul)
    + Symptom-Signature Guard (polarity / symptom / component compatibility)
    + source check (a request carrying a different SIIS article is not served another article's plan)
Entries persist to JSON so a restarted container comes up warm.
"""
import hashlib
import json
import threading
import time

import numpy as np

from . import config
from .embed import embed_many, embed_one
from .text import normalise, signature, signature_compatible


def siis_hash(siis_text: str) -> str | None:
    if not siis_text:
        return None
    return hashlib.sha1(" ".join(siis_text.split()).encode("utf-8")).hexdigest()[:16]


class SemanticCache:
    def __init__(self, path=config.CACHE_PATH, tau: float = config.CACHE_TAU, tau_low: float = config.CACHE_TAU_LOW):
        self.path = path
        self.tau, self.tau_low = tau, tau_low
        self.entries: dict[str, dict] = {}
        self.exact: dict[str, str] = {}
        self.keys: list[str] = []            # row -> entry id
        self.sigs: list[dict] = []           # row -> signature of that paraphrase
        self.profiles: dict[str, set] = {}   # entry id -> set of symptom sets seen across its paraphrases
        self.mat = np.zeros((0, 384), dtype=np.float32)
        self.lock = threading.Lock()
        self.stats = {"lookups": 0, "hits": 0, "guard_rejections": 0}
        self.guard_enabled = True

    # ------------------------------------------------------------------ persistence
    def load(self) -> int:
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            for e in data.get("entries", []):
                self._index(e, persist=False)
        return len(self.entries)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"entries": list(self.entries.values())}, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    def clear(self) -> None:
        with self.lock:
            self.entries.clear(); self.exact.clear(); self.keys.clear(); self.sigs.clear(); self.profiles.clear()
            self.mat = np.zeros((0, 384), dtype=np.float32)

    # ------------------------------------------------------------------ write
    def _index(self, entry: dict, persist: bool = True) -> None:
        texts = [entry["query"]] + [v for v in entry.get("query_variations", [])] + entry.get("aliases", [])
        norms = []
        for t in texts:
            n = normalise(t)
            if n and n not in norms:
                norms.append(n)
        vecs = embed_many(norms)
        sigs = [signature(n) for n in norms]
        entry["signature"] = signature(normalise(entry["query"]))   # recomputed: lexicon may have evolved
        with self.lock:
            self.entries[entry["id"]] = entry
            # symptom profile: every symptom set this problem has been described with
            self.profiles[entry["id"]] = {frozenset(g["symptoms"]) for g in sigs if g["symptoms"]}
            for n in norms:
                self.exact.setdefault(n + "|" + str(entry.get("siis_hash")), entry["id"])
                self.exact.setdefault(n + "|*", entry["id"])
            self.keys.extend([entry["id"]] * len(norms))
            self.sigs.extend(sigs)
            self.mat = np.vstack([self.mat, vecs]) if len(self.mat) else vecs
        if persist:
            self.save()

    def put(self, query: str, variations: list[str], response: dict, siis_text: str, meta: dict,
            aliases: list[str] | None = None, source: str | None = None) -> str:
        sh = siis_hash(siis_text)
        eid = hashlib.sha1((normalise(query) + "|" + str(sh)).encode()).hexdigest()[:12]
        entry = {"id": eid, "query": query, "query_variations": variations, "aliases": aliases or [],
                 "siis_hash": sh, "response": response, "model": meta.get("model"),
                 "created": int(time.time()), "signature": signature(normalise(query)),
                 "votes": {"up": 0, "down": 0}, **({"source": source} if source else {})}
        if eid in self.entries:
            return eid
        self._index(entry)
        return eid

    # ------------------------------------------------------------------ feedback / eviction
    def remove(self, eid: str) -> bool:
        with self.lock:
            if eid not in self.entries:
                return False
            keep = [i for i, k in enumerate(self.keys) if k != eid]
            self.mat = self.mat[keep] if keep else np.zeros((0, 384), dtype=np.float32)
            self.keys = [self.keys[i] for i in keep]
            self.sigs = [self.sigs[i] for i in keep]
            self.exact = {k: v for k, v in self.exact.items() if v != eid}
            self.profiles.pop(eid, None)
            self.entries.pop(eid)
        self.save()
        return True

    def feedback(self, eid: str, helpful: bool) -> dict:
        """Thumbs up/down on a served plan. A plan with more downs than ups is evicted, so the next request
        recompiles it from the source (self-healing cache)."""
        e = self.entries.get(eid)
        if not e:
            return {"plan_id": eid, "found": False}
        v = e.setdefault("votes", {"up": 0, "down": 0})
        v["up" if helpful else "down"] += 1
        evicted = v["down"] > v["up"]
        if evicted:
            self.remove(eid)
        else:
            self.save()
        return {"plan_id": eid, "found": True, "votes": v, "evicted": evicted}

    # ------------------------------------------------------------------ read
    def lookup(self, query: str, siis_text: str = "") -> tuple[dict | None, dict]:
        """Returns (entry | None, debug-info)."""
        self.stats["lookups"] += 1
        n = normalise(query)
        sh = siis_hash(siis_text)
        info = {"normalised": n, "signature": signature(n)}
        eid = self.exact.get(n + "|" + str(sh)) if sh else self.exact.get(n + "|*")
        if eid:
            self.stats["hits"] += 1
            info.update(match="exact", similarity=1.0)
            return self.entries[eid], info
        if not len(self.mat):
            info["match"] = "empty"
            return None, info
        q = embed_one(n)
        sims = self.mat @ q
        order = np.argsort(-sims)[:25]
        qsig = info["signature"]
        rejected = []
        for r in order:
            s = float(sims[r])
            if s < self.tau_low:
                break
            e = self.entries[self.keys[r]]
            if sh and e.get("siis_hash") != sh:
                continue  # request brings an article: only plans built from THAT article may be served
            if self.guard_enabled:
                # polarity vs the matched paraphrase; polarity + trigger context vs the ORIGINAL complaint
                ok, why = signature_compatible(qsig, self.sigs[r], check_symptoms=False)
                if ok:
                    ok, why = signature_compatible(qsig, e["signature"], check_symptoms=False)
                qs = frozenset(qsig["symptoms"])
                # strict profile: the matched paraphrase or the original complaint must name the same symptoms
                profile = {frozenset(self.sigs[r]["symptoms"]), frozenset(e["signature"]["symptoms"])} - {frozenset()}
                if ok and qs and profile and qs not in profile:
                    ok, why = False, "symptom_mismatch"
                if ok and s < self.tau and not (qs and qs in profile):
                    ok, why = False, "borderline_needs_symptom_match"
                if not ok:
                    rejected.append({"similarity": round(s, 3), "reason": why, "cached_query": e["query"][:80]})
                    continue
            elif s < self.tau:
                continue
            self.stats["hits"] += 1
            info.update(match="semantic", similarity=round(s, 4), matched=e["query"][:120])
            if rejected:
                info["guard_rejected"] = rejected[:3]
            return e, info
        if rejected:
            self.stats["guard_rejections"] += 1
            info["guard_rejected"] = rejected[:3]
        info["match"] = "miss"
        info["best_similarity"] = round(float(sims[order[0]]), 4) if len(order) else None
        return None, info


_cache: SemanticCache | None = None


def get_cache() -> SemanticCache:
    global _cache
    if _cache is None:
        _cache = SemanticCache()
        _cache.load()
    return _cache
