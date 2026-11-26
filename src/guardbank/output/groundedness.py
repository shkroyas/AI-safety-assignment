"""Groundedness check (SPEC §4 groundedness row, docs/specs/output-groundedness.md).

Split the answer into claims; score each against the cited chunks (keyword or HHEM);
require every number, percentage and date in a claim to appear in that evidence.
"""

from __future__ import annotations

import re
import time
from typing import Any

from guardbank.output.facts import extract_facts
from guardbank.output.schema import SupportReply
from guardbank.output.scorers import ClaimScorer, build_claim_scorer
from guardbank.types import Action, GuardResult

STAGE = "output_groundedness"

_SENT_END = re.compile(r"[.!?]+\s+|\n+")
_ABBREV = frozenset({"rs", "no", "mr", "mrs", "dr", "st", "e.g", "i.e", "approx"})


def split_claims(answer: str) -> list[str]:
    """Split on sentence ends and line breaks; abbreviations like "Rs." do not end a sentence."""
    claims, start = [], 0
    for m in _SENT_END.finditer(answer):
        before = answer[start : m.start()].split()
        if m.group(0).startswith(".") and before and before[-1].lower().rstrip(".") in _ABBREV:
            continue
        claims.append(answer[start : m.end()].strip())
        start = m.end()
    claims.append(answer[start:].strip())
    return [c for c in claims if c]


class GroundednessChecker:
    def __init__(self, config: dict[str, Any], scorer: ClaimScorer | None = None) -> None:
        kind = config.get("scorer", "keyword")
        # A model scorer brings its own calibrated tau_g (docs/specs/ml-output.md).
        self.tau_g: float = config.get(kind, {}).get("tau_g", config["tau_g"])
        self.number_check: bool = bool(config["number_check"])
        self.fallback_below: float = config["fallback_below"]
        self.scorer = scorer or build_claim_scorer(config)

    @classmethod
    def from_settings(cls, settings: Any) -> GroundednessChecker:
        return cls(settings.output["groundedness"])

    def check(self, reply: SupportReply, chunks: dict[str, str]) -> GuardResult:
        t0 = time.perf_counter()

        def result(action: Action, category: str | None, score: float, **details: Any):
            return GuardResult(
                stage=STAGE,
                detected=action != Action.ALLOW,
                score=score,
                category=category,
                action=action,
                latency_ms=(time.perf_counter() - t0) * 1000,
                details=details,
            )

        if reply.refusal_reason is not None:
            return result(Action.ALLOW, None, 0.0, skipped="refusal")
        cited = [chunks[c] for c in reply.citations if c in chunks]
        if not cited:
            return result(Action.FALLBACK, "NO_CITATIONS", 1.0, support=0.0, claims=[])

        ev_set = set(extract_facts("\n".join(cited))[0])
        claims = []
        for text in split_claims(reply.answer):
            facts, _ = extract_facts(text)
            missing = list(dict.fromkeys(f for f in facts if f not in ev_set))
            if not self.number_check:
                missing = []
            score = float(self.scorer.score(text, cited))
            claims.append(
                {
                    "text": text,
                    "score": score,
                    "numbers_missing": missing,
                    "supported": score >= self.tau_g and not missing,
                }
            )

        unsupported = [i for i, c in enumerate(claims) if not c["supported"]]
        support = 1 - len(unsupported) / len(claims) if claims else 1.0
        details = {"support": support, "claims": claims, "unsupported": unsupported}
        if not unsupported:
            return result(Action.ALLOW, None, 0.0, **details)
        if support < self.fallback_below:
            return result(Action.FALLBACK, "UNSUPPORTED_CLAIM", 1 - support, **details)
        numbers = any(claims[i]["numbers_missing"] for i in unsupported)
        category = "NUMBER_MISMATCH" if numbers else "UNSUPPORTED_CLAIM"
        return result(Action.REGENERATE, category, 1 - support, **details)
