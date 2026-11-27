"""Output leakage check (SPEC §4 sensitive-info row, docs/specs/output-leakage.md).

Worst first: canary leak and system-prompt similarity block the reply; PII in the answer
is kept (bank-published), partially masked (the user's own) or redacted (third party).
"""

from __future__ import annotations

import re
import time
from typing import Any

import numpy as np

from guardbank.input.normalizer import Normalizer
from guardbank.input.pii import PiiRedactor, PiiVault
from guardbank.output.groundedness import split_claims
from guardbank.rag.embed import Embedder, HashingEmbedder, SentenceTransformerEmbedder
from guardbank.rag.prompts import SYSTEM_TEMPLATE
from guardbank.types import Action, GuardResult, Span

STAGE = "output_leakage"
_TOKEN = re.compile(r"<([A-Z_]+)_\d+>")
_MIN_WORDS = 4
_NUMBER = re.compile(r"\d[\d\s\-\u2010-\u2013]*\d")  # digits with spaces or hyphens


def instruction_sentences(
    template: str = SYSTEM_TEMPLATE, exclude: list[str] | tuple[str, ...] = ()
) -> list[str]:
    """Sentences of the system prompt's instruction part (before CONTEXT:), canary removed.
    Sentences containing an `exclude` substring (public policy restated) are left out."""
    head = template.split("CONTEXT:")[0].replace("{canary}", "")
    blocks = re.split(r"\n(?=- )|\n\n", head)
    sentences = [s for b in blocks for s in split_claims(" ".join(b.strip(" -").split()))]
    return [
        s for s in sentences if len(s.split()) >= _MIN_WORDS and not any(x in s for x in exclude)
    ]


class LeakageChecker:
    def __init__(
        self,
        config: dict[str, Any],
        redactor: PiiRedactor,
        embedder: Embedder,
        normalizer: Normalizer,
    ) -> None:
        self.prefix: str = config["canary_prefix"].lower()
        self.tau_prompt: float = config["tau_prompt"][config["embedder"]]
        self.keep_last: int = config["keep_last"]
        self.full_hide: set[str] = set(config["full_hide"])
        # A number in the answer is bank-published when its digits equal a number in the context,
        # whatever the formatting (docs/specs/fix-output-overredaction.md). 0 = off.
        self.public_digits_min: int = config.get("public_digits_min", 0)
        self.redactor = redactor
        self.embedder = embedder
        self.normalizer = normalizer
        self._prompt = embedder.embed(instruction_sentences(exclude=config["public_prompt_lines"]))

    @classmethod
    def from_settings(cls, settings: Any) -> LeakageChecker:
        config = settings.output["leakage"]
        if config["embedder"] == "sentence-transformers":
            embedder: Embedder = SentenceTransformerEmbedder(config["embedding_model"])
        elif config["embedder"] == "hashing":
            embedder = HashingEmbedder(settings.retriever.hashing_dim)
        else:
            kind = config["embedder"]
            raise ValueError(
                f"unknown leakage embedder {kind!r}; allowed: hashing, sentence-transformers"
            )
        # Output: a password needs an explicit marker ("password is X"); "password reset" is text.
        pii_cfg = {
            **settings.input["pii"],
            "password_requires_marker": config.get("password_requires_marker", False),
        }
        return cls(
            config,
            PiiRedactor(pii_cfg),
            embedder,
            Normalizer.from_settings(settings),
        )

    def prompt_similarity(self, answer: str) -> float:
        sentences = split_claims(answer)
        if not sentences:
            return 0.0
        sims = self.embedder.embed(sentences) @ self._prompt.T
        return float(np.clip(sims.max(), 0.0, 1.0))

    def _canary_leak(self, answer: str, canary: str) -> bool:
        norm = self.normalizer.check(answer).details
        texts = [norm["normalized"], *norm["decoded"]]
        needles = (canary.lower(), self.prefix)
        return any(n in t.lower() for t in texts for n in needles)

    def _public_number(self, value: str, context: str) -> bool:
        digits = re.sub(r"\D", "", value)
        if not self.public_digits_min or len(digits) < self.public_digits_min:
            return False
        return any(re.sub(r"\D", "", n) == digits for n in _NUMBER.findall(context))

    def _mask(self, label: str, value: str) -> str:
        if label in self.full_hide:
            return "[hidden]"
        if label == "EMAIL" and "@" in value:
            local, domain = value.split("@", 1)
            return f"{local[:1]}***@{domain}"
        keep = value[-self.keep_last :] if self.keep_last else ""
        return "*" * max(len(value) - len(keep), 0) + keep

    def check(self, answer: str, vault: PiiVault, canary: str, context: str) -> GuardResult:
        t0 = time.perf_counter()
        sim = self.prompt_similarity(answer)

        def result(action, category, score, severity, text, incidents, spans=()):
            return GuardResult(
                stage=STAGE,
                detected=action != Action.ALLOW,
                score=score,
                spans=list(spans),
                category=category,
                action=action,
                latency_ms=(time.perf_counter() - t0) * 1000,
                details={
                    "text": text,
                    "incidents": incidents,
                    "severity": severity,
                    "prompt_similarity": sim,
                },
            )

        if self._canary_leak(answer, canary):
            return result(Action.BLOCK, "CANARY_LEAK", 1.0, "high", None, [{"type": "CANARY_LEAK"}])
        if sim >= self.tau_prompt:
            return result(Action.BLOCK, "PROMPT_LEAK", sim, "high", None, [{"type": "PROMPT_LEAK"}])

        edits: list[tuple[int, int, str, str, str]] = []  # start, end, replacement, type, label
        for m in _TOKEN.finditer(answer):
            value = vault.value_of(m.group(0))
            if value is not None:
                edits.append((m.start(), m.end(), self._mask(m[1], value), "OWN_PII", m[1]))
        for start, end, label in self.redactor.find(answer):
            value = answer[start:end]
            if value in context or self._public_number(value, context):
                continue  # bank-published data, e.g. the grievance email or the hotline
            if vault.has_value(value):
                edits.append((start, end, self._mask(label, value), "OWN_PII", label))
            else:
                edits.append((start, end, f"[redacted {label}]", "THIRD_PARTY_PII", label))

        if not edits:
            return result(Action.ALLOW, None, 0.0, None, answer, [])
        edits.sort()
        text = answer
        for start, end, repl, _, _ in reversed(edits):
            text = text[:start] + repl + text[end:]
        incidents = [{"type": t, "label": label} for _, _, _, t, label in edits]
        spans = [Span(start=s, end=e, label=t, text=label) for s, e, _, t, label in edits]
        third = any(t == "THIRD_PARTY_PII" for *_, t, _ in edits)
        if third:
            return result(Action.REDACT, "THIRD_PARTY_PII", 1.0, "medium", text, incidents, spans)
        return result(Action.REDACT, "OWN_PII", 0.5, "low", text, incidents, spans)
