"""Injection runner passes redacted text (docs/specs/fix-injection-pii-refusals.md)."""

import guardbank.input.injection as injection_mod
from guardbank.evaluation.datasets import TextItem
from guardbank.evaluation.runners import run_injection


class DigitScorer:
    def score(self, text):
        return 1.0 if any(c.isdigit() for c in text) else 0.0


def test_run_injection_uses_redacted_text(settings, monkeypatch):
    monkeypatch.setattr(injection_mod, "build_injection_scorer", lambda cfg: DigitScorer())
    items = [
        TextItem(id="A", text="My OTP is 482913, it did not arrive in time.", label=0, kind="t"),
        TextItem(id="B", text="Is the 1660 line open on Saturday?", label=0, kind="t"),
    ]
    preds = {p.id: p.pred for p in run_injection(items, settings)}
    assert preds == {"A": 0, "B": 1}
