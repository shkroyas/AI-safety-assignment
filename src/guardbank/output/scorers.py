"""Claim scorers for the groundedness check (docs/specs/output-groundedness.md).

`KeywordScorer` is the baseline. The HHEM NLI scorer arrives in feat/ml-detectors behind
the same `ClaimScorer` protocol, so the eval can ablate keyword vs NLI.
"""

from __future__ import annotations

import re
from typing import Protocol

_WORD = re.compile(r"[a-z]+")
# Function words and unit words; numbers themselves are handled by the number check.
_STOPWORDS = frozenset(
    """the and for are was were you your our ours with that this these those from will can
    could has have had per any all also into its their them they then than there here what
    which when where who how about just only more most such each other some may might shall
    should would must been being does did doing npr rupee rupees percent cent""".split()
)


class ClaimScorer(Protocol):
    def score(self, claim: str, evidence: str) -> float:
        """Return how well `evidence` supports `claim`, 0..1."""
        ...


def content_words(text: str) -> set[str]:
    words = set()
    for w in _WORD.findall(text.lower()):
        if len(w) < 3 or w in _STOPWORDS:
            continue
        words.add(w[:-1] if len(w) > 3 and w.endswith("s") else w)
    return words


class KeywordScorer:
    """Share of the claim's content words that occur in the evidence."""

    def score(self, claim: str, evidence: str) -> float:
        words = content_words(claim)
        if not words:
            return 1.0
        return len(words & content_words(evidence)) / len(words)
