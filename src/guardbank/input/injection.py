"""Input prompt-injection detection (SPEC §3, docs/specs/input-injection.md).

Pruned regex bank plus a classifier hook. `scan()` is reused by the chunk scan.
"""

from __future__ import annotations

import re
import time
from collections.abc import Iterable
from typing import Any

from guardbank.input.detectors import ScoreDetector, build_injection_scorer
from guardbank.types import Action, GuardResult, Span

STAGE = "input_injection"
_TOKEN = re.compile(r"<([A-Z_]+)_\d+>")
CLASSIFIER = "CLASSIFIER"


class InjectionDetector:
    def __init__(self, config: dict[str, Any], classifier: ScoreDetector | None = None) -> None:
        self.tau: float = config["tau"]
        self.refusal: str = config["refusal"]
        self.patterns: dict[str, re.Pattern[str]] = {
            name: re.compile(p["regex"], re.IGNORECASE | re.MULTILINE)
            for name, p in config["patterns"].items()
        }
        self.weights: dict[str, float] = {
            name: float(p["weight"]) for name, p in config["patterns"].items()
        }
        self.classifier = classifier or build_injection_scorer(config)
        # Messages with PII: the classifier must flag both the raw and the redacted text
        # (DeBERTa over-flags card/account numbers; docs/specs/fix-injection-pii-refusals.md).
        self.classify_redacted: bool = config.get("classifier_redacted", False)
        self.redacted_words: dict[str, str] = config.get("redacted_words", {})

    def _words(self, redacted: str) -> str:
        """`<CARD_1>` -> "card": typed tokens read as payloads to the classifier."""
        return _TOKEN.sub(
            lambda m: self.redacted_words.get(m.group(1), m.group(1).lower()), redacted
        )

    @classmethod
    def from_settings(cls, settings: Any) -> InjectionDetector:
        return cls(settings.input["injection"])

    def scan(self, text: str) -> list[Span]:
        """All pattern matches in `text`, in text order."""
        spans = [
            Span(start=m.start(), end=m.end(), label=name, text=m.group(0))
            for name, rx in self.patterns.items()
            for m in rx.finditer(text)
        ]
        return sorted(spans, key=lambda s: s.start)

    def check(
        self, text: str, decoded: Iterable[str] = (), redacted: str | None = None
    ) -> GuardResult:
        t0 = time.perf_counter()
        spans = self.scan(text)
        matched = {s.label for s in spans}
        for d in decoded:
            matched |= {s.label for s in self.scan(d)}
        # YAML order breaks ties between equal weights.
        matches = [name for name in self.patterns if name in matched]

        regex_score = max((self.weights[n] for n in matches), default=0.0)
        top = max(matches, key=lambda n: self.weights[n]) if matches else None
        clf_raw = self.classifier.score(text)
        clf_red = None
        if self.classify_redacted and redacted is not None and redacted != text:
            clf_red = self.classifier.score(self._words(redacted))
        clf_score = clf_raw if clf_red is None else min(clf_raw, clf_red)
        score = max(regex_score, clf_score)
        category = CLASSIFIER if clf_score > regex_score else top

        detected = score >= self.tau
        return GuardResult(
            stage=STAGE,
            detected=detected,
            score=score,
            spans=spans,
            category=category if detected else None,
            action=Action.BLOCK if detected else Action.ALLOW,
            latency_ms=(time.perf_counter() - t0) * 1000,
            details={
                "matches": matches,
                "regex_score": regex_score,
                "classifier_score": clf_score,
                "classifier_raw": clf_raw,
                "classifier_redacted": clf_red,
                "refusal": self.refusal if detected else None,
            },
        )
