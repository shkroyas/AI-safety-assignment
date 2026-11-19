import json

import pytest
from pydantic import ValidationError

from guardbank.types import Action, GuardResult, Span


def test_guard_result_round_trips_to_json():
    result = GuardResult(
        stage="input.pii",
        detected=True,
        score=0.93,
        spans=[Span(start=0, end=10, label="NP_MOBILE", text="9841234567")],
        category="pii",
        action=Action.REDACT,
        latency_ms=1.5,
        details={"count": 1},
    )
    data = json.loads(result.model_dump_json())
    assert data["action"] == "redact"
    assert GuardResult.model_validate(data) == result


def test_all_spec_actions_exist():
    assert {a.value for a in Action} == {
        "allow", "redact", "block", "route", "drop_chunk", "regenerate", "fallback",
    }


def test_invalid_action_rejected():
    with pytest.raises(ValidationError):
        GuardResult(stage="x", detected=False, score=0.0, action="explode", latency_ms=0.0)


def test_score_must_be_between_0_and_1():
    with pytest.raises(ValidationError):
        GuardResult(stage="x", detected=False, score=1.5, action="allow", latency_ms=0.0)


def test_allow_helper():
    r = GuardResult.allow("input.injection", latency_ms=0.2)
    assert not r.detected and r.action is Action.ALLOW and r.score == 0.0
