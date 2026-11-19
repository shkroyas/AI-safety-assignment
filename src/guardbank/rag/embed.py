"""Text embedders behind one interface.

HashingEmbedder is deterministic and dependency-free, so CI needs no model download.
SentenceTransformerEmbedder is the real model (optional `ml` extra).
"""

from __future__ import annotations

import hashlib
import re
from typing import Protocol

import numpy as np

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    "a an and are as at be by can do does for from how i in is it my of on or the to what "
    "when where which who will with you your".split()
)


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> np.ndarray:
        """Return an (n, dim) float32 array of L2-normalised vectors."""
        ...


def _normalise(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (vectors / norms).astype(np.float32)


class HashingEmbedder:
    """Bag of unigrams + bigrams hashed into a fixed-size vector, with sublinear tf."""

    def __init__(self, dim: int = 4096):
        self.dim = dim

    def _features(self, text: str) -> list[str]:
        tokens = [t for t in _TOKEN.findall(text.lower()) if t not in _STOP]
        return tokens + [f"{a}_{b}" for a, b in zip(tokens, tokens[1:], strict=False)]

    def _bucket(self, feature: str) -> int:
        digest = hashlib.blake2b(feature.encode(), digest_size=8).digest()
        return int.from_bytes(digest, "little") % self.dim

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, text in enumerate(texts):
            for feature in self._features(text):
                out[i, self._bucket(feature)] += 1.0
        return _normalise(np.log1p(out))


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]) -> np.ndarray:
        vectors = self.model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)
        return np.asarray(vectors, dtype=np.float32)
