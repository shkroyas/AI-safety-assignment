# Spec delta: feat/output-groundedness

SPEC section: 4. Output guardrails (Groundedness row + invalid-response policy rows 2–3) + 6. Evaluation (ablation). ≤40 lines.

## Scope
- `output/groundedness.py`: `GroundednessChecker.check(reply, cited: dict[chunk_id, text]) -> GuardResult` (stage `"output_groundedness"`).
- `ClaimScorer` protocol (`score(claim, evidence) -> float`) in `output/scorers.py`: `KeywordScorer` (real baseline);
  HHEM NLI arrives in `feat/ml-detectors` behind the same protocol. Number/date check is separate and switchable.

## Behaviour
- Claims: split `answer` on `.!?` + whitespace and on line breaks (decimals like `2.5%` stay whole). Evidence = cited chunks only.
- Keyword score = share of a claim's content words (lowercase, ≥3 letters, stopwords removed, trailing "s" stripped)
  found in the evidence; a claim with no content words scores 1.0.
- Number check (`number_check: true`): every number, amount, percentage and date in a claim must appear in the evidence
  after normalising (`25,000`→`25000`, `2 percent`/`2 per cent`→`2%`, `NPR`/`Rs.` prefixes ignored, ISO and "15 January" dates).
  A missing one makes the claim unsupported whatever its score.
- Claim supported iff `score >= tau_g` and no missing numbers; `support` = supported / claims; `score = 1 - support` (risk).
  `details`: `support`, `claims` = `[{text, score, numbers_missing, supported}]`, `unsupported` = indices.
  - all supported → `ALLOW`; refusal (`refusal_reason` set) → `ALLOW`, not checked.
  - some unsupported and `support >= fallback_below` → `REGENERATE`, category `NUMBER_MISMATCH` if any number missing, else `UNSUPPORTED_CLAIM`.
  - `support < fallback_below`, or no citations on a non-refusal (`NO_CITATIONS`) → `FALLBACK` (remediation sets escalate).

## Config (`config/guardrails.yaml`)
```yaml
output:
  groundedness:
    scorer: keyword        # keyword | hhem (feat/ml-detectors)
    tau_g: 0.6             # claim supported when score >= tau_g; tuned on dev in feat/eval
    number_check: true
    fallback_below: 0.5    # SPEC §4: support < 0.5 -> safe fallback
```

## Tests first (`tests/output/test_groundedness.py`, all fast)
- `test_claim_split` (decimals kept), `test_grounded_reply_allowed`, `test_wrong_amount_number_mismatch`, `test_number_formats_normalised`
  (parametrized), `test_invented_sentence_unsupported` → REGENERATE, `test_mostly_invented_fallback`, `test_no_citations_fallback`,
  `test_refusal_skipped`, `test_only_cited_chunks_are_evidence`, `test_number_check_off_by_config`, `test_scorer_swappable` (fake scorer).

## Limits and out of scope
- Keyword overlap misses paraphrase and negation ("no fee" vs "a fee"); numbers in words ("seven days") and Nepali (BS) dates unchecked.
- Regenerate/strip/fallback execution: `feat/remediation-pipeline`. HHEM and its 512-token limit: `feat/ml-detectors`.
