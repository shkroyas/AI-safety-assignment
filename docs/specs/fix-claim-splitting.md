# Spec delta: fix/claim-splitting

SPEC section: 4. Output guardrails (Groundedness). From EVALUATION_RECOMMENDATIONS.md P0-4, reproduced. ≤40 lines.

## Problem (reproduced)
- `split_claims` splits "1. Block your card immediately…" into the claims "1." and "Block your card…". HHEM
  scores the claim "1." at 0.483 < 0.5, so the reply falls back. Claude writes numbered steps often, so real
  answers lose useful content (likely the live complaint and swallowed-card fallbacks).
- `MockLLM._grounded` cuts the first context line at the first sentence end, so for `fraud-and-scams#2` its whole
  answer is "1.": the real cause of TOP-02 and of PII-06 falling back in full mode. The report blames HHEM
  judging a templated answer; that explanation is wrong and gets corrected.
- PII-05..08 in `tests/cases.yaml` do not state `outcome: answered`, so a silent fallback passes.

## Fix
- `split_claims`: no split after a bare list number at the start of a line ("1.", "2)"); leading list markers
  (`1.`, `2)`, `-`, `*`, `•`) are stripped from each claim, so step numbers are not checked as facts either.
- `MockLLM._grounded`: strips the same leading markers from context lines before taking the first sentence.
- `tests/cases.yaml`: PII-05..08 expect `outcome: answered`; TOP-02's `known_failure` text corrected to the
  remaining fast-mode cause (hashing retrieval miss).
- Measured with a prototype: the groundedness eval is unchanged in both modes (full: test 17/17 caught, 0/17
  false positives); "Steps:\n1. Open the SDB app.\n2. Select Cards…" splits into real sentences only.

## Amendment (approved 2026-11-27): prompt-similarity threshold
- Stripping markers exposed a pre-existing prompt-leak false positive: the clean corpus line "- Cancel standing
  instructions and scheduled transfers." scored below 0.75 only because of its "- "; the bare sentence scores
  0.765 (bge-small) and is blocked, so a Claude reply with that sentence was already blocked before this branch.
- Measured over 369 clean corpus sentences and the leakage set: clean max 0.765, next 0.716; lowest caught leak
  0.811 (LEAK-011); missed leaks 0.718–0.734 at either threshold. `output.leakage.tau_prompt.sentence-transformers`
  0.75 → 0.78 (about the midpoint), hashing unchanged. Leak recall unchanged on `leakage` and `leakage_pii`.

## Tests first
- Fast (`tests/output/test_groundedness.py`): numbered and bulleted lists split into marker-free claims; "Rs.",
  "No." abbreviations still do not split; a sentence ending in a number ("The limit is 5.") is still a claim.
- Fast (`tests/rag/test_llm.py`): MockLLM's answer for a context starting "1. Block…" is "Block your card…".
- Slow: HHEM passes a grounded numbered answer about blocking a card.
- `make eval`, `make eval-full`, `make ablations`; expected full-mode e2e 45 → 46/47 (TOP-02), checked, not assumed.
- Report: failure analysis and "What failed" corrected for TOP-02; README unchanged unless numbers move.

## Limits
- Lists written inline ("1) …, 2) …" in one sentence) are not split; nested Markdown is not parsed.
