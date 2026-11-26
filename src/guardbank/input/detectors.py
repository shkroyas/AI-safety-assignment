"""ML detector interface (CLAUDE.md rule): real models sit behind `Detector`, with a CPU stub."""

from __future__ import annotations

from typing import Protocol

from guardbank.types import Span


class Detector(Protocol):
    def detect(self, text: str) -> list[Span]:
        """Return labelled spans (offsets into `text`, `span.text` = matched text)."""
        ...


class StubDetector:
    """CPU stub for fast tests and CI: finds nothing."""

    def detect(self, text: str) -> list[Span]:
        return []


class PresidioDetector:
    """Presidio AnalyzerEngine on spaCy NER. Needs the `pii` extra and the spaCy model."""

    def __init__(self, spacy_model: str, entities: list[str]) -> None:
        from presidio_analyzer import AnalyzerEngine
        from presidio_analyzer.nlp_engine import NlpEngineProvider

        provider = NlpEngineProvider(
            nlp_configuration={
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": spacy_model}],
            }
        )
        self.entities = entities
        self._engine = AnalyzerEngine(
            nlp_engine=provider.create_engine(), supported_languages=["en"]
        )

    def detect(self, text: str) -> list[Span]:
        if not self.entities:
            return []
        hits = self._engine.analyze(text=text, entities=self.entities, language="en")
        return [
            Span(start=h.start, end=h.end, label=h.entity_type, text=text[h.start : h.end])
            for h in hits
        ]


class ScoreDetector(Protocol):
    def score(self, text: str) -> float:
        """Return the probability (0..1) that `text` is a prompt-injection attack."""
        ...


class StubScorer:
    """CPU stub for fast tests and CI: scores everything 0.0."""

    def score(self, text: str) -> float:
        return 0.0
