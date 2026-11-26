"""Run every end-to-end case in tests/cases.yaml (SPEC §5, docs/specs/e2e-cases.md).

Fast mode: stub detectors, hashing embedder, MockLLM. A case with `known_failure` is a
documented real miss and runs as a strict xfail, so a fix shows up as XPASS.
"""

import os
from pathlib import Path

import pytest

from guardbank.audit import AuditLog
from guardbank.cases import load_cases, run_case
from guardbank.pipeline import Pipeline
from guardbank.rag.llm import MockLLM

CASES = load_cases(Path(__file__).parent / "cases.yaml")


def _param(case):
    marks = (
        [pytest.mark.xfail(strict=True, reason=case.known_failure)] if case.known_failure else []
    )
    return pytest.param(case, id=case.id, marks=marks)


@pytest.fixture(scope="module")
def pipeline(tmp_path_factory):
    from guardbank.config import load_settings

    s = load_settings(Path(__file__).parents[1] / "config" / "guardrails.yaml", env={})
    audit = AuditLog(tmp_path_factory.mktemp("e2e") / "audit.jsonl")
    return Pipeline.from_settings(s, llm=MockLLM(), audit=audit)


@pytest.mark.parametrize("case", [_param(c) for c in CASES])
def test_case(pipeline, case):
    result = run_case(pipeline, case)
    assert result.passed, result.reasons


@pytest.mark.live
@pytest.mark.skipif(
    not (os.environ.get("HOSTED_PROVIDER") and os.environ.get("BEDROCK_API_KEYS")),
    reason="live run needs Bedrock credentials in the environment",
)
@pytest.mark.parametrize("case", [_param(c) for c in CASES if not c.llm_output])
def test_cases_live(case, tmp_path):
    from guardbank.config import load_settings
    from guardbank.rag.llm import build_llm

    s = load_settings(Path(__file__).parents[1] / "config" / "guardrails.yaml", env=os.environ)
    p = Pipeline.from_settings(
        s, llm=build_llm(s, os.environ), audit=AuditLog(tmp_path / "audit.jsonl")
    )
    result = run_case(p, case)
    assert result.passed, result.reasons
