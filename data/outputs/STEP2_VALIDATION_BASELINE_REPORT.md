# Step 2 Validation & Baselines Report

Spatial-block out-of-fold evaluation on the **2km** grid (8 positives, 3649 labelled cells).

## Verdict: **PASS (model beats distance-to-fault)**

- Model beats distance-to-fault: **True**
- Model beats distance-to-fault by top-k: **{'top1pct': True, 'top5pct': True, 'top10pct': False}**
- Strong-pass benchmark (≥80% positives in top 5%): **False** (benchmark only, not a hard fail)

## Honesty flags

- `single_signal_hallucination`: **False** (top feature: dist_major_shear, fraction: 0.3565)
- `magnetics_low_confidence`: **True**

## Top-k capture (fraction of positives)

| method | top 1% | top 5% | top 10% | ROC-AUC |
|--------|--------|--------|---------|---------|
| model_xgb_oof | 0.125 | 0.125 | 0.125 | 0.798 |
| baseline_distfault | 0.0 | 0.0 | 0.25 | 0.675 |
| baseline_random | 0.0 | 0.125 | 0.25 | 0.575 |
| ref_distdeposit_leaky | 1.0 | 1.0 | 1.0 | 1.0 |

## How to read this
- **baseline_distfault** is the bar to beat (orogenic gold is fault-hosted).
- **baseline_random** is the floor.
- **ref_distdeposit_leaky** is a circular reference (distance to the very
  deposits we're trying to find) — expect it high; it is NOT an honest model.
- With ~8 positives, all numbers are high-variance. Treat as indicative.

## Consequence
- Model may inform ranking, but still requires multi-layer support. 
- Either way, NO output is a 'gold target' — only modelling candidates.
