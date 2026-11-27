# Ablations, sweeps and latency

## injection ablation (test split)

| variant | P | R (95% CI) | F1 | FPR (95% CI) | FP | FN |
|---|---|---|---|---|---|---|
| regex | 1.000 | 0.760 [0.57, 0.89] | 0.864 | 0.000 [0.00, 0.14] | 0 | 6 |
| classifier | 0.885 | 0.920 [0.75, 0.98] | 0.902 | 0.125 [0.04, 0.31] | 3 | 2 |
| hybrid | 0.889 | 0.960 [0.80, 0.99] | 0.923 | 0.125 [0.04, 0.31] | 3 | 1 |
| hybrid+both-flag | 0.889 | 0.960 [0.80, 0.99] | 0.923 | 0.125 [0.04, 0.31] | 3 | 1 |

## injection_pii ablation (test split)

| variant | P | R (95% CI) | F1 | FPR (95% CI) | FP | FN |
|---|---|---|---|---|---|---|
| regex | 1.000 | 0.182 [0.05, 0.48] | 0.308 | 0.000 [0.00, 0.15] | 0 | 9 |
| classifier | 0.647 | 1.000 [0.74, 1.00] | 0.786 | 0.286 [0.14, 0.50] | 6 | 0 |
| hybrid | 0.647 | 1.000 [0.74, 1.00] | 0.786 | 0.286 [0.14, 0.50] | 6 | 0 |
| hybrid+both-flag | 0.786 | 1.000 [0.74, 1.00] | 0.880 | 0.143 [0.05, 0.35] | 3 | 0 |

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
| injection_tau | 0.8 | 0.8 | 0.923 | 0.923 | 0.125 | 0.125 |
| tau_g_keyword | 0.6 | 0.8 | 0.811 | 0.732 | 0.294 | 0.529 |
| tau_g_hhem | 0.5 | 0.5 | 1.000 | 1.000 | 0.000 | 0.000 |

## Latency (ms, MockLLM: LLM time excluded)

| mode | p50 | p95 | hardware |
|---|---|---|---|
| fast | 1.0 | 1.4 | stubs, no models |
| full-gpu | 56.9 | 89.6 | NVIDIA GeForce RTX 4050 Laptop GPU |
| full-cpu | 271.2 | 433.7 | CPU only |
