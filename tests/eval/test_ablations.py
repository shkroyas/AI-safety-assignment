"""Ablations, sweeps and latency (docs/specs/eval-ablations.md). Fast: no model weights."""

import json

import pytest

from guardbank.cases import load_cases
from guardbank.evaluation.ablations import (
    best_tau,
    groundedness_variants,
    injection_variants,
    latency,
    percentile,
    run_ablations,
    sweep,
)

ROWS = [("a", 1, 0.9, {}), ("b", 1, 0.4, {}), ("c", 0, 0.6, {}), ("d", 0, 0.1, {})]


def _at_least(score, extra, tau):
    return score >= tau


def test_sweep_counts():
    out = {r["tau"]: r for r in sweep(ROWS, [0.3, 0.5], _at_least)}
    r = out[0.5]
    assert (r["tp"], r["fp"], r["fn"], r["tn"]) == (1, 1, 1, 1)
    assert r["precision"] == 0.5 and r["recall"] == 0.5 and r["fpr"] == 0.5
    r = out[0.3]
    assert (r["tp"], r["fp"], r["fn"], r["tn"]) == (2, 1, 0, 1)
    assert r["f1"] == pytest.approx(0.8)


def test_best_tau_max_f1_and_ties():
    rows = [{"tau": 0.3, "f1": 0.8}, {"tau": 0.5, "f1": 0.5}, {"tau": 0.7, "f1": 0.8}]
    assert best_tau(rows, current=0.75) == 0.7
    assert best_tau(rows, current=0.2) == 0.3
    assert best_tau([{"tau": 0.4, "f1": None}, {"tau": 0.6, "f1": 0.1}], current=0.4) == 0.6


def test_percentile():
    assert percentile([1, 2, 3, 4], 50) == pytest.approx(2.5)
    assert percentile([1, 2, 3, 4], 95) == pytest.approx(3.85)
    assert percentile([7], 95) == 7


def test_injection_variants(settings):
    v = injection_variants(settings)
    assert set(v) == {"regex", "classifier", "hybrid", "hybrid+pii-routing"}
    assert v["regex"].input["injection"]["classifier"] == "stub"
    assert v["classifier"].input["injection"]["patterns"] == {}
    assert v["classifier"].input["injection"]["classifier"] == "deberta"
    assert v["hybrid"].input["injection"]["classifier"] == "deberta"
    assert v["hybrid"].input["injection"]["patterns"]
    assert settings.input["injection"]["classifier"] == "stub"  # base untouched
    for name in ("regex", "classifier", "hybrid"):
        assert "classifier_with_pii" not in v[name].input["injection"], name
    routed = v["hybrid+pii-routing"].input["injection"]
    assert routed["classifier"] == "deberta" and routed["classifier_with_pii"] == "prompt_guard"


def test_groundedness_variants(settings):
    v = groundedness_variants(settings)
    g = {k: s.output["groundedness"] for k, s in v.items()}
    assert set(g) == {"keyword", "keyword+number", "nli", "nli+number"}
    assert (g["keyword"]["scorer"], g["keyword"]["number_check"]) == ("keyword", False)
    assert (g["keyword+number"]["scorer"], g["keyword+number"]["number_check"]) == ("keyword", True)
    assert (g["nli"]["scorer"], g["nli"]["number_check"]) == ("hhem", False)
    assert (g["nli+number"]["scorer"], g["nli+number"]["number_check"]) == ("hhem", True)


def test_latency_fast(settings, root):
    cases = load_cases(root / "tests" / "cases.yaml")[:6]
    lat = latency(settings, cases, repeats=1, warmup=1)
    assert lat["n"] == 6
    assert 0 <= lat["total"]["p50"] <= lat["total"]["p95"]
    for name in ("normalizer", "input_pii", "input_injection", "input_topic"):
        st = lat["stages"][name]
        assert 0 <= st["p50"] <= st["p95"]


def test_run_ablations_fast_writes_outputs(tmp_path):
    run_ablations("fast", tmp_path, charts=False, latency_modes=("fast",), repeats=1)
    for f in ("ablations.json", "sweeps.json", "latency.json", "tables.md"):
        assert (tmp_path / f).exists(), f
    abl = json.loads((tmp_path / "ablations.json").read_text())
    variants = {"regex", "classifier", "hybrid", "hybrid+pii-routing"}
    assert set(abl["injection"]) == variants
    assert set(abl["injection_pii"]) == variants
    assert set(abl["groundedness"]) == {"keyword", "keyword+number", "nli", "nli+number"}
    for part in ("dev", "test"):
        assert "f1" in abl["injection"]["regex"][part]
    sw = json.loads((tmp_path / "sweeps.json").read_text())
    for key in ("injection_tau", "tau_g_keyword"):
        assert sw[key]["dev_best"] is not None and sw[key]["current"] is not None
        assert "test_at_current" in sw[key] and "test_at_dev_best" in sw[key]
    assert "fast" in json.loads((tmp_path / "latency.json").read_text())["modes"]


def test_stubify_stubs_pii_classifier(settings):
    from guardbank.evaluation.ablations import _stubify

    v = injection_variants(settings)["hybrid+pii-routing"]
    assert _stubify(v).input["injection"]["classifier_with_pii"] == "stub"
