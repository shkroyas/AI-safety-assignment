"""RAG assistant without guardrails yet: retrieve -> prompt -> LLM -> parse.

Guardrail stages plug in around these steps in later branches (SPEC §2).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from pydantic import ValidationError

from guardbank.audit import AuditLog
from guardbank.config import Settings
from guardbank.output.schema import SupportReply
from guardbank.rag.corpus import chunk_docs, load_corpus
from guardbank.rag.embed import Embedder, HashingEmbedder, SentenceTransformerEmbedder
from guardbank.rag.llm import LLMClient, LLMResponse
from guardbank.rag.prompts import build_system_prompt, new_canary
from guardbank.rag.retriever import Hit, Retriever


@dataclass
class AnswerResult:
    request_id: str
    reply: SupportReply | None
    raw_text: str
    retrieved: list[Hit]
    llm: LLMResponse


def build_embedder(settings: Settings) -> Embedder:
    if settings.retriever.embedder == "sentence-transformers":
        return SentenceTransformerEmbedder(settings.retriever.embedding_model)
    return HashingEmbedder(settings.retriever.hashing_dim)


class Assistant:
    def __init__(self, retriever: Retriever, llm: LLMClient, audit: AuditLog):
        self.retriever = retriever
        self.llm = llm
        self.audit = audit
        self.canary = new_canary()

    @classmethod
    def from_settings(cls, settings: Settings, *, llm: LLMClient) -> Assistant:
        chunks = chunk_docs(load_corpus(settings.resolve(settings.corpus.path)))
        retriever = Retriever(chunks, build_embedder(settings), top_k=settings.retriever.top_k)
        return cls(retriever, llm, AuditLog(settings.resolve(settings.audit.path)))

    def answer(self, text: str) -> AnswerResult:
        request_id = uuid.uuid4().hex
        hits = self.retriever.search(text)
        system = build_system_prompt(hits, self.canary)
        response = self.llm.generate(system, [{"role": "user", "content": text}])
        try:
            reply = SupportReply.model_validate_json(response.text)
        except ValidationError:
            reply = None
        return AnswerResult(request_id, reply, response.text, hits, response)
