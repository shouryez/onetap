"""Catalog + knowledge-base loading and hybrid (BM25 + dense) retrieval with RRF fusion."""
import json
import math
import re
from collections import Counter
from functools import lru_cache

import numpy as np

from . import config
from .embed import embed_many, embed_one

_TOK = re.compile(r"[a-z0-9]+")
_BM25_STOP = set("the a an and or of to on in via for your device settings setting page the on".split())


def _toks(s: str) -> list[str]:
    return [t for t in _TOK.findall(s.lower()) if t not in _BM25_STOP]


class BM25:
    def __init__(self, docs: list[str], k1: float = 1.4, b: float = 0.75):
        self.docs = [_toks(d) for d in docs]
        self.k1, self.b = k1, b
        self.avg = sum(map(len, self.docs)) / max(1, len(self.docs))
        df = Counter(t for d in self.docs for t in set(d))
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.tf = [Counter(d) for d in self.docs]

    def scores(self, q: str) -> np.ndarray:
        qt = _toks(q)
        out = np.zeros(len(self.docs), dtype=np.float32)
        for i, tf in enumerate(self.tf):
            dl = len(self.docs[i])
            s = 0.0
            for t in qt:
                if t in tf:
                    f = tf[t]
                    s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avg))
            out[i] = s
        return out


def rrf(rank_lists: list[list[int]], k: int = 60) -> dict[int, float]:
    fused: dict[int, float] = {}
    for rl in rank_lists:
        for r, idx in enumerate(rl):
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (k + r + 1)
    return fused


# ----------------------------------------------------------------------------- deeplink catalog
class Catalog:
    def __init__(self):
        raw = json.loads(config.DEEPLINKS_PATH.read_text(encoding="utf-8"))
        self.entries: list[dict] = raw["deeplinks"]
        self.by_id = {e["id"]: e for e in self.entries}
        self.uris = {e["deeplink"] for e in self.entries}
        self.dummy = self.by_id["DL-DUMMY"]
        # searchable entries: everything except the placeholder
        self.search = [e for e in self.entries if e["id"] != "DL-DUMMY"]
        self.texts = [self.doc_text(e) for e in self.search]
        self.bm25 = BM25(self.texts)
        self.vecs = embed_many(self.texts)

    @staticmethod
    def doc_text(e: dict) -> str:
        return f"{e.get('message') or ''}. {e.get('description') or ''} {e.get('qna_description') or ''}"

    def retrieve(self, query: str, k: int = 8) -> list[tuple[dict, float]]:
        bm = self.bm25.scores(query)
        dv = self.vecs @ embed_one(query)
        bm_rank = list(np.argsort(-bm)[: 40])
        dv_rank = list(np.argsort(-dv)[: 40])
        fused = rrf([bm_rank, dv_rank])
        top = sorted(fused.items(), key=lambda x: -x[1])[:k]
        return [(self.search[i], float(dv[i])) for i, _ in top]

    def dense_top(self, query: str, k: int = 8) -> list[tuple[dict, float]]:
        dv = self.vecs @ embed_one(query)
        return [(self.search[i], float(dv[i])) for i in np.argsort(-dv)[:k]]

    def bm25_top(self, query: str, k: int = 8) -> list[tuple[dict, float]]:
        bm = self.bm25.scores(query)
        return [(self.search[i], float(bm[i])) for i in np.argsort(-bm)[:k]]


# ----------------------------------------------------------------------------- SIIS knowledge base
class KnowledgeBase:
    """Distinct SIIS articles, used when a request omits siis_response."""

    def __init__(self):
        raw = json.loads(config.SIIS_PATH.read_text(encoding="utf-8"))
        self.rows: list[dict] = raw["responses"]
        seen: dict[str, dict] = {}
        for r in self.rows:
            s = r["siis_response"]
            seen.setdefault(s["title"], s)
        self.articles = list(seen.values())
        self.vecs = embed_many([a["title"] + ". " + a["content"][:1500] for a in self.articles])

    def best(self, query: str) -> tuple[dict | None, float]:
        sims = self.vecs @ embed_one(query)
        i = int(np.argmax(sims))
        return self.articles[i], float(sims[i])


@lru_cache(maxsize=1)
def catalog() -> Catalog:
    return Catalog()


@lru_cache(maxsize=1)
def kb() -> KnowledgeBase:
    return KnowledgeBase()


def input_queries() -> list[str]:
    return [l.strip() for l in config.INPUT_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]


def siis_to_text(siis) -> str:
    if siis is None:
        return ""
    if isinstance(siis, dict):
        return f"{siis.get('title', '')}\n{siis.get('content', '')}".strip()
    return str(siis)
