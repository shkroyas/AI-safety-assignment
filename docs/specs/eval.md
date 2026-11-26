# Spec delta: feat/eval (step 12a; ablations, sweeps, latency and charts follow in feat/eval-ablations)

SPEC section: 6. Evaluation. ≤40 lines.

## Scope
- `data/eval/*.jsonl`: hand-written synthetic labeled sets, ~275 items. No text shared with `tests/cases.yaml` or
  `data/topics/train.yaml` (case-insensitive, whitespace-normalised; a test enforces it).
  | set | n | label | positive = guardrail fires |
  |---|---|---|---|
  | `injection` | ~70 | attack 1 / benign 0 (incl. look-alikes); `kind` | input injection `BLOCK` (normalizer + decoded) |
  | `pii` | ~50 | `labels: [..]`, empty = none (incl. order ids, amounts) | input PII `REDACT`; per-label recall too |
  | `topics` | ~60 | one of the 7 categories | per class one-vs-rest + macro F1; "sensitive vs NORMAL" binary |
  | `groundedness` | ~50 | claim + evidence list, unsupported 1 / supported 0; `kind` | claim not supported (score/number check) |
  | `leakage` | ~30 | answer, leak 1 / clean 0; `{canary}` placeholder | leakage `BLOCK`, or `REDACT` of third-party PII |
  | `chunk_poison` | ~15 | synthetic poisoned chunks, all 1; the 117 clean corpus chunks are the 0s | chunk scan drops it |
- `src/guardbank/evaluation/`: `datasets.py` (load + split), `metrics.py`, `runners.py` (one runner per set).
  `eval/run_eval.py --mode fast|full`: `make eval` (stubs, hashing, keyword) and `make eval-full` (`ml` extra: deberta, gliner,
  embed_logreg, hhem, bge-small leakage + retriever).

## Behaviour
- Split: stratified by label, 30% dev / 70% test, deterministic (items ordered by sha256(id) within each label). Thresholds
  are never tuned on test; this branch only reports with the frozen YAML.
- Metrics per set and split: TP/FP/FN/TN, precision, recall, F1, FPR, Wilson 95% CI for precision, recall and FPR,
  every FP and FN by id. Zero denominators give `null`, never a fake 0 or 1.
- Also runs `tests/cases.yaml` and stores each case's `actual`/`pass` (SPEC §5).
- Outputs in `eval/results/<mode>/`: `summary.json` (mode, git commit, sha256 of the YAML, metrics), `errors.md` (FP/FN per set:
  id, kind, score, text cut to 80 chars), `cases.json`. Results are committed so the report cites a fixed run.

## Tests first (`tests/eval/`, all fast)
- `test_metrics.py`: counts; P/R/F1/FPR incl. zero-denominator `null`; Wilson CI for 8/10 = (0.490, 0.943) and 0/0 = null.
- `test_datasets.py`: every set loads and validates; ids unique; minimum sizes; both labels in dev and test; dev share
  30% ± 5% per label; no overlap with cases or topic training text; card numbers only from the 4111 test BIN.
- `test_run_eval.py`: fast mode on all sets writes `summary.json`, `errors.md`, `cases.json` to a temp dir with the
  documented keys; every FP/FN id exists in its set.

## Out of scope
- Ablations, tau / tau_g sweeps, latency, charts: `feat/eval-ablations`. Fixes for found failures: `fix/*`.
