"""Local CPU embeddings (bge-small via fastembed/ONNX). ~5 ms per short query."""
import threading
from functools import lru_cache

import numpy as np

from . import config

_model = None
_lock = threading.Lock()


def _get():
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                import os
                from fastembed import TextEmbedding
                _model = TextEmbedding(config.EMBED_MODEL, cache_dir=os.getenv("FASTEMBED_CACHE_PATH"))
                list(_model.embed(["warm up"]))
    return _model


def embed_many(texts: list[str]) -> np.ndarray:
    if not texts:
        return np.zeros((0, 384), dtype=np.float32)
    v = np.array(list(_get().embed(texts, batch_size=64)), dtype=np.float32)
    v /= np.linalg.norm(v, axis=1, keepdims=True) + 1e-9
    return v


@lru_cache(maxsize=4096)
def _embed_one_cached(text: str) -> bytes:
    return embed_many([text])[0].tobytes()


def embed_one(text: str) -> np.ndarray:
    return np.frombuffer(_embed_one_cached(text), dtype=np.float32)


def ready() -> bool:
    return _model is not None


def warm() -> None:
    _get()
