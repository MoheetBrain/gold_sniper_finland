# Step 2 Model Report

Minimal XGBoost (PU-style) with spatial-block out-of-fold scoring. No deep
learning. OOF scores feed the baseline comparison in 11b.

## clgb_grid_2km

- Real features used: ['dist_major_shear', 'fault_intersection_density', 'dist_key_lithological_contact', 'gravity_gradient', 'till_au_clr', 'till_as_clr', 'till_sb_clr']
- Feature coverage: {'dist_major_shear': 1.0, 'fault_intersection_density': 1.0, 'dist_key_lithological_contact': 1.0, 'gravity_gradient': 1.0, 'till_au_clr': 0.01, 'till_as_clr': 0.01, 'till_sb_clr': 0.01}
- Positive cells: 8
- Spatial-block folds: 5
- Feature importances: {'dist_major_shear': 0.3564999997615814, 'fault_intersection_density': 0.08209999650716782, 'dist_key_lithological_contact': 0.22300000488758087, 'gravity_gradient': 0.3384000062942505, 'till_au_clr': 0.0, 'till_as_clr': 0.0, 'till_sb_clr': 0.0}
- Top feature importance fraction: dist_major_shear=0.36
- single_signal_hallucination: False
- OOF scores written for 3649 labelled cells.

## clgb_grid_1km

- Real features used: ['dist_major_shear', 'fault_intersection_density', 'dist_key_lithological_contact']
- Feature coverage: {'dist_major_shear': 1.0, 'fault_intersection_density': 1.0, 'dist_key_lithological_contact': 1.0}
- Positive cells: 9
- Spatial-block folds: 5
- Feature importances: {'dist_major_shear': 0.4514000117778778, 'fault_intersection_density': 0.2874999940395355, 'dist_key_lithological_contact': 0.26109999418258667}
- Top feature importance fraction: dist_major_shear=0.45
- single_signal_hallucination: False
- OOF scores written for 14659 labelled cells.

## Caveat
- Positive labels are few, so spatial-block metrics remain high-variance.
- The decisive question is whether the model beats distance-to-fault (see 11b).
- No score is a gold target; scores are modelling-candidate evidence only.
