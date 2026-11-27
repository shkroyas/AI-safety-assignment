"""Metric math (docs/specs/eval.md)."""

import pytest

from guardbank.evaluation.metrics import (
    binary_metrics,
    entity_metrics,
    multiclass_metrics,
    wilson,
)


def test_binary_counts_and_rates():
    rows = [("a", 1, 1), ("b", 1, 0), ("c", 0, 1), ("d", 0, 0), ("e", 1, 1)]
    m = binary_metrics(rows)
    assert (m["tp"], m["fp"], m["fn"], m["tn"]) == (2, 1, 1, 1)
    assert m["precision"] == pytest.approx(2 / 3)
    assert m["recall"] == pytest.approx(2 / 3)
    assert m["f1"] == pytest.approx(2 / 3)
    assert m["fpr"] == pytest.approx(1 / 2)
    assert m["fp_ids"] == ["c"] and m["fn_ids"] == ["b"]
    assert m["n"] == 5


def test_zero_denominators_are_null():
    m = binary_metrics([("a", 0, 0), ("b", 0, 0)])
    assert m["precision"] is None and m["recall"] is None and m["f1"] is None
    assert m["fpr"] == 0.0
    assert m["ci"]["recall"] is None
    m = binary_metrics([("a", 1, 1)])
    assert m["fpr"] is None and m["ci"]["fpr"] is None


def test_wilson_known_values():
    lo, hi = wilson(8, 10)
    assert lo == pytest.approx(0.490, abs=1e-3) and hi == pytest.approx(0.943, abs=1e-3)
    assert wilson(0, 0) is None
    lo, hi = wilson(0, 5)
    assert lo == 0.0 and 0 < hi < 1


def test_ci_present_for_rates():
    m = binary_metrics([("a", 1, 1), ("b", 1, 0), ("c", 0, 0)])
    assert m["ci"]["recall"] == pytest.approx(wilson(1, 2))
    assert m["ci"]["precision"] == pytest.approx(wilson(1, 1))
    assert m["ci"]["fpr"] == pytest.approx(wilson(0, 1))


def test_multiclass():
    rows = [("1", "A", "A"), ("2", "A", "B"), ("3", "B", "B"), ("4", "C", "C")]
    m = multiclass_metrics(rows, ["A", "B", "C"])
    assert m["accuracy"] == pytest.approx(3 / 4)
    assert m["per_class"]["A"]["recall"] == pytest.approx(1 / 2)
    assert m["per_class"]["B"]["precision"] == pytest.approx(1 / 2)
    f1s = [m["per_class"][c]["f1"] for c in "ABC"]
    assert m["macro_f1"] == pytest.approx(sum(f1s) / 3)
    assert m["confusion"]["A"]["B"] == 1


# ---------- entity-level PII (docs/specs/fix-entity-pii-metrics.md) ----------


def test_entity_metrics_label_bags():
    rows = [
        ("A", ["PERSON", "NP_PHONE"], ["NP_PHONE"]),  # missed second entity -> FN
        ("B", ["EMAIL"], ["EMAIL", "PERSON"]),  # extra entity -> FP
        ("C", ["LOCATION", "LOCATION"], ["LOCATION"]),  # duplicate label counted
        ("D", [], []),
    ]
    m = entity_metrics(rows)
    assert (m["tp"], m["fp"], m["fn"]) == (3, 1, 2)
    assert m["precision"] == pytest.approx(3 / 4)
    assert m["recall"] == pytest.approx(3 / 5)
    assert m["fp_entities"] == [["B", "PERSON"]]
    assert sorted(m["fn_entities"]) == [["A", "PERSON"], ["C", "LOCATION"]]
    assert m["per_label"]["LOCATION"] == {
        "tp": 1,
        "fp": 0,
        "fn": 1,
        "precision": 1.0,
        "recall": 0.5,
    }
    assert set(m["ci"]) == {"precision", "recall"}
