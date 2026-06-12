# Step 2.2B Feature Ablation Audit

Spatial-block out-of-fold ablation using the same positive/background framing as the Step 2 model.

- Evaluation grid: `2km`
- Labelled cells evaluated per runnable group: 3649
- Positives: 8
- Best feature group by ROC-AUC: `full_current_model`
- `single_signal_hallucination_risk` present in any ablation: **True**
- Variance status: all metrics with 8 positives move in 12.5 percentage-point increments; treat as high-variance.

## Results

| group | features | ROC-AUC | top1 | top5 | top10 | baseline top5/top10 | beats dist-fault | top feature | single-signal risk | variance |
|-------|----------|---------|------|------|-------|---------------------|------------------|-------------|--------------------|----------|
| structure_lithology_only | dist_major_shear;fault_intersection_density;dist_key_lithological_contact | 0.7146 | 0.0 | 0.0 | 0.0 | 0.0/0.25 | NO | dist_major_shear (0.4911) | NO | high_variance |
| gravity_only | gravity_gradient | 0.7031 | 0.0 | 0.0 | 0.25 | 0.0/0.25 | NO | gravity_gradient (1.0) | YES | high_variance |
| till_au_as_sb_only | till_au_clr;till_as_clr;till_sb_clr | 0.3803 | 0.0 | 0.0 | 0.0 | 0.0/0.25 | NO | till_as_clr (0.4491) | NO | high_variance |
| structure_plus_gravity | dist_major_shear;fault_intersection_density;dist_key_lithological_contact;gravity_gradient | 0.7843 | 0.125 | 0.125 | 0.125 | 0.0/0.25 | YES | dist_major_shear (0.3717) | NO | high_variance |
| structure_plus_till | dist_major_shear;fault_intersection_density;dist_key_lithological_contact;till_au_clr;till_as_clr;till_sb_clr | 0.7465 | 0.0 | 0.0 | 0.0 | 0.0/0.25 | NO | dist_major_shear (0.4146) | NO | high_variance |
| gravity_plus_till | gravity_gradient;till_au_clr;till_as_clr;till_sb_clr | 0.6655 | 0.0 | 0.0 | 0.25 | 0.0/0.25 | NO | gravity_gradient (0.9235) | YES | high_variance |
| full_current_model | dist_major_shear;fault_intersection_density;dist_key_lithological_contact;gravity_gradient;till_au_clr;till_as_clr;till_sb_clr | 0.7984 | 0.125 | 0.125 | 0.125 | 0.0/0.25 | YES | dist_major_shear (0.3565) | NO | high_variance |

## Feature Importance

### structure_lithology_only

- Model feature importance: `{"dist_key_lithological_contact": 0.3593299984931946, "dist_major_shear": 0.49114999175071716, "fault_intersection_density": 0.14952999353408813}`
- Permutation importance: `{"dist_key_lithological_contact": 0.05406, "dist_major_shear": 0.12044, "fault_intersection_density": 7e-05}`

### gravity_only

- Model feature importance: `{"gravity_gradient": 1.0}`
- Permutation importance: `{"gravity_gradient": 0.48076}`

### till_au_as_sb_only

- Model feature importance: `{"till_as_clr": 0.44912999868392944, "till_au_clr": 0.25672000646591187, "till_sb_clr": 0.2941499948501587}`
- Permutation importance: `{"till_as_clr": -0.00459, "till_au_clr": -0.00459, "till_sb_clr": -0.00459}`

### structure_plus_gravity

- Model feature importance: `{"dist_key_lithological_contact": 0.25633999705314636, "dist_major_shear": 0.3717400133609772, "fault_intersection_density": 0.08865000307559967, "gravity_gradient": 0.283270001411438}`
- Permutation importance: `{"dist_key_lithological_contact": 0.00554, "dist_major_shear": 0.03495, "fault_intersection_density": 0.0, "gravity_gradient": 0.02885}`

### structure_plus_till

- Model feature importance: `{"dist_key_lithological_contact": 0.39864999055862427, "dist_major_shear": 0.4145500063896179, "fault_intersection_density": 0.1868000030517578, "till_as_clr": 0.0, "till_au_clr": 0.0, "till_sb_clr": 0.0}`
- Permutation importance: `{"dist_key_lithological_contact": 0.08109, "dist_major_shear": 0.1816, "fault_intersection_density": 7e-05, "till_as_clr": 0.0, "till_au_clr": 0.0, "till_sb_clr": 0.0}`

### gravity_plus_till

- Model feature importance: `{"gravity_gradient": 0.9235000014305115, "till_as_clr": 0.04933999851346016, "till_au_clr": 0.027170000597834587, "till_sb_clr": 0.0}`
- Permutation importance: `{"gravity_gradient": 0.48477, "till_as_clr": -6e-05, "till_au_clr": -0.00014, "till_sb_clr": 0.0}`

### full_current_model

- Model feature importance: `{"dist_key_lithological_contact": 0.2229900062084198, "dist_major_shear": 0.35653001070022583, "fault_intersection_density": 0.0820700004696846, "gravity_gradient": 0.33840999007225037, "till_as_clr": 0.0, "till_au_clr": 0.0, "till_sb_clr": 0.0}`
- Permutation importance: `{"dist_key_lithological_contact": 0.00878, "dist_major_shear": 0.02546, "fault_intersection_density": 0.0, "gravity_gradient": 0.03401, "till_as_clr": 0.0, "till_au_clr": 0.0, "till_sb_clr": 0.0}`

## Interpretation

- A group is marked as beating distance-to-fault only when top-5% capture and ROC-AUC both exceed the baseline on the same OOF cells.
- Top-10% failure remains important: the current full model does not dominate the simple fault-distance baseline at top 10%.
- One-feature groups that beat the baseline, or groups with >=75% importance in one feature, are flagged as single-signal risk.
- No outputs from this audit are targets or target memos.
