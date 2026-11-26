"""Sensitive-topic router (SPEC §3 routing table, docs/specs/input-topics.md).

Crisis keyword fast-path first, then keyword rules per category, then a classifier hook.
The YAML routing table turns the category into an action and an optional fixed reply.
"""

from __future__ import annotations

import re
import time
from typing import Any

from guardbank.input.detectors import StubTopicClassifier, TopicClassifier
from guardbank.types import Action, GuardResult, Span

STAGE = "input_topic"
CRISIS = "CRISIS"
NORMAL = "NORMAL"


def _compile(patterns: list[str]) -> list[re.Pattern[str]]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


class TopicRouter:
    def __init__(self, config: dict[str, Any], classifier: TopicClassifier | None = None) -> None:
        self.tau: float = config["tau"]
        self.crisis = _compile(config["crisis"])
        self.categories = {name: _compile(rx) for name, rx in config["categories"].items()}
        helpline = config["helpline"]
        fill = {"helpline_name": helpline["name"], "helpline_number": helpline["number"]}
        self.routes: dict[str, dict[str, Any]] = {}
        for name, route in config["routes"].items():
            r = dict(route)
            if r.get("response"):
                r["response"] = r["response"].format(**fill)
            self.routes[name] = r
        if classifier is None:
            kind = config.get("classifier", "stub")
            if kind != "stub":
                raise NotImplementedError(f"classifier {kind!r} arrives in feat/ml-detectors")
            classifier = StubTopicClassifier()
        self.classifier = classifier

    @classmethod
    def from_settings(cls, settings: Any) -> TopicRouter:
        return cls(settings.input["topics"])

    @staticmethod
    def _hits(label: str, patterns: list[re.Pattern[str]], text: str) -> list[Span]:
        return [
            Span(start=m.start(), end=m.end(), label=label, text=m.group(0))
            for rx in patterns
            for m in rx.finditer(text)
        ]

    def _classify(self, text: str) -> tuple[str, float, str, list[Span]]:
        """(category, score, source, spans) — first rule that fires wins."""
        spans = self._hits(CRISIS, self.crisis, text)
        if spans:
            return CRISIS, 1.0, "crisis", spans
        for name, patterns in self.categories.items():
            spans = self._hits(name, patterns, text)
            if spans:
                return name, 1.0, "keyword", spans
        label, prob = self.classifier.predict(text)
        if label != NORMAL and label in self.routes and prob >= self.tau:
            return label, prob, "classifier", []
        return NORMAL, prob if label == NORMAL else 0.0, "classifier", []

    def check(self, text: str) -> GuardResult:
        t0 = time.perf_counter()
        category, score, source, spans = self._classify(text)
        route = self.routes[category]
        detected = category != NORMAL
        return GuardResult(
            stage=STAGE,
            detected=detected,
            score=score if detected else 0.0,
            spans=sorted(spans, key=lambda s: s.start),
            category=category,
            action=Action(route["action"]),
            latency_ms=(time.perf_counter() - t0) * 1000,
            details={
                "route": route["route"],
                "escalate": bool(route["escalate"]),
                "response": route.get("response"),
                "disclaimer": route.get("disclaimer"),
                "matches": sorted({s.label for s in spans}),
                "source": source,
            },
        )
