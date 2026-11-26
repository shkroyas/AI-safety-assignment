"""ML detector interfaces (CLAUDE.md rule): real models sit behind protocols, with CPU stubs.

Factories pick the implementation from YAML. Real models load lazily on first use and are
cached per (name, device), so e.g. input injection and chunk scan share one model.
See docs/specs/ml-input.md.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any, Protocol

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


class TopicClassifier(Protocol):
    def predict(self, text: str) -> tuple[str, float]:
        """Return (category label, probability 0..1) for `text`."""
        ...


class StubTopicClassifier:
    """CPU stub for fast tests and CI: everything is NORMAL with probability 0.0."""

    def predict(self, text: str) -> tuple[str, float]:
        return "NORMAL", 0.0


# ---------- real models (need the `ml` extra) ----------


def resolve_device(device: str) -> str:
    """'auto' -> 'cuda' when a GPU is available, else 'cpu'."""
    if device != "auto":
        return device
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


@functools.cache
def _hf_classifier(name: str, device: str) -> Any:
    from transformers import pipeline

    return pipeline("text-classification", model=name, device=device, top_k=None)


@functools.cache
def _gliner(name: str, device: str) -> Any:
    from gliner import GLiNER

    return GLiNER.from_pretrained(name).to(device)


@functools.cache
def sentence_encoder(name: str, device: str) -> Any:
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(name, device=device)


class HFInjectionScorer:
    """Hugging Face text classifier; score = probability of `positive_label`."""

    def __init__(self, model_name: str, positive_label: str, max_length: int, device: str) -> None:
        self.model_name = model_name
        self.positive_label = positive_label
        self.max_length = max_length
        self.device = device
        self._pipe: Any = None

    @property
    def loaded(self) -> bool:
        return self._pipe is not None

    def score(self, text: str) -> float:
        if self._pipe is None:
            self._pipe = _hf_classifier(self.model_name, resolve_device(self.device))
        out = self._pipe(text, truncation=True, max_length=self.max_length)
        scores = out[0] if out and isinstance(out[0], list) else out
        return float(next((d["score"] for d in scores if d["label"] == self.positive_label), 0.0))


class GlinerDetector:
    """GLiNER zero-shot NER for names and places; `labels` maps GLiNER label -> our label.

    GLiNER scores generic nouns ("Someone", "my family", "staff member", "ATM") as high as real
    names, so a span is dropped when its head word (last token, after leading `determiners`)
    is in `ignore`. A one-word span is its own head, which covers pronouns like "I".
    See docs/specs/fix-gliner-generic-nouns.md."""

    def __init__(
        self,
        model_name: str,
        labels: dict[str, str],
        threshold: float,
        device: str,
        ignore: list[str] | tuple[str, ...] = (),
        determiners: list[str] | tuple[str, ...] = (),
    ):
        self.model_name = model_name
        self.labels = labels
        self.threshold = threshold
        self.device = device
        self.ignore = frozenset(w.lower() for w in ignore)
        self.determiners = frozenset(w.lower() for w in determiners)
        self._model: Any = None

    def is_generic(self, span_text: str) -> bool:
        words = [w.strip(".,;:!?'\"()") for w in span_text.lower().split()]
        while words and words[0] in self.determiners:
            words.pop(0)
        return not words or words[-1] in self.ignore

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def detect(self, text: str) -> list[Span]:
        if self._model is None:
            self._model = _gliner(self.model_name, resolve_device(self.device))
        hits = self._model.predict_entities(text, list(self.labels), threshold=self.threshold)
        return [
            Span(start=h["start"], end=h["end"], label=self.labels[h["label"]], text=h["text"])
            for h in hits
            if h["label"] in self.labels and not self.is_generic(h["text"])
        ]


class EmbedLogRegClassifier:
    """Sentence embeddings + logistic regression, trained on first use from a YAML file
    of {category: [examples]}. `prob` is the winning class probability."""

    def __init__(self, embedding_model: str, train_path: Path, c: float, device: str) -> None:
        self.embedding_model = embedding_model
        self.train_path = train_path
        self.c = c
        self.device = device
        self._clf: Any = None
        self._encoder: Any = None

    @property
    def loaded(self) -> bool:
        return self._clf is not None

    def _embed(self, texts: list[str]) -> Any:
        return self._encoder.encode(texts, normalize_embeddings=True, convert_to_numpy=True)

    def _train(self) -> None:
        import yaml
        from sklearn.linear_model import LogisticRegression

        data = yaml.safe_load(self.train_path.read_text(encoding="utf-8"))
        texts = [t for items in data.values() for t in items]
        labels = [label for label, items in data.items() for _ in items]
        self._encoder = sentence_encoder(self.embedding_model, resolve_device(self.device))
        self._clf = LogisticRegression(C=self.c, max_iter=2000).fit(self._embed(texts), labels)

    def predict(self, text: str) -> tuple[str, float]:
        if self._clf is None:
            self._train()
        proba = self._clf.predict_proba(self._embed([text]))[0]
        best = int(proba.argmax())
        return str(self._clf.classes_[best]), float(proba[best])


# ---------- factories ----------


def _unknown(what: str, kind: str, allowed: list[str]) -> ValueError:
    return ValueError(f"unknown {what} {kind!r}; allowed: {', '.join(allowed)}")


def build_injection_scorer(config: dict[str, Any]) -> ScoreDetector:
    kind = config.get("classifier", "stub")
    if kind == "stub":
        return StubScorer()
    models = config.get("models", {})
    if kind not in models:
        raise _unknown("injection classifier", kind, ["stub", *models])
    m = models[kind]
    return HFInjectionScorer(
        m["name"], m["positive_label"], config.get("max_length", 512), config.get("device", "auto")
    )


_PII_ML_LABELS = ("PERSON", "LOCATION")


def build_pii_detector(config: dict[str, Any]) -> Detector:
    kind = config.get("backend", "stub")
    if kind == "stub":
        return StubDetector()
    if kind == "presidio":
        wanted = [x for x in config["labels"] if x in _PII_ML_LABELS]
        return PresidioDetector(config["spacy_model"], wanted)
    if kind == "gliner":
        g = config["gliner"]
        return GlinerDetector(
            g["name"],
            g["labels"],
            g["threshold"],
            g.get("device", "auto"),
            g.get("ignore", []),
            g.get("determiners", []),
        )
    raise _unknown("PII backend", kind, ["stub", "presidio", "gliner"])


def build_topic_classifier(config: dict[str, Any]) -> TopicClassifier:
    kind = config.get("classifier", "stub")
    if kind == "stub":
        return StubTopicClassifier()
    if kind == "embed_logreg":
        from guardbank.config import ROOT

        e = config["embed_logreg"]
        path = Path(e["train_path"])
        return EmbedLogRegClassifier(
            e["embedding_model"],
            path if path.is_absolute() else ROOT / path,
            float(e["C"]),
            e.get("device", "auto"),
        )
    raise _unknown("topic classifier", kind, ["stub", "embed_logreg"])
