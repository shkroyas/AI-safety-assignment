"""Named fault injectors for the schema guard (docs/specs/output-schema.md).

Each entry maps a fault name to (inject, expected category). `inject` takes a valid
reply dict and returns the raw text a misbehaving model might send. The eval feeds these
through `MockLLM(scripted=...)`.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

Inject = Callable[[dict[str, Any]], str]


def _set(**changes: Any) -> Inject:
    return lambda d: json.dumps({**d, **changes})


def _drop(field: str) -> Inject:
    return lambda d: json.dumps({k: v for k, v in d.items() if k != field})


FAULTS: dict[str, tuple[Inject, str]] = {
    "not_json": (lambda d: f"Sure! {d['answer']}", "JSON_INVALID"),
    "truncated": (lambda d: json.dumps(d)[:-15], "JSON_INVALID"),
    "json_array": (lambda d: json.dumps([d]), "JSON_INVALID"),
    "missing_field": (_drop("intent"), "SCHEMA_INVALID"),
    "extra_field": (_set(note="extra"), "SCHEMA_INVALID"),
    "bad_intent": (_set(intent="mortgage"), "SCHEMA_INVALID"),
    "confidence_high": (_set(confidence=1.5), "SCHEMA_INVALID"),
    "confidence_negative": (_set(confidence=-0.1), "SCHEMA_INVALID"),
    "wrong_type": (_set(confidence="high"), "SCHEMA_INVALID"),
    "empty_answer": (_set(answer=""), "SCHEMA_INVALID"),
    "answer_too_long": (_set(answer="x" * 1201), "SCHEMA_INVALID"),
    "empty_citations": (_set(citations=[], refusal_reason=None), "RULE_VIOLATION"),
    "complaint_no_escalate": (_set(intent="complaint", escalate=False), "RULE_VIOLATION"),
    "unknown_citation": (_set(citations=["made-up-doc#7"]), "CITATION_MISSING"),
}
