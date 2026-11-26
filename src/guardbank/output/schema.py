"""Response schema the LLM must follow, and the guard that checks it (SPEC §4).

`SchemaGuard` runs: optional code-fence strip -> JSON parse -> Pydantic -> citation-exists.
See docs/specs/output-schema.md.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Iterable
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from guardbank.types import Action, GuardResult

Intent = Literal["account", "cards", "loans", "fees", "kyc", "complaint", "other"]


class SupportReply(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1, max_length=1200)
    citations: list[str] = Field(description="Chunk ids from the context, e.g. 'atm-cards#1'")
    intent: Intent
    confidence: float = Field(ge=0.0, le=1.0)
    escalate: bool
    refusal_reason: str | None = None

    @model_validator(mode="after")
    def _rules(self) -> SupportReply:
        if not self.citations and self.refusal_reason is None:
            raise ValueError("citations must be non-empty unless refusal_reason is set")
        if self.intent == "complaint" and not self.escalate:
            raise ValueError("escalate must be true when intent is 'complaint'")
        return self


STAGE = "output_schema"
_FENCE = re.compile(r"^\s*```(?:json)?[ \t]*\n?(.*?)\n?[ \t]*```\s*$", re.DOTALL)
_CHUNK_ID = re.compile(r"^[a-z0-9-]+#\d+$")


def _safe_id(cid: Any) -> str:
    """Echo a cited id only if it looks like a chunk id, so model text never lands in logs."""
    return cid if isinstance(cid, str) and _CHUNK_ID.fullmatch(cid) else "<invalid id>"


class SchemaGuard:
    def __init__(self, config: dict[str, Any]) -> None:
        self.strip_code_fence: bool = bool(config.get("strip_code_fence", True))

    @classmethod
    def from_settings(cls, settings: Any) -> SchemaGuard:
        return cls(settings.output["schema"])

    def check(self, raw: str, retrieved_ids: Iterable[str]) -> GuardResult:
        t0 = time.perf_counter()
        text, fenced = raw, False
        if self.strip_code_fence and (m := _FENCE.match(raw)):
            text, fenced = m.group(1), True

        category, errors, reply = self._validate(text, set(retrieved_ids))
        latency_ms = (time.perf_counter() - t0) * 1000
        if category is None:
            return GuardResult.allow(STAGE, latency_ms=latency_ms, reply=reply, fenced=fenced)
        return GuardResult(
            stage=STAGE,
            detected=True,
            score=1.0,
            category=category,
            action=Action.REGENERATE,
            latency_ms=latency_ms,
            details={
                "errors": errors,
                "feedback": "Your previous reply was rejected: "
                + "; ".join(errors)
                + ". Reply again with only a JSON object that follows the schema.",
                "fenced": fenced,
            },
        )

    @staticmethod
    def _validate(
        text: str, retrieved: set[str]
    ) -> tuple[str | None, list[str], SupportReply | None]:
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as e:
            return "JSON_INVALID", [f"not valid JSON ({e.msg} at char {e.pos})"], None
        if not isinstance(obj, dict):
            return "JSON_INVALID", [f"expected a JSON object, got {type(obj).__name__}"], None

        try:
            reply = SupportReply.model_validate(obj)
        except ValidationError as e:
            errs = e.errors(include_input=False, include_url=False)
            # The model-level validator (empty loc) only runs once every field is valid.
            if all(not err["loc"] for err in errs):
                msgs = [str(err["msg"]).removeprefix("Value error, ") for err in errs]
                return "RULE_VIOLATION", msgs, None
            msgs = [f"{'.'.join(map(str, err['loc'])) or 'reply'}: {err['msg']}" for err in errs]
            return "SCHEMA_INVALID", msgs, None

        unknown = [c for c in reply.citations if c not in retrieved]
        if unknown:
            ids = ", ".join(_safe_id(c) for c in unknown)
            return "CITATION_MISSING", [f"citations not in the retrieved context: {ids}"], None
        return None, [], reply
