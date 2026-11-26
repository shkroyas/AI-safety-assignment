"""Number, percentage and date extraction for the groundedness check and keyword scorer."""

from __future__ import annotations

import re

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
