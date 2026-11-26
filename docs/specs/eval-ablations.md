# Spec delta: feat/eval-ablations (step 12b)

SPEC section: 6. Evaluation (ablations, threshold sweeps, latency). ≤40 lines.

## Scope
- `src/guardbank/evaluation/ablations.py` + `eval/run_ablations.py`, `make ablations` (`ml` extra, GPU if available).
  Outputs in `eval/results/ablations/`: `ablations.json`, `sweeps.json`, `latency.json`, `tables.md`, `charts/*.png`.
- `matplotlib` joins the `ml` extra (charts only).

## Behaviour
- **Injection ablation** on the injection set: `regex` (stub classifier), `classifier` (DeBERTa, empty pattern bank),
  `hybrid` (both, as shipped). Same normalizer and decoding for all three.
- **Groundedness ablation**: `keyword`, `keyword+number`, `nli` (HHEM, number check off), `nli+number`.
- Both report P/R/F1/FPR with Wilson CIs on dev and test, plus FP/FN ids per variant.
- **Sweeps** (`tau` for injection on hybrid scores, `tau_g` for keyword and HHEM, grid 0.05…0.95 step 0.05 + current):
  each item is scored once, then thresholded. The dev-best F1 tau (tie → closest to the current value) is reported
  with its test metrics next to the current tau's test metrics. **YAML is not changed here**; a change is a `fix/*`.
- **Latency**: the 45 e2e cases through the pipeline with MockLLM, 3 repeats after 1 warm-up run, for `fast`,
  `full-gpu` and `full-cpu` (`device: cpu`). p50/p95 of the total and per stage, from `GuardResult.latency_ms`.
  LLM time is excluded (MockLLM). The GPU name and torch version are recorded.
- Charts: tau / tau_g sweep curves (P, R, F1 against tau, with the current and dev-best tau marked), ablation F1 bars
  with CI error bars, latency p50/p95 bars per mode. Colour-blind-safe palette, readable in light and dark.

## API (testable without models)
- `sweep(rows, taus, predict) -> list[{tau, precision, recall, f1, fpr, tp, fp, fn, tn}]`; `rows = (id, label, score, extra)`.
- `best_tau(sweep_rows, current) -> float`; `percentile(values, q)` (linear interpolation).
- `injection_variants(settings) -> dict[name, Settings]`, `groundedness_variants(settings) -> dict[name, Settings]`.
- `latency(settings, cases, repeats, warmup) -> {total: {p50, p95}, stages: {stage: {p50, p95}}, n}`.

## Tests first (`tests/eval/test_ablations.py`, all fast)
- sweep counts against a hand-computed toy set; `best_tau` picks max F1 and breaks ties towards current; percentile values;
  variants set the right kinds (regex → stub, classifier → no patterns, nli → hhem and number_check off);
  `latency` on fast settings returns p50 <= p95 for every pipeline stage; the ablation run in fast mode writes the JSON files and `tables.md`.

## Out of scope
- Changing thresholds (needs dev evidence + Royas OK: `fix/*`); the report text (`docs/report`).
