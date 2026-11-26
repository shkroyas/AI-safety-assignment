# Ablations, sweeps and latency

## injection ablation (test split)

| variant | P | R (95% CI) | F1 | FPR (95% CI) | FP | FN |
|---|---|---|---|---|---|---|
| regex | 0.826 | 0.760 [0.57, 0.89] | 0.792 | 0.167 [0.07, 0.36] | 4 | 6 |
| classifier | 0.885 | 0.920 [0.75, 0.98] | 0.902 | 0.125 [0.04, 0.31] | 3 | 2 |
| hybrid | 0.800 | 0.960 [0.80, 0.99] | 0.873 | 0.250 [0.12, 0.45] | 6 | 1 |

## groundedness ablation (test split)

| variant | P | R (95% CI) | F1 | FPR (95% CI) | FP | FN |
|---|---|---|---|---|---|---|
| keyword | 0.706 | 0.706 [0.47, 0.87] | 0.706 | 0.294 [0.13, 0.53] | 5 | 5 |
| keyword+number | 0.750 | 0.882 [0.66, 0.97] | 0.811 | 0.294 [0.13, 0.53] | 5 | 2 |
| nli | 1.000 | 0.941 [0.73, 0.99] | 0.970 | 0.000 [0.00, 0.18] | 0 | 1 |
| nli+number | 1.000 | 1.000 [0.82, 1.00] | 1.000 | 0.000 [0.00, 0.18] | 0 | 0 |

## Threshold sweeps (chosen on dev, reported on test)

| sweep | current | dev-best | test F1 @current | test F1 @dev-best | test FPR @current | test FPR @dev-best |
|---|---|---|---|---|---|---|
| injection_tau | 0.8 | 0.05 | 0.873 | 0.873 | 0.250 | 0.250 |
| tau_g_keyword | 0.6 | 0.8 | 0.811 | 0.732 | 0.294 | 0.529 |
| tau_g_hhem | 0.5 | 0.5 | 1.000 | 1.000 | 0.000 | 0.000 |

## Latency (ms, MockLLM: LLM time excluded)

| mode | p50 | p95 | hardware |
|---|---|---|---|
| fast | 1.0 | 1.5 | stubs, no models |
| full-gpu | 58.5 | 98.2 | NVIDIA GeForce RTX 4050 Laptop GPU |
| full-cpu | 268.6 | 465.2 | CPU only |
