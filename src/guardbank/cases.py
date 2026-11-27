"""End-to-end case format and runner (SPEC §5, docs/specs/e2e-cases.md).

`run_case` drives one case through a `Pipeline` and checks its expectations. Output-side
cases script the LLM with `llm_output`; the templates `{cite}`, `{canary}` and `{grounded}`
are filled from the system prompt of each call, so cases never hard-code retrieval.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from guardbank.pipeline import Pipeline, PipelineResult, Session
from guardbank.rag.llm import LLMResponse, MockLLM

Category = Literal[
    "normal_input",
    "malicious_input",
    "sensitive_info",
    "sensitive_topic",
    "invalid_output",
    "unsupported_claim",
]
CATEGORY_PREFIX = {
    "normal_input": "NRM",
    "malicious_input": "INJ",
    "sensitive_info": "PII",
    "sensitive_topic": "TOP",
    "invalid_output": "SCH",
    "unsupported_claim": "GRD",
}
SPEC_MIN = {
    "normal_input": 8,
    "malicious_input": 8,
    "sensitive_info": 8,
    "sensitive_topic": 6,
    "invalid_output": 5,
    "unsupported_claim": 5,
}
# SPEC dotted stage name -> GuardResult.stage
STAGES = {
    "input.normalizer": "normalizer",
    "input.pii": "input_pii",
    "input.injection": "input_injection",
    "input.topic": "input_topic",
    "rag.chunk_scan": "chunk_scan",
    "output.schema": "output_schema",
    "output.groundedness": "output_groundedness",
    "output.leakage": "output_leakage",
    "remediation": "remediation",
}

_CANARY = re.compile(r"GB-CANARY-[0-9a-f]+")
_FIRST_ID = re.compile(r"^\[([a-z0-9-]+#\d+)\]", re.MULTILINE)


class Expected(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: str
    action: str
    outcome: str | None = None
    escalate: bool | None = None
    llm_calls: int | None = None
    text_contains: list[str] = Field(default_factory=list)
    text_excludes: list[str] = Field(default_factory=list)


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    category: Category
    input: str
    reference_docs: list[str] = Field(default_factory=list)
    llm_output: list[str] | None = None
    expected: Expected
    known_failure: str | None = None

    @field_validator("llm_output", mode="before")
    @classmethod
    def _as_list(cls, v: Any) -> Any:
        return [v] if isinstance(v, str) else v


class CaseResult(BaseModel):
    id: str
    passed: bool
    actual: dict[str, Any]
    reasons: list[str]
    text: str = ""  # the final reply the customer would see


def load_cases(path: str | Path) -> list[Case]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return [Case.model_validate(item) for item in data]


class CaseLLM(MockLLM):
    """Returns the case's scripted outputs in order (the last repeats), with templates filled."""

    def __init__(self, outputs: list[str]) -> None:
        super().__init__()
        self.outputs = outputs

    def generate(self, system, messages, *, temperature=None):
        n = len(self.calls)
        self.calls.append({"system": system, "messages": messages, "temperature": temperature})
        raw = self.outputs[min(n, len(self.outputs) - 1)]
        return LLMResponse(text=fill(raw, system), model="case", latency_ms=0.0)


def fill(raw: str, system: str) -> str:
    grounded = json.loads(MockLLM._grounded(system))["answer"]
    cite = _FIRST_ID.search(system)
    canary = _CANARY.search(system)
    return (
        raw.replace("{grounded}", json.dumps(grounded)[1:-1])  # JSON-escaped, quotes stripped
        .replace("{cite}", cite.group(1) if cite else "")
        .replace("{canary}", canary.group(0) if canary else "")
    )


def _actual(result: PipelineResult, stage: str) -> dict[str, Any]:
    first = next((s for s in result.stages if s.stage == stage), None)
    return {
        "stage": stage,
        "action": first.action.value if first else None,
        "outcome": result.outcome,
        "escalate": result.escalate,
        "llm_calls": result.llm_calls,
    }


def check(case: Case, result: PipelineResult) -> CaseResult:
    exp = case.expected
    actual = _actual(result, STAGES[exp.stage])
    reasons = []
    if actual["action"] is None:
        reasons.append(f"stage {exp.stage} never ran")
    elif actual["action"] != exp.action:
        reasons.append(f"{exp.stage}: expected action {exp.action}, got {actual['action']}")
    for key in ("outcome", "escalate", "llm_calls"):
        want = getattr(exp, key)
        if want is not None and actual[key] != want:
            reasons.append(f"{key}: expected {want}, got {actual[key]}")
    for s in exp.text_contains:
        if s not in result.text:
            reasons.append(f"text_contains: {s!r} missing from reply")
    for s in exp.text_excludes:
        if s in result.text:
            reasons.append(f"text_excludes: {s!r} found in reply")
    if case.reference_docs:
        scan = next((s for s in result.stages if s.stage == "chunk_scan"), None)
        kept = {cid.split("#")[0] for cid in scan.details["kept"]} if scan else set()
        if not kept & set(case.reference_docs):
            reasons.append(f"reference_docs: none of {case.reference_docs} in kept {sorted(kept)}")
    return CaseResult(
        id=case.id, passed=not reasons, actual=actual, reasons=reasons, text=result.text
    )


def run_case(pipeline: Pipeline, case: Case) -> CaseResult:
    """Run one case in a fresh session. A scripted LLM is swapped in for this case only."""
    original = pipeline.llm
    if case.llm_output:
        pipeline.llm = CaseLLM(case.llm_output)
    try:
        result = pipeline.run(case.input, Session())
    finally:
        pipeline.llm = original
    return check(case, result)
