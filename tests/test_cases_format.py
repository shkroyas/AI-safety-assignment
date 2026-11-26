"""Format of tests/cases.yaml and the case runner (SPEC §5, docs/specs/e2e-cases.md)."""

import re
from collections import Counter

import pytest

from guardbank.cases import (
    CATEGORY_PREFIX,
    SPEC_MIN,
    STAGES,
    Case,
    load_cases,
    run_case,
)
from guardbank.pipeline import Pipeline
from guardbank.rag.llm import MockLLM

OUTPUT_SIDE = {"invalid_output", "unsupported_claim"}


@pytest.fixture(scope="module")
def cases(request):
    return load_cases(request.config.rootpath / "tests" / "cases.yaml")


@pytest.fixture
def pipeline(settings, tmp_path):
    from guardbank.audit import AuditLog

    return Pipeline.from_settings(settings, llm=MockLLM(), audit=AuditLog(tmp_path / "a.jsonl"))


def test_spec_counts(cases):
    counts = Counter(c.category for c in cases)
    for category, minimum in SPEC_MIN.items():
        assert counts[category] >= minimum, category
    assert len(cases) >= 40


def test_ids_unique_and_prefixed(cases):
    ids = [c.id for c in cases]
    assert len(ids) == len(set(ids))
    for c in cases:
        assert re.fullmatch(rf"{CATEGORY_PREFIX[c.category]}-\d{{2}}", c.id), c.id


def test_stage_names_valid(cases):
    for c in cases:
        assert c.expected.stage in STAGES, c.id


def test_output_side_cases_script_the_llm(cases):
    for c in cases:
        if c.category in OUTPUT_SIDE:
            assert c.llm_output, c.id


def _luhn(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch) * (2 if i % 2 else 1)
        total += d - 9 if d > 9 else d
    return total % 10 == 0


def test_only_test_card_numbers(cases):
    for c in cases:
        blob = c.input + " ".join(c.llm_output or [])
        for m in re.finditer(r"\d(?:[ -]?\d){12,18}", blob):
            digits = re.sub(r"\D", "", m.group(0))
            if _luhn(digits):
                assert digits.startswith("4111"), c.id


def _case(**kw):
    data = {
        "id": "NRM-99",
        "category": "normal_input",
        "input": "What is the daily ATM withdrawal limit?",
        "expected": {"stage": "remediation", "action": "allow", "outcome": "answered"},
    }
    data.update(kw)
    return Case.model_validate(data)


def test_runner_pass_and_fail(pipeline):
    ok = run_case(pipeline, _case())
    assert ok.passed is True and ok.reasons == []
    assert ok.actual["outcome"] == "answered" and ok.actual["action"] == "allow"
    bad = run_case(
        pipeline,
        _case(expected={"stage": "input.injection", "action": "block", "llm_calls": 0}),
    )
    assert bad.passed is False
    assert any("input.injection" in r for r in bad.reasons)
    assert any("llm_calls" in r for r in bad.reasons)


def test_runner_templates(pipeline):
    raw = (
        '{"answer": "{grounded}", "citations": ["{cite}"], "intent": "cards",'
        ' "confidence": 0.9, "escalate": false, "refusal_reason": null}'
    )
    r = run_case(pipeline, _case(llm_output=raw))
    assert r.passed, r.reasons
    leak = run_case(
        pipeline,
        _case(
            llm_output=raw.replace("{grounded}", "{grounded} Ref {canary}."),
            expected={"stage": "output.leakage", "action": "block", "outcome": "blocked"},
        ),
    )
    assert leak.passed, leak.reasons
    assert isinstance(pipeline.llm, MockLLM)  # the scripted LLM is swapped back out


def test_reference_docs_checked(pipeline):
    assert run_case(pipeline, _case(reference_docs=["atm-cards"])).passed
    miss = run_case(pipeline, _case(reference_docs=["home-loans"]))
    assert not miss.passed
    assert any("reference_docs" in r for r in miss.reasons)
