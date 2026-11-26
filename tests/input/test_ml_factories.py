"""ML detector factories, no weights loaded (docs/specs/ml-input.md)."""

import copy

import pytest
import yaml

from guardbank.input.detectors import (
    EmbedLogRegClassifier,
    GlinerDetector,
    HFInjectionScorer,
    StubDetector,
    StubScorer,
    StubTopicClassifier,
    build_injection_scorer,
    build_pii_detector,
    build_topic_classifier,
)
from guardbank.input.injection import InjectionDetector
from guardbank.input.topics import TopicRouter


def _cfg(settings, section, **changes):
    cfg = copy.deepcopy(settings.input[section])
    cfg.update(changes)
    return cfg


def test_injection_stub_default(settings):
    assert isinstance(build_injection_scorer(settings.input["injection"]), StubScorer)


@pytest.mark.parametrize(
    ("kind", "name", "label"),
    [
        ("deberta", "protectai/deberta-v3-base-prompt-injection-v2", "INJECTION"),
        ("prompt_guard", "meta-llama/Llama-Prompt-Guard-2-86M", "LABEL_1"),
    ],
)
def test_injection_models_build_lazily(settings, kind, name, label):
    cfg = _cfg(settings, "injection", classifier=kind)
    scorer = build_injection_scorer(cfg)
    assert isinstance(scorer, HFInjectionScorer)
    assert scorer.model_name == name
    assert scorer.positive_label == label
    assert scorer.loaded is False
    assert isinstance(InjectionDetector(cfg).classifier, HFInjectionScorer)


def test_pii_backends(settings):
    assert isinstance(build_pii_detector(settings.input["pii"]), StubDetector)
    det = build_pii_detector(_cfg(settings, "pii", backend="gliner"))
    assert isinstance(det, GlinerDetector)
    assert det.model_name == "urchade/gliner_multi_pii-v1"
    assert det.loaded is False


def test_topic_classifier_builds_lazily(settings):
    assert isinstance(build_topic_classifier(settings.input["topics"]), StubTopicClassifier)
    cfg = _cfg(settings, "topics", classifier="embed_logreg")
    clf = build_topic_classifier(cfg)
    assert isinstance(clf, EmbedLogRegClassifier)
    assert clf.loaded is False
    assert isinstance(TopicRouter(cfg).classifier, EmbedLogRegClassifier)


@pytest.mark.parametrize(
    ("section", "key", "builder"),
    [
        ("injection", "classifier", build_injection_scorer),
        ("pii", "backend", build_pii_detector),
        ("topics", "classifier", build_topic_classifier),
    ],
)
def test_unknown_kind_raises(settings, section, key, builder):
    with pytest.raises(ValueError, match="allowed"):
        builder(_cfg(settings, section, **{key: "nope"}))


def test_topic_training_set(settings, root):
    cfg = settings.input["topics"]["embed_logreg"]
    data = yaml.safe_load((root / cfg["train_path"]).read_text(encoding="utf-8"))
    assert set(data) == set(settings.input["topics"]["routes"])
    texts = [t for items in data.values() for t in items]
    assert len(texts) == len(set(t.lower() for t in texts))
    for label, items in data.items():
        assert len(items) >= 10, label


def test_chunk_scan_classifier_is_its_own_setting(settings):
    from guardbank.rag.chunk_scan import ChunkScanner

    s = copy.deepcopy(settings)
    s.input["injection"]["classifier"] = "deberta"
    assert isinstance(ChunkScanner.from_settings(s).detector.classifier, StubScorer)
    s.rag["chunk_scan"]["classifier"] = "deberta"
    assert isinstance(ChunkScanner.from_settings(s).detector.classifier, HFInjectionScorer)
