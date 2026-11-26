"""Invalid-response policy (SPEC §4, docs/specs/remediation-pipeline.md).

Holds the policy texts and limits from YAML, records the final decision of a request as a
`GuardResult` (stage "remediation"), and sanitises stage details before they are audited.
"""

from __future__ import annotations

from typing import Any

from guardbank.types import Action, GuardResult

STAGE = "remediation"

# Detail keys that carry user or model text; never written to the audit log.
_TEXT_KEYS = frozenset({"normalized", "decoded", "redacted", "decoded_redacted", "text", "reply"})


def audit_details(details: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in details.items() if k not in _TEXT_KEYS}
    if "claims" in out:
        out["claims"] = [
            {
                "score": round(c["score"], 4),
                "supported": c["supported"],
                "n_numbers_missing": len(c["numbers_missing"]),
            }
            for c in out["claims"]
        ]
    return out


class Remediation:
    def __init__(self, config: dict[str, Any]) -> None:
        self.max_schema_retries: int = config["max_schema_retries"]
        self.regenerate_instruction: str = config["regenerate_instruction"]
        self.strip_note: str = config["strip_note"]
        self.fallback_text: str = config["fallback_text"]
        self.block_text: str = config["block_text"]

    @classmethod
    def from_settings(cls, settings: Any) -> Remediation:
        return cls(settings.remediation)

    def strip(self, claims: list[dict[str, Any]]) -> str:
        kept = [c["text"] for c in claims if c["supported"]]
        return " ".join([*kept, self.strip_note])

    @staticmethod
    def decision(action: Action, reason: str, *, attempts: int, **details: Any) -> GuardResult:
        return GuardResult(
            stage=STAGE,
            detected=action != Action.ALLOW,
            score=0.0 if action == Action.ALLOW else 1.0,
            category=reason,
            action=action,
            latency_ms=0.0,
            details={"reason": reason, "attempts": attempts, **details},
        )
