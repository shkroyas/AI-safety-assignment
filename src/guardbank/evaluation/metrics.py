"""Detection metrics with Wilson 95% intervals. Zero denominators give None, never a fake 0 or 1."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable
from typing import Any

Z95 = 1.959963984540054


def wilson(k: int, n: int, z: float = Z95) -> list[float] | None:
    if n == 0:
        return None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    lo = 0.0 if k == 0 else max(0.0, centre - margin)
    hi = 1.0 if k == n else min(1.0, centre + margin)
    return [lo, hi]


def _ratio(a: int, b: int) -> float | None:
    return a / b if b else None


def binary_metrics(rows: Iterable[tuple[str, int, int]]) -> dict[str, Any]:
    """rows: (id, label, prediction) with 1 = positive (attack / leak / unsupported / fires)."""
    tp = fp = fn = tn = 0
    fp_ids: list[str] = []
    fn_ids: list[str] = []
    for item_id, label, pred in rows:
        if label and pred:
            tp += 1
        elif label:
            fn += 1
            fn_ids.append(item_id)
        elif pred:
            fp += 1
            fp_ids.append(item_id)
        else:
            tn += 1
    precision, recall = _ratio(tp, tp + fp), _ratio(tp, tp + fn)
    if precision is None or recall is None:
        f1 = None
    else:
        f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    return {
        "n": tp + fp + fn + tn,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "fpr": _ratio(fp, fp + tn),
        "ci": {
            "precision": wilson(tp, tp + fp),
            "recall": wilson(tp, tp + fn),
            "fpr": wilson(fp, fp + tn),
        },
        "fp_ids": fp_ids,
        "fn_ids": fn_ids,
    }


def multiclass_metrics(rows: list[tuple[str, str, str]], classes: list[str]) -> dict[str, Any]:
    """rows: (id, gold, predicted). One-vs-rest metrics per class, macro F1, confusion matrix."""
    per_class = {
        c: binary_metrics((i, int(g == c), int(p == c)) for i, g, p in rows) for c in classes
    }
    f1s = [m["f1"] for m in per_class.values() if m["f1"] is not None]
    confusion = {g: {p: 0 for p in classes} for g in classes}
    for _, g, p in rows:
        confusion[g][p] += 1
    return {
        "n": len(rows),
        "accuracy": _ratio(sum(g == p for _, g, p in rows), len(rows)),
        "macro_f1": sum(f1s) / len(f1s) if f1s else None,
        "per_class": per_class,
        "confusion": confusion,
    }


def entity_metrics(rows: Iterable[tuple[str, list[str], list[str]]]) -> dict[str, Any]:
    """Entity-level PII scoring over label bags: rows are (id, expected labels, found labels).

    A missed second entity is a false negative and an extra entity a false positive, which the
    message-level metric hides (docs/specs/fix-entity-pii-metrics.md). Labels, not spans.
    """
    tp = fp = fn = 0
    fp_entities: list[list[str]] = []
    fn_entities: list[list[str]] = []
    per: dict[str, Counter] = {}
    for item_id, expected, found in rows:
        want, got = Counter(expected), Counter(found)
        hit = want & got
        for label in set(want) | set(got):
            c = per.setdefault(label, Counter())
            c["tp"] += hit[label]
            c["fp"] += got[label] - hit[label]
            c["fn"] += want[label] - hit[label]
        tp += sum(hit.values())
        fp += sum((got - hit).values())
        fn += sum((want - hit).values())
        fp_entities += [[item_id, label] for label in sorted((got - hit).elements())]
        fn_entities += [[item_id, label] for label in sorted((want - hit).elements())]
    precision, recall = _ratio(tp, tp + fp), _ratio(tp, tp + fn)
    if precision is None or recall is None:
        f1 = None
    else:
        f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    per_label = {
        label: {
            "tp": c["tp"],
            "fp": c["fp"],
            "fn": c["fn"],
            "precision": _ratio(c["tp"], c["tp"] + c["fp"]),
            "recall": _ratio(c["tp"], c["tp"] + c["fn"]),
        }
        for label, c in sorted(per.items())
    }
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "ci": {"precision": wilson(tp, tp + fp), "recall": wilson(tp, tp + fn)},
        "fp_entities": fp_entities,
        "fn_entities": fn_entities,
        "per_label": per_label,
    }
