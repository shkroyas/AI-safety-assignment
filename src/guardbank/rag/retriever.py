"""Top-k retrieval over corpus chunks with a FAISS inner-product index."""

from __future__ import annotations

from dataclasses import dataclass

import faiss

from guardbank.rag.corpus import Chunk
from guardbank.rag.embed import Embedder


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float


class Retriever:
    def __init__(self, chunks: list[Chunk], embedder: Embedder, top_k: int = 4):
        if not chunks:
            raise ValueError("Retriever needs at least one chunk")
        self.chunks = chunks
        self.embedder = embedder
        self.top_k = top_k
        # Title is prepended so short sections still match their topic.
        vectors = embedder.embed([f"{c.title}\n{c.text}" for c in chunks])
        self.index = faiss.IndexFlatIP(vectors.shape[1])
        self.index.add(vectors)

    def search(self, query: str, k: int | None = None) -> list[Hit]:
        k = min(k or self.top_k, len(self.chunks))
        scores, ids = self.index.search(self.embedder.embed([query]), k)
        return [
            Hit(chunk=self.chunks[i], score=float(s))
            for s, i in zip(scores[0], ids[0], strict=True)
            if i >= 0
        ]
