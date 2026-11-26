"""MCP server exposing the guardrails as tools for Claude Code (SPEC §9, docs/specs/api-mcp.md).

Registered as `guardbank` in .mcp.json. Runs on stdio with the fast (stub) settings and MockLLM,
so red-teaming from Claude Code needs no keys and never calls the hosted model.
"""

from __future__ import annotations

import functools
import tempfile
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer

from guardbank.audit import AuditLog
from guardbank.cases import load_cases
from guardbank.cases import run_case as _run_case
from guardbank.config import DEFAULT_CONFIG, ROOT, load_settings
from guardbank.input.injection import InjectionDetector
from guardbank.input.normalizer import Normalizer
from guardbank.input.pii import PiiRedactor, PiiVault
from guardbank.input.topics import TopicRouter
from guardbank.output.groundedness import GroundednessChecker
from guardbank.output.leakage import LeakageChecker
from guardbank.output.schema import SchemaGuard
from guardbank.pipeline import Pipeline
from guardbank.rag.llm import MockLLM
from guardbank.remediation import audit_details, public_report
from guardbank.types import Action, GuardResult

server = MCPServer(
    "guardbank",
    instructions="Guardrails of the fictional Sagarmatha Digital Bank assistant. "
    "check_input / check_output run single stages; run_case runs an end-to-end case.",
)
# Worst first, for the check_output verdict.
_SEVERITY = [Action.BLOCK, Action.FALLBACK, Action.REGENERATE, Action.REDACT, Action.ALLOW]


@functools.cache
def _settings():
    return load_settings(DEFAULT_CONFIG, env={})


@functools.cache
def _pipeline() -> Pipeline:
    audit = AuditLog(Path(tempfile.mkdtemp(prefix="guardbank-mcp-")) / "audit.jsonl")
    return Pipeline.from_settings(_settings(), llm=MockLLM(), audit=audit)


def _stages(results: list[GuardResult]) -> list[dict[str, Any]]:
    return [
        {**entry, "details": audit_details(r.details)}
        for entry, r in zip(public_report(results), results, strict=True)
    ]


@server.tool()
def check_input(text: str) -> dict[str, Any]:
    """Run the input guardrails (normalizer, PII, injection, topic router) on one message."""
    s = _settings()
    norm = Normalizer.from_settings(s).check(text)
    pii = PiiRedactor.from_settings(s).check(
        norm.details["normalized"], PiiVault(), decoded=norm.details["decoded"]
    )
    results = [norm, pii]
    inj = InjectionDetector.from_settings(s).check(
        norm.details["normalized"], decoded=norm.details["decoded"]
    )
    results.append(inj)
    verdict = "block" if inj.action == Action.BLOCK else "allow"
    if verdict == "allow":
        topic = TopicRouter.from_settings(s).check(pii.details["redacted"])
        results.append(topic)
        if topic.action != Action.ALLOW and topic.details["route"] != "answer":
            verdict = "block" if topic.action == Action.BLOCK else "route"
    return {
        "verdict": verdict,
        "redacted_text": pii.details["redacted"],
        "stages": _stages(results),
    }


@server.tool()
def check_output(
    raw_llm_output: str, retrieved: dict[str, str], canary: str = ""
) -> dict[str, Any]:
    """Run the output guardrails on a raw LLM reply: schema, then leakage and groundedness."""
    s = _settings()
    results = [SchemaGuard.from_settings(s).check(raw_llm_output, list(retrieved))]
    if results[0].action == Action.ALLOW:
        reply = results[0].details["reply"]
        canary = canary or s.output["leakage"]["canary_prefix"]
        context = "\n\n".join(f"[{cid}] {text}" for cid, text in retrieved.items())
        leak = LeakageChecker.from_settings(s).check(reply.answer, PiiVault(), canary, context)
        results.append(leak)
        if leak.action != Action.BLOCK:
            results.append(GroundednessChecker.from_settings(s).check(reply, retrieved))
    worst = min((r.action for r in results), key=_SEVERITY.index)
    return {"verdict": worst.value, "stages": _stages(results)}


@server.tool()
def run_case(case_id: str) -> dict[str, Any]:
    """Run one end-to-end case from tests/cases.yaml through the pipeline (MockLLM)."""
    cases = {c.id: c for c in load_cases(ROOT / "tests" / "cases.yaml")}
    if case_id not in cases:
        return {"error": f"unknown case id {case_id!r}; known: {', '.join(sorted(cases))}"}
    return _run_case(_pipeline(), cases[case_id]).model_dump()


if __name__ == "__main__":
    server.run("stdio")
