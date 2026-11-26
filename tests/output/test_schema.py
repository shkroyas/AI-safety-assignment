"""Output schema guard + fault injection (SPEC §4 schema row, docs/specs/output-schema.md)."""

import copy
import json

import pytest

from guardbank.output.faults import FAULTS
from guardbank.output.schema import SchemaGuard, SupportReply
from guardbank.rag.llm import MockLLM
from guardbank.types import Action, GuardResult

RETRIEVED = ["atm-cards#1", "card-blocking#2"]

VALID = {
    "answer": "The daily ATM withdrawal limit is NPR 25,000.",
    "citations": ["atm-cards#1"],
    "intent": "cards",
    "confidence": 0.9,
    "escalate": False,
    "refusal_reason": None,
}


@pytest.fixture
def guard(settings) -> SchemaGuard:
    return SchemaGuard.from_settings(settings)


def test_valid_reply_allowed(guard):
    r = guard.check(json.dumps(VALID), RETRIEVED)
    assert isinstance(r, GuardResult)
    assert r.stage == "output_schema"
    assert r.detected is False
    assert r.action == Action.ALLOW
    assert isinstance(r.details["reply"], SupportReply)
    assert r.details["reply"].citations == ["atm-cards#1"]
    assert r.details["fenced"] is False


def test_refusal_without_citations_allowed(guard):
    refusal = {**VALID, "citations": [], "refusal_reason": "no_context", "confidence": 0.0}
    assert guard.check(json.dumps(refusal), RETRIEVED).action == Action.ALLOW


def test_fault_catalogue_covers_spec():
    assert set(FAULTS) == {
        "not_json",
        "truncated",
        "json_array",
        "missing_field",
        "extra_field",
        "bad_intent",
        "confidence_high",
        "confidence_negative",
        "wrong_type",
        "empty_answer",
        "answer_too_long",
        "empty_citations",
        "complaint_no_escalate",
        "unknown_citation",
    }


@pytest.mark.parametrize("name", sorted(FAULTS))
def test_fault_detected(guard, name):
    inject, expected = FAULTS[name]
    r = guard.check(inject(copy.deepcopy(VALID)), RETRIEVED)
    assert r.detected is True
    assert r.score == 1.0
    assert r.action == Action.REGENERATE
    assert r.category == expected
    assert r.details["errors"]
    assert "reply" not in r.details


def test_errors_do_not_echo_raw(guard):
    secret = "GB-CANARY-deadbeef"
    raw = json.dumps({**VALID, "intent": secret})
    r = guard.check(raw, RETRIEVED)
    assert r.category == "SCHEMA_INVALID"
    blob = json.dumps(r.details)
    assert secret not in blob


def test_feedback_names_field(guard):
    r = guard.check(json.dumps({**VALID, "confidence": 3}), RETRIEVED)
    assert "confidence" in r.details["feedback"]
    r = guard.check(json.dumps({**VALID, "citations": ["nope#9"]}), RETRIEVED)
    assert r.category == "CITATION_MISSING"
    assert "nope#9" in r.details["feedback"]


def test_code_fence_stripped(guard):
    raw = "```json\n" + json.dumps(VALID) + "\n```"
    r = guard.check(raw, RETRIEVED)
    assert r.action == Action.ALLOW
    assert r.details["fenced"] is True


def test_fence_strip_off_by_config(settings):
    cfg = copy.deepcopy(settings.output["schema"])
    cfg["strip_code_fence"] = False
    r = SchemaGuard(cfg).check("```json\n" + json.dumps(VALID) + "\n```", RETRIEVED)
    assert r.category == "JSON_INVALID"


def test_mockllm_scripted_fault_roundtrip(guard):
    inject, expected = FAULTS["unknown_citation"]
    llm = MockLLM(scripted=[inject(copy.deepcopy(VALID)), json.dumps(VALID)])
    first = guard.check(llm.generate("sys", []).text, RETRIEVED)
    second = guard.check(llm.generate("sys", []).text, RETRIEVED)
    assert first.category == expected
    assert second.action == Action.ALLOW
