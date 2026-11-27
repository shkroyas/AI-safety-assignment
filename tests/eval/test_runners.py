"""Injection runner applies the same PII routing as the pipeline (docs/specs/fix-injection-pii-refusals.md)."""

import copy

import guardbank.input.injection as injection_mod
from guardbank.evaluation.datasets import TextItem
from guardbank.evaluation.runners import run_injection


class Fixed:
    def __init__(self, v):
        self.v = v

    def score(self, text):
        return self.v


def test_run_injection_routes_by_pii(settings, monkeypatch):
    s = copy.deepcopy(settings)
    s.input["injection"]["classifier"] = "hi"
    s.input["injection"]["classifier_with_pii"] = "lo"
    monkeypatch.setattr(
        injection_mod,
        "build_injection_scorer",
        lambda cfg: Fixed(1.0 if cfg["classifier"] == "hi" else 0.0),
    )
    items = [
        TextItem(id="A", text="My OTP is 482913, it did not arrive in time.", label=0, kind="t"),
        TextItem(id="B", text="What are the branch opening hours?", label=0, kind="t"),
    ]
    preds = {p.id: p.pred for p in run_injection(items, s)}
    assert preds == {"A": 0, "B": 1}
