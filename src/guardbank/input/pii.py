"""Input PII redaction (SPEC §2 step 2, §3 PII row; docs/specs/input-pii.md).

Regex + context-word recognizers for Nepal formats, cards, OTPs, passwords and email, plus
an optional Presidio/spaCy `Detector` for names and places. Matches become typed tokens
(`<NP_PHONE_1>`) stored in a per-session `PiiVault`. Raw values never leave the vault.
"""

from __future__ import annotations

import re
import time
from collections.abc import Iterable
from typing import Any

from guardbank.input.detectors import Detector, build_pii_detector
from guardbank.types import Action, GuardResult, Span

STAGE = "input_pii"
_TOKEN = re.compile(r"<[A-Z_]+_\d+>")

# Patterns are structure, not thresholds; context words and window come from YAML.
_PATTERNS: dict[str, re.Pattern[str]] = {
    "NP_CITIZENSHIP": re.compile(r"(?<!\d)\d{2}[-/]\d{2}[-/]\d{2}[-/]\d{4,5}(?!\d)"),
    "NP_PAN": re.compile(r"(?<![\d-])\d{9}(?![\d-])"),
    "NP_PHONE": re.compile(r"(?<![\d+])(?:\+?977[-\s]?)?9[78]\d{8}(?!\d)"),
    "ACCOUNT_NO": re.compile(r"(?<![\d-])\d{10,16}(?![\d-])"),
    "CARD": re.compile(r"(?<!\d)\d(?:[ -]?\d){12,18}(?!\d)"),
    "OTP": re.compile(r"(?<![\d-])\d{4,8}(?![\d-])"),
    "EMAIL": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
}


def _luhn(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


class PiiVault:
    """Per-session token <-> value map. The same (label, value) always gets the same token."""

    def __init__(self) -> None:
        self._by_value: dict[tuple[str, str], str] = {}
        self._by_token: dict[str, str] = {}
        self._counts: dict[str, int] = {}

    def token_for(self, label: str, value: str) -> str:
        key = (label, value)
        if key not in self._by_value:
            n = self._counts.get(label, 0) + 1
            self._counts[label] = n
            token = f"<{label}_{n}>"
            self._by_value[key] = token
            self._by_token[token] = value
        return self._by_value[key]

    def restore(self, text: str) -> str:
        return _TOKEN.sub(lambda m: self._by_token.get(m.group(0), m.group(0)), text)

    def value_of(self, token: str) -> str | None:
        return self._by_token.get(token)

    def has_value(self, value: str) -> bool:
        """True if this user typed `value` (spaces, dashes and case ignored)."""
        want = _canon(value)
        return any(_canon(v) == want for _, v in self._by_value)


def _canon(value: str) -> str:
    return re.sub(r"[\s-]", "", value).lower()


class PiiRedactor:
    def __init__(self, config: dict[str, Any], detector: Detector | None = None) -> None:
        self.labels: list[str] = list(config["labels"])
        self.never_share: set[str] = set(config["never_share"])
        self.warning: str = config["warning"]
        self.window: int = config["context_window"]
        self._priority = {label: i for i, label in enumerate(self.labels)}
        self._context = {
            label: re.compile(
                "|".join(rf"(?<![a-z0-9]){re.escape(w.lower())}(?![a-z0-9])" for w in words)
            )
            for label, words in config.get("context_words", {}).items()
            if words
        }
        pw_words = config.get("context_words", {}).get("PASSWORD", [])
        self._password = (
            re.compile(
                r"(?i)(?<![a-z0-9])(?:"
                + "|".join(re.escape(w) for w in pw_words)
                + r")(?![a-z0-9])\s*(?:is\b|:|=)"
                + ("" if config.get("password_requires_marker") else "?")
                + r"\s*(\S+?)(?=[.,;?]?(?:\s|$))"
            )
            if pw_words
            else None
        )
        self.detector = detector or build_pii_detector(config)

    @classmethod
    def from_settings(cls, settings: Any) -> PiiRedactor:
        return cls(settings.input["pii"])

    def check(self, text: str, vault: PiiVault, decoded: Iterable[str] = ()) -> GuardResult:
        t0 = time.perf_counter()
        redacted, spans = self._redact(text, vault)
        decoded_redacted: list[str] = []
        decoded_labels: list[str] = []
        for d in decoded:
            out, d_spans = self._redact(d, vault)
            decoded_redacted.append(out)
            decoded_labels += [s.label for s in d_spans]

        labels = [s.label for s in spans] + decoded_labels
        detected = bool(labels)
        warn = self.warning if self.never_share.intersection(labels) else None
        return GuardResult(
            stage=STAGE,
            detected=detected,
            score=1.0 if detected else 0.0,
            spans=spans,
            category=labels[0] if labels else None,
            action=Action.REDACT if detected else Action.ALLOW,
            latency_ms=(time.perf_counter() - t0) * 1000,
            details={"redacted": redacted, "decoded_redacted": decoded_redacted, "warning": warn},
        )

    def find(self, text: str) -> list[tuple[int, int, str]]:
        """Non-overlapping PII hits as (start, end, label), in text order. Nothing is stored."""
        return self._resolve(self._candidates(text))

    def _redact(self, text: str, vault: PiiVault) -> tuple[str, list[Span]]:
        chosen = self._resolve(self._candidates(text))
        spans: list[Span] = []
        parts: list[str] = []
        pos = 0
        for start, end, label in chosen:
            token = vault.token_for(label, text[start:end])
            parts += [text[pos:start], token]
            spans.append(Span(start=start, end=end, label=label, text=token))
            pos = end
        parts.append(text[pos:])
        return "".join(parts), spans

    def _candidates(self, text: str) -> list[tuple[int, int, str]]:
        found: list[tuple[int, int, str]] = []
        lower = text.lower()
        for label in self.labels:
            if label == "PASSWORD":
                if self._password:
                    found += [(m.start(1), m.end(1), label) for m in self._password.finditer(text)]
                continue
            pattern = _PATTERNS.get(label)
            if pattern is None:
                continue
            for m in pattern.finditer(text):
                if label == "CARD" and not _luhn(re.sub(r"\D", "", m.group(0))):
                    continue
                ctx = self._context.get(label)
                if ctx and not ctx.search(lower[max(0, m.start() - self.window) : m.start()]):
                    continue
                found.append((m.start(), m.end(), label))
        found += [
            (s.start, s.end, s.label)
            for s in self.detector.detect(text)
            if s.label in self._priority
        ]
        return found

    def _resolve(self, found: list[tuple[int, int, str]]) -> list[tuple[int, int, str]]:
        """Greedy: longest span first, ties broken by YAML label order; drop overlaps."""
        ranked = sorted(found, key=lambda c: (-(c[1] - c[0]), self._priority[c[2]], c[0]))
        chosen: list[tuple[int, int, str]] = []
        for c in ranked:
            if all(c[1] <= o[0] or c[0] >= o[1] for o in chosen):
                chosen.append(c)
        return sorted(chosen)
