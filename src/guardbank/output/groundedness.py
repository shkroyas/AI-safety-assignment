"""Groundedness check (SPEC §4 groundedness row, docs/specs/output-groundedness.md).

Split the answer into claims; score each against the cited chunks; require every number,
percentage and date in a claim to appear in that evidence.
"""

from __future__ import annotations

import re
import time
from typing import Any

from guardbank.output.schema import SupportReply
from guardbank.output.scorers import ClaimScorer, KeywordScorer
from guardbank.types import Action, GuardResult

STAGE = "output_groundedness"

_SENT_END = re.compile(r"[.!?]+\s+|\n+")
_ABBREV = frozenset({"rs", "no", "mr", "mrs", "dr", "st", "e.g", "i.e", "approx"})

_MONTHS = {
    m: i
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1
    )
}
_MON = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
_ISO = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
_DMY = re.compile(rf"\b(\d{{1,2}})\s+{_MON},?(?:\s+(\d{{4}}))?\b", re.IGNORECASE)
_MDY = re.compile(rf"\b{_MON}\s+(\d{{1,2}})(?:,?\s+(\d{{4}}))?\b", re.IGNORECASE)
_PERCENT = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(?:%|percent\b|per\s+cent\b)", re.IGNORECASE)
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


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


def _num(raw: str) -> str:
    n = raw.replace(",", "")
    return n.rstrip("0").rstrip(".") if "." in n else str(int(n))


def _date(y: str | None, mon: int, d: str) -> list[str]:
    md = f"--{mon:02d}-{int(d):02d}"
    return [f"{int(y):04d}{md[1:]}", md] if y else [md]


def extract_facts(text: str) -> tuple[list[str], str]:
    """Normalised numbers/percentages/dates in `text`, and the text with them blanked out."""
    facts: list[str] = []

    def take(rx: re.Pattern[str], conv) -> None:
        nonlocal text

        def repl(m: re.Match[str]) -> str:
            facts.extend(conv(m))
            return " "

        text = rx.sub(repl, text)

    take(_ISO, lambda m: _date(m[1], int(m[2]), m[3]))
    take(_DMY, lambda m: _date(m[3], _MONTHS[m[2].lower()[:3]], m[1]))
    take(_MDY, lambda m: _date(m[3], _MONTHS[m[1].lower()[:3]], m[2]))
    take(_PERCENT, lambda m: [_num(m[1]) + "%"])
    take(_NUMBER, lambda m: [_num(m[0])])
    return facts, text


class GroundednessChecker:
    def __init__(self, config: dict[str, Any], scorer: ClaimScorer | None = None) -> None:
        self.tau_g: float = config["tau_g"]
        self.number_check: bool = bool(config["number_check"])
        self.fallback_below: float = config["fallback_below"]
        if scorer is None:
            kind = config.get("scorer", "keyword")
            if kind != "keyword":
                raise NotImplementedError(f"scorer {kind!r} arrives in feat/ml-output")
            scorer = KeywordScorer()
        self.scorer = scorer

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

        evidence = "\n".join(cited)
        ev_facts, ev_text = extract_facts(evidence)
        ev_set = set(ev_facts)
        claims = []
        for text in split_claims(reply.answer):
            facts, words_only = extract_facts(text)
            missing = list(dict.fromkeys(f for f in facts if f not in ev_set))
            if not self.number_check:
                missing = []
            score = float(self.scorer.score(words_only, ev_text))
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
