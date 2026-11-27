"""Guarded pipeline (SPEC §2 steps 1-8, docs/specs/remediation-pipeline.md).

Input guards -> retrieval + chunk scan -> LLM -> output guards, with the remediation policy
deciding retries, strips and fallbacks. Every stage result is appended to the audit log.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from guardbank.assistant import build_embedder
from guardbank.audit import AuditLog
from guardbank.config import Settings
from guardbank.input.injection import InjectionDetector
from guardbank.input.normalizer import Normalizer
from guardbank.input.pii import PiiRedactor, PiiVault
from guardbank.input.topics import TopicRouter
from guardbank.output.groundedness import GroundednessChecker
from guardbank.output.leakage import LeakageChecker
from guardbank.output.schema import SchemaGuard, SupportReply
from guardbank.rag.chunk_scan import ChunkScanner
from guardbank.rag.corpus import chunk_docs, load_corpus
from guardbank.rag.llm import LLMClient
from guardbank.rag.prompts import build_system_prompt, format_context, new_canary
from guardbank.rag.retriever import Retriever
from guardbank.remediation import Remediation, audit_details
from guardbank.types import Action, GuardResult

# Topic routes answered with a fixed reply and no LLM call -> outcome name.
_FIXED_ROUTES = {"crisis": "crisis", "block": "blocked", "redirect": "redirect"}


@dataclass
class Session:
    vault: PiiVault = field(default_factory=PiiVault)


@dataclass
class PipelineResult:
    request_id: str
    text: str
    reply: SupportReply | None
    escalate: bool
    outcome: str
    stages: list[GuardResult]
    llm_calls: int
    latency_ms: float


class Pipeline:
    def __init__(
        self,
        *,
        normalizer: Normalizer,
        pii: PiiRedactor,
        injection: InjectionDetector,
        topics: TopicRouter,
        retriever: Retriever,
        chunk_scan: ChunkScanner,
        llm: LLMClient,
        schema: SchemaGuard,
        groundedness: GroundednessChecker,
        leakage: LeakageChecker,
        remediation: Remediation,
        audit: AuditLog,
    ) -> None:
        self.normalizer, self.pii, self.injection, self.topics = normalizer, pii, injection, topics
        self.retriever, self.chunk_scan, self.llm = retriever, chunk_scan, llm
        self.schema, self.groundedness, self.leakage = schema, groundedness, leakage
        self.remediation, self.audit = remediation, audit

    @classmethod
    def from_settings(
        cls, settings: Settings, *, llm: LLMClient, audit: AuditLog | None = None
    ) -> Pipeline:
        chunks = chunk_docs(load_corpus(settings.resolve(settings.corpus.path)))
        return cls(
            normalizer=Normalizer.from_settings(settings),
            pii=PiiRedactor.from_settings(settings),
            injection=InjectionDetector.from_settings(settings),
            topics=TopicRouter.from_settings(settings),
            retriever=Retriever(chunks, build_embedder(settings), top_k=settings.retriever.top_k),
            chunk_scan=ChunkScanner.from_settings(settings),
            llm=llm,
            schema=SchemaGuard.from_settings(settings),
            groundedness=GroundednessChecker.from_settings(settings),
            leakage=LeakageChecker.from_settings(settings),
            remediation=Remediation.from_settings(settings),
            audit=audit or AuditLog(settings.resolve(settings.audit.path)),
        )

    def run(self, text: str, session: Session) -> PipelineResult:
        return _Run(self, text, session).execute()


class _Run:
    """State of one request; keeps `Pipeline.run` readable."""

    def __init__(self, p: Pipeline, text: str, session: Session) -> None:
        self.p, self.text, self.vault = p, text, session.vault
        self.request_id = uuid.uuid4().hex
        self.stages: list[GuardResult] = []
        self.llm_calls = 0
        self.t0 = time.perf_counter()

    def log(self, result: GuardResult) -> GuardResult:
        self.stages.append(result)
        safe = result.model_copy(update={"details": audit_details(result.details)})
        input_text = self.text if result.stage == "remediation" else None
        self.p.audit.append(self.request_id, safe, input_text=input_text)
        return result

    def finish(
        self,
        outcome: str,
        text: str,
        action: Action,
        reason: str,
        *,
        reply: SupportReply | None = None,
        escalate: bool = False,
        attempts: int = 0,
    ) -> PipelineResult:
        self.log(self.p.remediation.decision(action, reason, attempts=attempts, outcome=outcome))
        return PipelineResult(
            request_id=self.request_id,
            text=text,
            reply=reply,
            escalate=escalate,
            outcome=outcome,
            stages=self.stages,
            llm_calls=self.llm_calls,
            latency_ms=(time.perf_counter() - self.t0) * 1000,
        )

    def call_llm(self, system: str, messages: list[dict], temperature: float | None) -> str:
        self.llm_calls += 1
        return self.p.llm.generate(system, messages, temperature=temperature).text

    def schema_valid(
        self, system: str, messages: list[dict], retrieved: list[str], temperature: float | None
    ) -> tuple[SupportReply | None, list[dict]]:
        """LLM call + schema guard, retried with the guard's feedback; None if all fail."""
        for _ in range(self.p.remediation.max_schema_retries + 1):
            raw = self.call_llm(system, messages, temperature)
            r = self.log(self.p.schema.check(raw, retrieved))
            messages = [*messages, {"role": "assistant", "content": raw}]
            if r.action == Action.ALLOW:
                return r.details["reply"], messages
            messages.append({"role": "user", "content": r.details["feedback"]})
        return None, messages

    def execute(self) -> PipelineResult:
        p, rem = self.p, self.p.remediation
        norm = self.log(p.normalizer.check(self.text)).details
        pii = self.log(p.pii.check(norm["normalized"], self.vault, decoded=norm["decoded"]))
        redacted = pii.details["redacted"]

        inj = self.log(
            p.injection.check(
                norm["normalized"],
                decoded=norm["decoded"],
                redacted=redacted if pii.detected else None,
            )
        )
        if inj.action == Action.BLOCK:
            return self.finish("blocked", inj.details["refusal"], Action.BLOCK, "input_injection")

        topic = self.log(p.topics.check(redacted))
        route = topic.details["route"]
        if route in _FIXED_ROUTES:
            outcome = _FIXED_ROUTES[route]
            action = Action.BLOCK if route == "block" else Action.ROUTE
            return self.finish(
                outcome,
                topic.details["response"],
                action,
                f"topic_{topic.category.lower()}",
                escalate=topic.details["escalate"],
            )

        kept, scan = p.chunk_scan.filter(p.retriever.search(redacted))
        self.log(scan)
        chunks = {h.chunk.id: h.chunk.text for h in kept}
        canary = new_canary()
        system = build_system_prompt(kept, canary)
        context = format_context(kept)
        messages: list[dict[str, Any]] = [{"role": "user", "content": redacted}]

        def fallback(reason: str) -> PipelineResult:
            text = self.extras(rem.fallback_text, topic, pii)
            return self.finish(
                "fallback", text, Action.FALLBACK, reason, escalate=True, attempts=self.llm_calls
            )

        def leak_blocked(answer: str) -> bool:
            r = self.log(p.leakage.check(answer, self.vault, canary, context))
            return r.action == Action.BLOCK

        reply, messages = self.schema_valid(system, messages, list(chunks), None)
        if reply is None:
            return fallback("schema_invalid")
        if leak_blocked(reply.answer):
            return self.finish("blocked", rem.block_text, Action.BLOCK, "output_leak")

        g = self.log(p.groundedness.check(reply, chunks))
        answer, reason, action = reply.answer, "answered", Action.ALLOW
        if g.action == Action.REGENERATE:
            messages.append({"role": "user", "content": rem.regenerate_instruction})
            reply, messages = self.schema_valid(system, messages, list(chunks), 0)
            if reply is None:
                return fallback("schema_invalid_on_regenerate")
            if leak_blocked(reply.answer):
                return self.finish("blocked", rem.block_text, Action.BLOCK, "output_leak")
            g = self.log(p.groundedness.check(reply, chunks))
            answer, reason = reply.answer, "regenerated"
            if g.action == Action.REGENERATE:
                answer, reason, action = (
                    rem.strip(g.details["claims"]),
                    "stripped_unsupported",
                    Action.REDACT,
                )
        if g.action == Action.FALLBACK:
            return fallback(f"groundedness_{(g.category or 'fallback').lower()}")

        final = self.log(p.leakage.check(answer, self.vault, canary, context))
        text = self.extras(final.details["text"], topic, pii)
        escalate = reply.escalate or topic.details["escalate"]
        return self.finish(
            "answered",
            text,
            action,
            reason,
            reply=reply,
            escalate=escalate,
            attempts=self.llm_calls,
        )

    @staticmethod
    def extras(text: str, topic: GuardResult, pii: GuardResult) -> str:
        parts = [text, topic.details.get("disclaimer"), pii.details.get("warning")]
        return " ".join(x for x in parts if x)
