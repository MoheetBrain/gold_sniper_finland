# Validation & Baselines

Step 2's core question is **not** "where is gold" — it is "does the model carry any
real signal beyond a dumb baseline, under honest spatial validation?" If it doesn't, we
do not rank targets.

## Spatial-block cross-validation (no leakage)

- 20 km × 20 km blocks (`09_make_spatial_blocks.py`). Whole blocks go to train or test.
- Out-of-fold (OOF) predictions via `GroupKFold` over blocks (`11`).
- **Random k-fold is forbidden** here: neighbouring cells share spatial autocorrelation
  and would leak between train and test, inflating skill.

## Baselines (the bars to clear)

| baseline | meaning | role |
|----------|---------|------|
| `baseline_random` | seeded uniform noise | the floor |
| `baseline_distfault` | 1/(1+distance-to-major-shear) | **the bar to beat** (orogenic gold is fault-hosted) |
| `ref_distdeposit_leaky` | 1/(1+distance-to-known-deposit) | leaky reference ceiling (circular — NOT honest) |

## Metrics

- **Top-k area capture** (top 1% / 5% / 10%): fraction of known deposits falling in the
  top-ranked area. This is the metric that matters for prospectivity.
- **ROC-AUC**: reported, but with a small-sample caveat.
- **Strong-pass benchmark**: ≥80% of positives in top 5%. Reported, but **not** an
  immediate hard fail when data is incomplete (per project rule).

## Hard gate

The model "passes" only if its top-5% capture **and** ROC-AUC both exceed
distance-to-fault. Otherwise the verdict is **FAIL** and target ranking does **not**
proceed on the model score — candidates fall back to transparent geology scores and are
flagged `insufficient_data` / `needs_manual_geology_review`.

## Result of this run (2 km grid)

- Positives evaluated: **8**; labelled eval cells: **3,649**.
- ROC-AUC: model **0.715**, distance-to-fault **0.675**, random **0.575**.
- Top-5% capture: model **0.00**, distance-to-fault **0.00**, random **0.125**.
- **Verdict: FAIL — the model does not beat distance-to-fault.**

### Why this is the *expected, correct* outcome

With only coarse 1:1,000,000 structures, no magnetics/gravity/till, and 8 positives, the
model has almost nothing to learn beyond "near a mapped megastructure" — and at 1:1M the
known deposits are often **not** near the few mapped structures, so even the baseline is
weak. The framework correctly refuses to manufacture confidence. This is the
anti-hallucination behaviour we want.

### What would change the verdict

Add the missing evidence layers (airborne magnetics + derivatives, gravity, till
geochemistry with glacial-shift ablation) and finer 1:200k structures, then re-run. Only
if the model then beats distance-to-fault on blocked CV do we proceed to rank real
modelling candidates.
