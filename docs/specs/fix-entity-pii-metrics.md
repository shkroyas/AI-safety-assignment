# Spec delta: fix/entity-pii-metrics

SPEC section: 6. Evaluation. From EVALUATION_RECOMMENDATIONS.md P1-1, measured. ≤40 lines.

## Problem (measured)
- The PII metric is message-level (any PII vs none), so a missed second entity or an extra false entity in a
  message that has PII is invisible. Measured at entity level (label bags per item):
  - fast test: P 1.000, R 0.853 (5 names/places missed: GLiNER-only labels); dev R 0.857.
  - full test: P 0.850, R 1.000 (6 extra entities); dev P 0.933. The reported message-level P/R are 1.000.
- The 6 + 1 full-mode extras: 1 detector error ("my employer" → PERSON, PIIE-013); 5 labeling gaps in my items
  (PIIE-030 "Sita", PIIE-033 a second place "Durbar Square", PIIE-053/054/058 the cities in the landline items
  added in #27); 1 by policy (PIIE-043 "Lalitpur" in a branch question, labeled none on purpose).

## Change
- `run_pii` keeps the found labels; the PII set reports, beside the message-level metrics, entity-level micro
  P/R/F1 (Wilson CI) and per-label P/R from label bags, with FP/FN listed as (id, label).
- Label corrections, limited to unambiguous names and places in the text: PIIE-030 + PERSON, PIIE-033 +
  LOCATION, PIIE-053/054/058 + LOCATION. PIIE-043 unchanged (policy). PIIE-013 unchanged (detector error,
  reported). Because these were found by looking at detector output, both the before-correction and
  after-correction entity numbers go in the report.
- Report and README metrics tables gain the entity-level PII row.

## Tests first
- `tests/eval/test_metrics.py`: label-bag scoring (missed second entity = FN, extra entity = FP, duplicate
  labels counted) on a hand-made example.
- `tests/eval/test_run_eval.py`: the pii summary has `entity` metrics with fp/fn lists.
- `make eval`, `make eval-full`, `make docs`.

## Limits
- Label bags, not spans: a right label on the wrong words still counts as correct. Span-level scoring would
  need span annotations the set does not have.
