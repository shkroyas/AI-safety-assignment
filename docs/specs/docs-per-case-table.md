# Spec delta: docs/per-case-table

SPEC section: 5. Test case format + assignment §3 ("for each test case, record: test input and relevant reference
information, expected behavior, actual behavior, pass/fail"). From EVALUATION_RECOMMENDATIONS.md P0-6. ≤40 lines.

## Problem
- The report and README show only per-category pass counts. `eval/results/*/cases.json` has id, category,
  pass, actual and reasons, but not the input, the reference information or the expected behaviour, and not
  the reply text. A grader checking §3 against the report sees counts, not the per-case record.

## Change
- `CaseResult` gains `text` (the final reply). `_run_cases` writes, per case: `id`, `category`, `input`,
  `reference` (the `reference_docs` ids, or "scripted LLM output: …" shortened to 120 characters for fault
  injection cases, or "—"), `expected` (the expected dict), `actual` (unchanged), `reply` (shortened to 160
  characters), `pass`, `reasons`, `known_failure`.
- `scripts/report_tables.py` gains a `cases_detail` block: one row per case with id, category, input,
  reference, expected (outcome / stage / action), actual (outcome / stage / action), pass in full mode and
  pass in fast mode (known fast-mode failures marked). Shown in the report as "Appendix A. End-to-end
  cases"; the README links to it. Pipes and newlines in cell text are escaped.
- `tests/test_docs.py` keeps checking the blocks are current; the appendix must have one row per case.

## Tests first
- `tests/eval/test_run_eval.py`: `cases.json` rows have the new keys; `input` equals the case input;
  `reference` is set for every case that has `reference_docs` or `llm_output`.
- `tests/test_docs.py`: the appendix table has as many rows as `tests/cases.yaml` has cases.
- `make eval`, `make eval-full` (cases.json regenerated); `make docs`.

## Limits
- Long inputs and replies are shortened in the table; `cases.json` keeps the full input and the shortened
  reply (no PII is stored: case inputs are synthetic and replies are post-guardrail).
