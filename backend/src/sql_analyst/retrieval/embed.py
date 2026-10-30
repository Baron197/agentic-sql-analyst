"""Text embedders for retrieval. Both are local and keyless.

- `FastEmbedder`: a multilingual sentence-transformers model run with fastembed (ONNX),
  because about a third of the questions are in Bahasa Indonesia (docs/DECISIONS.md).
  The model (~220 MB) downloads once into EMBEDDING_CACHE_DIR.
- `HashEmbedder`: hashed bag of words. No download; used by unit tests only.
"""

import hashlib
import math
import re
from typing import Literal, Protocol

from sql_analyst.config import Settings

DIM = 384
_TOKEN = re.compile(r"\w+")


class Embedder(Protocol):
    name: str
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def _normalize(v: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


class FastEmbedder:
    def __init__(self, model_name: str, cache_dir: str | None = None):
        self.name = model_name
        self.dim = DIM
        self.cache_dir = cache_dir or None
        self._model = None

    def _load(self):
        if self._model is None:
            from fastembed import TextEmbedding  # imported lazily: loading takes a second or two

            self._model = TextEmbedding(model_name=self.name, cache_dir=self.cache_dir)
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = [_normalize([float(x) for x in v]) for v in self._load().embed(texts)]
        if vectors and len(vectors[0]) != self.dim:
            raise ValueError(f"{self.name} returned {len(vectors[0])} dims, expected {self.dim}")
        return vectors


class HashEmbedder:
    """Deterministic bag-of-words vectors (feature hashing). For tests: no model download."""

    name = "hash-bow-384"
    dim = DIM

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            v = [0.0] * self.dim
            for token in _TOKEN.findall(text.lower()):
                h = int.from_bytes(hashlib.md5(token.encode()).digest()[:4], "little")
                v[h % self.dim] += 1.0 if (h >> 31) & 1 else -1.0
            out.append(_normalize(v))
        return out


def make_embedder(settings: Settings, kind: Literal["fastembed", "hash"] = "fastembed") -> Embedder:
    if kind == "hash":
        return HashEmbedder()
    return FastEmbedder(settings.embedding_model, settings.embedding_cache_dir)
