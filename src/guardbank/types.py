"""Shared result type returned by every guardrail (SPEC §1)."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Action(StrEnum):
    ALLOW = "allow"
    REDACT = "redact"
    BLOCK = "block"
    ROUTE = "route"
    DROP_CHUNK = "drop_chunk"
    REGENERATE = "regenerate"
    FALLBACK = "fallback"


class Span(BaseModel):
    model_config = ConfigDict(frozen=True)

    start: int = Field(ge=0)
    end: int = Field(ge=0)
    label: str
    text: str = ""


class GuardResult(BaseModel):
    """Verdict of one guardrail stage. Read by the pipeline, tests, eval and audit log."""

    stage: str
    detected: bool
    score: float = Field(ge=0.0, le=1.0)
    spans: list[Span] = Field(default_factory=list)
    category: str | None = None
    action: Action
    latency_ms: float = Field(ge=0.0)
    details: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def allow(cls, stage: str, *, latency_ms: float, **details: Any) -> GuardResult:
        return cls(
            stage=stage,
            detected=False,
            score=0.0,
            action=Action.ALLOW,
            latency_ms=latency_ms,
            details=details,
        )
