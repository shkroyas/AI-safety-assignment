"""One runner per labeled set: run the real guardrail on each item and record its prediction."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from guardbank.config import Settings
from guardbank.input.injection import InjectionDetector
from guardbank.input.normalizer import Normalizer
from guardbank.input.pii import PiiRedactor, PiiVault
from guardbank.input.topics import TopicRouter
from guardbank.output.groundedness import GroundednessChecker
from guardbank.output.leakage import LeakageChecker
from guardbank.output.schema import SupportReply
from guardbank.rag.chunk_scan import ChunkScanner
from guardbank.rag.corpus import Chunk, chunk_docs, load_corpus
from guardbank.rag.retriever import Hit
from guardbank.types import Action

EVAL_CANARY = "GB-CANARY-e5a1c0ffee0000ab"


@dataclass
class Prediction:
    id: str
    label: Any
    pred: Any
    score: float
    kind: str
    text: str
    extra: dict[str, Any] = field(default_factory=dict)


def settings_for(base: Settings, mode: str) -> Settings:
    """fast = YAML as committed; full = every ML model switched on (needs the `ml` extra)."""
    s = copy.deepcopy(base)
    if mode == "full":
        s.input["injection"]["classifier"] = "deberta"
        s.input["pii"]["backend"] = "gliner"
        s.input["topics"]["classifier"] = "embed_logreg"
        s.output["groundedness"]["scorer"] = "hhem"
        s.output["leakage"]["embedder"] = "sentence-transformers"
        s.retriever.embedder = "sentence-transformers"
    elif mode != "fast":
        raise ValueError(f"unknown eval mode {mode!r}; allowed: fast, full")
    return s


def models_used(s: Settings) -> dict[str, str]:
    return {
        "injection": s.input["injection"]["classifier"],
        "pii": s.input["pii"]["backend"],
        "topics": s.input["topics"]["classifier"],
        "groundedness": s.output["groundedness"]["scorer"],
        "leakage": s.output["leakage"]["embedder"],
        "chunk_scan": s.rag["chunk_scan"].get("classifier", "stub"),
        "retriever": s.retriever.embedder,
    }


def run_injection(items: list[Any], s: Settings) -> list[Prediction]:
    """Same order as the pipeline: PII first, so the classifier also sees the redacted text."""
    norm, det = Normalizer.from_settings(s), InjectionDetector.from_settings(s)
    red = PiiRedactor.from_settings(s)
    out = []
    for it in items:
        n = norm.check(it.text).details
        pii = red.check(n["normalized"], PiiVault(), decoded=n["decoded"])
        redacted = pii.details["redacted"] if pii.detected else None
        r = det.check(n["normalized"], decoded=n["decoded"], redacted=redacted)
        out.append(
            Prediction(it.id, it.label, int(r.action == Action.BLOCK), r.score, it.kind, it.text)
        )
    return out


def run_pii(items: list[Any], s: Settings) -> list[Prediction]:
    norm, red = Normalizer.from_settings(s), PiiRedactor.from_settings(s)
    out = []
    for it in items:
        n = norm.check(it.text).details
        r = red.check(n["normalized"], PiiVault(), decoded=n["decoded"])
        found = sorted({sp.label for sp in r.spans})
        out.append(
            Prediction(
                it.id,
                int(bool(it.labels)),
                int(r.detected),
                r.score,
                it.kind,
                it.text,
                {"expected": it.labels, "found": found},
            )
        )
    return out


def run_topics(items: list[Any], s: Settings) -> list[Prediction]:
    norm, router = Normalizer.from_settings(s), TopicRouter.from_settings(s)
    out = []
    for it in items:
        r = router.check(norm.check(it.text).details["normalized"])
        out.append(
            Prediction(
                it.id,
                it.label,
                r.category,
                r.score,
                it.label,
                it.text,
                {"source": r.details["source"]},
            )
        )
    return out


def run_groundedness(items: list[Any], s: Settings) -> list[Prediction]:
    checker = GroundednessChecker.from_settings(s)
    out = []
    for it in items:
        chunks = {f"ev#{i}": text for i, text in enumerate(it.evidence)}
        reply = SupportReply(
            answer=it.claim, citations=list(chunks), intent="other", confidence=0.5, escalate=False
        )
        r = checker.check(reply, chunks)
        claims = r.details.get("claims", [])
        unsupported = int(not claims or not all(c["supported"] for c in claims))
        score = min((c["score"] for c in claims), default=0.0)
        missing = [n for c in claims for n in c["numbers_missing"]]
        out.append(
            Prediction(
                it.id,
                it.label,
                unsupported,
                score,
                it.kind,
                it.claim,
                {"numbers_missing": len(missing)},
            )
        )
    return out


def run_leakage(items: list[Any], s: Settings) -> list[Prediction]:
    leak = LeakageChecker.from_settings(s)
    out = []
    for it in items:
        answer = it.answer.replace("{canary}", EVAL_CANARY)
        r = leak.check(answer, PiiVault(), EVAL_CANARY, it.context)
        fired = r.action == Action.BLOCK or r.category == "THIRD_PARTY_PII"
        out.append(
            Prediction(
                it.id,
                it.label,
                int(fired),
                r.details["prompt_similarity"],
                it.kind,
                it.answer,
                {"category": r.category},
            )
        )
    return out


def clean_corpus_chunks(s: Settings) -> list[Chunk]:
    chunks = chunk_docs(load_corpus(s.resolve(s.corpus.path)))
    return [c for c in chunks if not c.poisoned]


def run_chunk_scan(items: list[Any], s: Settings) -> list[Prediction]:
    """Poisoned synthetic chunks are the positives; the clean corpus chunks are the negatives."""
    scanner = ChunkScanner.from_settings(s)
    rows = [(it.id, 1, it.text, it.kind) for it in items] + [
        (c.id, 0, c.text, "clean_corpus") for c in clean_corpus_chunks(s)
    ]
    out = []
    for cid, label, text, kind in rows:
        _, r = scanner.filter(
            [Hit(Chunk(id=cid, doc_id=cid.split("#")[0], title="", text=text), 1.0)]
        )
        out.append(Prediction(cid, label, int(r.detected), r.score, kind, text))
    return out


def run_crisis(items: list[Any], s: Settings) -> list[Prediction]:
    """Crisis set run like the pipeline (normalize, redact, route); pred = routed to CRISIS."""
    norm, red, router = (
        Normalizer.from_settings(s),
        PiiRedactor.from_settings(s),
        TopicRouter.from_settings(s),
    )
    out = []
    for it in items:
        n = norm.check(it.text).details
        redacted = red.check(n["normalized"], PiiVault(), decoded=n["decoded"]).details["redacted"]
        r = router.check(redacted)
        pred = int(r.category == "CRISIS")
        out.append(Prediction(it.id, it.label, pred, r.score, it.kind, it.text))
    return out


RUNNERS = {
    "injection": run_injection,
    "injection_pii": run_injection,
    "crisis": run_crisis,
    "pii": run_pii,
    "topics": run_topics,
    "groundedness": run_groundedness,
    "leakage": run_leakage,
    "leakage_pii": run_leakage,
    "chunk_poison": run_chunk_scan,
}
