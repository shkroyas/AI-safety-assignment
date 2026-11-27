# Spec delta: fix/groundedness-live-style

SPEC section: 4. Output guardrails (Groundedness) + 6. Evaluation. Found by the re-recorded live demo. ≤40 lines.

## Problem (measured on 3 live Claude answers, full mode, 2026-11-27)
- In the re-recorded demo 3 of 7 Claude answers went to the safe fallback on groundedness, while the synthetic
  groundedness set scores F1 1.00: the set does not look like how Claude writes.
- Claim-level scores of the swallowed-card and complaint answers (15 sentences, 11 below τ_g 0.5) fall into:
  - conversational sentences with nothing to check: "I'm sorry to hear your card was swallowed…" (0.011),
    "Here's what you should do:" (0.163), "Please do not share your PIN, password, or OTP…" (0.035, a rule the
    system prompt itself imposes) → groundedness false positives;
  - real additions beyond the context: "request a replacement card by contacting our support team", "raise this
    complaint through the mobile app, by visiting a branch, or by contacting our support team" → correct catches;
  - a paraphrase HHEM misses: "raise a formal complaint … providing the date and amount" (0.177) although the
    chunk says exactly that → model limitation;
  - a retrieval gap: "swallowed by the ATM" retrieves ATM limits and account closure, not the blocking steps.

## Fix
- `output.groundedness.non_claims` (YAML regexes, case-insensitive): apologies/empathy at sentence start, lead-ins
  ending in ":", and "do not / never share your PIN / password / OTP / CVV". Such sentences are kept in the
  answer but not scored (`details.claims[*].skipped = true`). Measured: they match 0 of the 50 groundedness eval
  items and exactly the 4 conversational sentences among the 15 live claims.
- New eval set `data/eval/groundedness_live.jsonl` (reported as `groundedness_live`): the 15 live sentences plus
  the sentences of the live scam-victim answer, each hand-labelled supported (0) / unsupported (1) against its
  cited chunks, with the reason in a `note` field; conversational ones labelled 0. Labels are written before the
  fix is measured on the set; before/after both reported.

## Tests first
- Fast (`tests/output/test_groundedness.py`): the three conversational forms are skipped; "Blocked cards cannot be
  unblocked." and "The fee is NPR 500." are still claims; an answer of only skipped sentences plus one supported
  claim is allowed; an unsupported addition next to an apology still fails.
- `tests/eval/test_datasets.py`: new set valid, both labels present, every item has a note and evidence.
- `make eval`, `make eval-full`, `make ablations`; groundedness and groundedness_live before/after in the report.

## Limits
- The HHEM paraphrase miss and the retrieval gap are reported, not fixed. The non-claim list is closed and English
  only; a factual sentence written as an apology ("I'm sorry, but the fee is NPR 500") would be skipped.
