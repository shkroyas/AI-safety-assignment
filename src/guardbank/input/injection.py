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
CLASSIFIER = "CLASSIFIER"


class InjectionDetector:
    def __init__(
        self,
        config: dict[str, Any],
        classifier: ScoreDetector | None = None,
        pii_classifier: ScoreDetector | None = None,
    ) -> None:
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
        # Messages with PII are scored by a second classifier when configured: DeBERTa
        # over-flags benign messages carrying card/account numbers or passwords.
        with_pii = config.get("classifier_with_pii")
        if pii_classifier is not None:
            self.pii_classifier = pii_classifier
        elif with_pii:
            self.pii_classifier = build_injection_scorer({**config, "classifier": with_pii})
        else:
            self.pii_classifier = self.classifier

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

    def check(self, text: str, decoded: Iterable[str] = (), has_pii: bool = False) -> GuardResult:
        t0 = time.perf_counter()
        spans = self.scan(text)
        matched = {s.label for s in spans}
        for d in decoded:
            matched |= {s.label for s in self.scan(d)}
        # YAML order breaks ties between equal weights.
        matches = [name for name in self.patterns if name in matched]

        regex_score = max((self.weights[n] for n in matches), default=0.0)
        top = max(matches, key=lambda n: self.weights[n]) if matches else None
        clf_name = "with_pii" if has_pii else "default"
        clf_score = (self.pii_classifier if has_pii else self.classifier).score(text)
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
                "classifier": clf_name,
                "classifier_score": clf_score,
                "refusal": self.refusal if detected else None,
            },
        )
