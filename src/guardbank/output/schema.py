"""Response schema the LLM must follow (SPEC §4).

The model only; validation stages (citation existence, fault handling) are added in
feat/output-guardrails.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
