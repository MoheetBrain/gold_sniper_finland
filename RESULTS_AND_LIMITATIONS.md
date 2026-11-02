# Results and limitations

## Evidence status

**No real-data ML metric was independently reproduced in this release.** The original committed summaries were cross-checked for consistency. Their supporting feature, label, role, block and OOF prediction tables are absent from reachable Git history. The new synthetic demonstration and regression tests were executed; they do not validate Finnish prospectivity.

## Experimental chronology

| Stage | Evidence in private source history | Interpretation |
|---|---|---|
| 4 June 2026: initial regional model | Structure-only documentation; AUC about 0.715; top-5% capture 0 / 8 | Failed the strict capture-plus-AUC gate. Preserve the negative finding. |
| 12 June: gravity and sparse till | `201f53e` aggregate validation; 3,649 cells, eight positives; AUC 0.798 | Reported improvement after added features; not a new independent cohort. |
| 12 June: seven ablations | `40a71ff` ablation table; full model AUC 0.7984, structure+gravity 0.7843 | Sparse till had zero fitted importance in the full model; attribution is uncertain. |
| 13–15 June: maps, Monte Carlo, TerraMind and v2 | Scripts committed through `c272a4b`; many required inputs/outputs untracked | Implementation or prototype evidence; no independent confirmation of claimed v2 improvements. |
| 2 November: release engineering | Corrected fold-local preprocessing, synthetic execution and regression tests | New software verification only. Historical metrics are frozen, not silently replaced. |

## Historical aggregates

| Method | ROC-AUC | Top 1% capture | Top 5% capture | Top 10% capture |
|---|---:|---:|---:|---:|
| XGBoost OOF | 0.798 | 1 / 8 | 1 / 8 | 1 / 8 |
| Fault distance | 0.675 | 0 / 8 | 0 / 8 | 2 / 8 |
| One seeded random draw | 0.575 | 0 / 8 | 1 / 8 | 2 / 8 |

The circular distance-to-known-deposit reference scored 1.0 AUC and complete capture. It uses the answer to construct its score and is not evidence of model quality.

The top 5% contains 183 of 3,649 cells, capturing one known positive. That is a 12.5% recall and 1/183 known-positive fraction; neither is a calibrated geological discovery probability. At top 10%, the fault baseline captures twice as many positives as the model. With eight positives, each capture step is 12.5 percentage points. AUC does not have that same step size. Confidence bounds for historical AUC cannot be reconstructed from these aggregates alone.

## Ablations and missingness

The historical [seven-group ablation table](data/historical/STEP2_2B_FEATURE_ABLATION.csv) reports AUCs of 0.7146 (structure/lithology), 0.7031 (gravity), 0.3803 (till only), 0.7843 (structure+gravity), 0.7465 (structure+till), 0.6655 (gravity+till), and 0.7984 (full). These share the same tiny labelled population. Comparing groups on the same evaluation repeatedly is exploratory selection, not independent confirmation.

The gravity feature was available for all 3,798 original grid cells; Au/As/Sb till features covered about 1%. A feature counted as “real” because any value exists can still be mostly missing. Numerical magnetics were absent from the validated Step 2 summary. The labels “single_signal_hallucination” and “PASS” in historical files were custom heuristics, not accepted statistical diagnostics or proof of correctness.

## Material limitations

- **Historical preprocessing leakage:** medians and class weights used held-out rows. Fixed for future execution, effect on historical AUC unknown.
- **Spatial dependence:** block separation is not a guarantee of independent folds; adjacent boundaries, coarse maps and shared deposit systems remain relevant.
- **Label and exploration bias:** background is unlabelled, not barren; label-informed exclusion changes the evaluation population.
- **Small sample:** eight positive cells may represent fewer independent geological systems. No deployment study, field validation, external test region or prospective discovery has been demonstrated.
- **Feature validity:** coarse contacts/faults are proxies; sparse till, provisional glacial directions and regional gravity cannot establish target-scale mechanisms.
- **Baseline/tie sensitivity:** one random seed is not a null distribution. Flat or tied scores can change capture through row order. New code exposes tie bounds.
- **Model interpretation:** training-set importances and hand-selected Monte Carlo weights are not causal geological evidence. Simulation stability does not eliminate incorrect assumptions.
- **Cadastre:** historical rights and incomplete restriction masks cannot establish current legal availability or authorise fieldwork.
- **Reproducibility:** original raw datasets, exact historic software environment and prediction tables are missing. The locked release environment applies to this demonstration, not to reconstruction of the original machine.

## What was reproduced

The original five geometry/status tests and the expanded release tests pass. The public demonstration executes grid construction, polygon overlap, feature creation, role assignment, grouped XGBoost, predeclared ablations, repeated random baselines and Monte Carlo rank sensitivity. Its inputs, folds and outputs are in [data/example](data/example). See [validation](docs/VALIDATION.md) for exact counts and audit boundaries.
