---
name: run-eval
description: Run the guardbank evaluation (metrics, ablations, threshold sweeps, latency) and summarise what changed. Use when asked to evaluate, measure, re-run metrics, or check whether a fix moved precision/recall.
---

# Run the evaluation

1. `git stash list` / `git status`: note uncommitted changes, since results must match a commit.
2. Copy the current `eval/results/summary.json` to the scratchpad as the baseline (if present).
3. Run `make eval` (fast, stub models) or `make eval-full` (real models, needs GPU and HF token).
4. Read only `eval/results/summary.json` and `eval/results/errors.md`. Don't load the
   labeled sets in `data/eval/` into context.
5. Report per guardrail: precision, recall, F1, FPR, FP and FN counts, and the delta against
   the baseline. List the FN/FP ids that are new or fixed.
6. Thresholds are tuned on the **dev** split only. Never change a threshold because of a test-split result.
