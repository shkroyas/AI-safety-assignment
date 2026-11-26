"""Claim scorers for the groundedness check (docs/specs/output-groundedness.md, ml-output.md).

`score(claim, evidences)` gets the full claim text and one string per cited chunk.
`KeywordScorer` is the baseline; `HHEMScorer` (output/hhem.py) is the NLI model.
"""

from __future__ import annotations

import re
from typing import Any, Protocol

from guardbank.output.facts import extract_facts

_WORD = re.compile(r"[a-z]+")
# Function words and unit words; numbers themselves are handled by the number check.
_STOPWORDS = frozenset(
    """the and for are was were you your our ours with that this these those from will can
    could has have had per any all also into its their them they then than there here what
    which when where who how about just only more most such each other some may might shall
    should would must been being does did doing npr rupee rupees percent cent""".split()
)


class ClaimScorer(Protocol):
    def score(self, claim: str, evidences: list[str]) -> float:
        """Return how well the cited chunks support `claim`, 0..1."""
        ...


def content_words(text: str) -> set[str]:
    words = set()
    for w in _WORD.findall(text.lower()):
        if len(w) < 3 or w in _STOPWORDS:
            continue
        words.add(w[:-1] if len(w) > 3 and w.endswith("s") else w)
    return words


class KeywordScorer:
    """Share of the claim's content words (numbers and dates blanked) found in the evidence."""

    def score(self, claim: str, evidences: list[str]) -> float:
        words = content_words(extract_facts(claim)[1])
        if not words:
            return 1.0
        evidence = content_words(extract_facts("\n".join(evidences))[1])
        return len(words & evidence) / len(words)


def build_claim_scorer(config: dict[str, Any]) -> ClaimScorer:
    kind = config.get("scorer", "keyword")
    if kind == "keyword":
        return KeywordScorer()
    if kind == "hhem":
        from guardbank.output.hhem import HHEMScorer

        h = config["hhem"]
        return HHEMScorer(
            h["name"], h["revision"], h["foundation"], h["prompt"], h["max_length"], h["device"]
        )
    raise ValueError(f"unknown groundedness scorer {kind!r}; allowed: keyword, hhem")
