# Step 2 Method — minimal source-grounded CLGB orogenic-gold modelling

Step 2 turns Step 1.5 legal/geographic candidate clusters into **geology-ranked
modelling candidates** (never "gold targets"), while proving whether a model beats
simple baselines. It is deliberately minimal and anti-hallucination: **no foundation
models, no deep learning**, only source-grounded GTK data + an explainable baseline.

## Pipeline

| script | purpose |
|--------|---------|
| `05_load_gtk_layers.py` | Pull AOI-clipped GTK open data (deposits, structures, bedrock, Natura 2000, protected areas, groundwater) from GTK's ArcGIS REST server. |
| `06_build_minimal_feature_stack.py` | The 10-feature stack on 2 km + 1 km grids. Real where data exists, NULL + reported where not. |
| `07_build_clgb_positive_labels.py` | CLGB orogenic-gold positives from FODD `GENETIC_TYPE`; exclude contaminating systems. |
| `08_build_unlabelled_background.py` | Positive-unlabelled background with a 5 km exclusion buffer. |
| `09_make_spatial_blocks.py` | 20 km spatial blocks for leakage-free CV. |
| `10_distance_to_fault_baseline.py` | Distance-to-fault + random (+ leaky distance-to-deposit) baselines. |
| `11_train_baseline_xgboost_or_pu.py` | Minimal XGBoost (PU-style) with spatial-block out-of-fold scoring. |
| `11b_topk_capture_metrics.py` | Top-k capture + ROC-AUC; **beat-the-baseline gate**. |
| `11c_till_shift_ablation.py` | Till glacial-shift ablation framework (raw + up-ice shifts). |
| `04c_build_restriction_masks.py` | Apply Natura 2000 / protected / water restriction masks. |
| `run_step2_minimal.py` | Orchestrate all of the above + fuse into ranked modelling candidates. |

## Data provenance

All inputs are **GTK open data (CC BY 4.0)** pulled live from
`https://gtkdata.gtk.fi/arcgis/rest/services`, AOI-clipped, reprojected to EPSG:3067.
See `data/outputs/STEP2_DATA_AUDIT.md` for exactly what was retrieved and what is missing.

## The 10-feature stack

Structure ×2 (`dist_major_shear`, `fault_intersection_density`), lithology ×1
(`dist_key_lithological_contact`), magnetics ×2, gravity ×1, till geochem ×4. Only the
first three are real this run; the rest are explicit NULLs (no magnetics/gravity/till
yet). This is reported loudly — the model cannot show multi-layer convergence until the
geophysics and geochemistry are added.

## Scoring & gating (run_step2_minimal)

Each 2 km cell gets transparent component scores (`structural_score`,
`lithology_score`, null `geophysics_score` / till scores), a `model_score` (XGBoost
OOF), a `baseline_score` (distance-to-fault), and `model_minus_baseline`. Final status
is assigned by honest precedence:

1. `restricted_area` — fails the restriction mask.
2. `legally_blocked` — not Tukes-open (conservative).
3. `insufficient_data` — open but only structure/lithology and model failed the gate.
4. `needs_manual_geology_review` — open, restriction-clear, top-decile structure, for a
   geologist to inspect.

**No cell is labelled `modelling_candidate`** while the model fails the baseline gate.
Nothing is ever a "gold target".

## Honest limitations this run

- 3/10 real features; 6/10 (geophysics + geochem) missing → no real convergence.
- 9 positives → high-variance validation.
- GTK structure/bedrock are 1:1,000,000 scale (coarse).
- Restriction set is partial (no Sámi Homeland / parks / surface water yet).

See `VALIDATION_AND_BASELINES.md`, `CLGB_MODEL_EXCLUSIONS.md`,
`TILL_GEOCHEMISTRY_PROCESSING.md`.
