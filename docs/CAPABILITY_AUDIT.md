# Capability inventory

Every original Python file was parsed and inventoried. “Implemented” identifies code, not proof that all external-data paths ran. “Verified” refers only to the stated tests/demo. No GNN implementation was found.

| Original file | Release disposition | Evidence / boundary |
|---|---|---|
| `fix_qgis.py` | Private backup only | Maps/diagnostics may expose targets, paths or restricted basemap choices; replaced with safe figures |
| `scripts/00_download_tukes_map_files.py` | Included | Retained generic implementation; external-data execution not reproduced |
| `scripts/01_make_aoi_grid.py` | Included | Retained; exercised with synthetic inputs (release corrections documented) |
| `scripts/02_mask_taken_areas.py` | Included | Retained; exercised with synthetic inputs (release corrections documented) |
| `scripts/02b_build_restriction_masks_placeholder.py` | Included | Retained generic implementation; external-data execution not reproduced |
| `scripts/02c_classify_tukes_status.py` | Included | Retained generic implementation; external-data execution not reproduced |
| `scripts/03_demo_rank_open_cells.py` | Included | Retained generic implementation; external-data execution not reproduced |
| `scripts/04_cluster_open_cells.py` | Included | Retained generic implementation; external-data execution not reproduced |
| `scripts/04b_refine_aoi_to_clgb.py` | Included | Retained generic implementation; external-data execution not reproduced |
| `scripts/04c_build_restriction_masks.py` | Included | Retained generic implementation; external-data execution not reproduced |
| `scripts/05_load_gtk_layers.py` | Included | Retained generic implementation; external-data execution not reproduced |
| `scripts/06_build_minimal_feature_stack.py` | Included | Retained; exercised with synthetic inputs (release corrections documented) |
| `scripts/06c_process_magnetics.py` | Included | Retained generic implementation; external-data execution not reproduced |
| `scripts/06d_process_gravity.py` | Included | Retained generic implementation; external-data execution not reproduced |
| `scripts/07_build_clgb_positive_labels.py` | Included | Retained generic implementation; external-data execution not reproduced |
| `scripts/08_build_unlabelled_background.py` | Included | Retained; exercised with synthetic inputs (release corrections documented) |
| `scripts/09_make_spatial_blocks.py` | Included | Retained; exercised with synthetic inputs (release corrections documented) |
| `scripts/10_distance_to_fault_baseline.py` | Included | Retained generic implementation; external-data execution not reproduced |
| `scripts/11_train_baseline_xgboost_or_pu.py` | Included | Retained; exercised with synthetic inputs (release corrections documented) |
| `scripts/11b_topk_capture_metrics.py` | Included | Retained generic implementation; external-data execution not reproduced |
| `scripts/11c_till_shift_ablation.py` | Included | Retained generic implementation; external-data execution not reproduced |
| `scripts/12_make_target_memos.py` | Private backup only | Historical orchestration/prototype; depends on private outputs or removed scripts |
| `scripts/13_build_qgis_project.py` | Private backup only | Maps/diagnostics may expose targets, paths or restricted basemap choices; replaced with safe figures |
| `scripts/14_build_cartographic_map.py` | Private backup only | Maps/diagnostics may expose targets, paths or restricted basemap choices; replaced with safe figures |
| `scripts/14_build_command_center_maps.py` | Private backup only | Maps/diagnostics may expose targets, paths or restricted basemap choices; replaced with safe figures |
| `scripts/14b_diagnostic_coordinates.py` | Private backup only | Maps/diagnostics may expose targets, paths or restricted basemap choices; replaced with safe figures |
| `scripts/16_data_acquisition_audit.py` | Private backup only | Maps/diagnostics may expose targets, paths or restricted basemap choices; replaced with safe figures |
| `scripts/19_build_interim_till_features_au_as_sb.py` | Included | Retained generic implementation; external-data execution not reproduced |
| `scripts/21_validate_local_geophysics.py` | Included | Retained generic implementation; external-data execution not reproduced |
| `scripts/22_feature_ablation_audit.py` | Included | Retained generic implementation; external-data execution not reproduced |
| `scripts/23_audit_review_candidates.py` | Private backup only | Maps/diagnostics may expose targets, paths or restricted basemap choices; replaced with safe figures |
| `scripts/24_till_coverage_diagnosis.py` | Private backup only | Historical orchestration/prototype; depends on private outputs or removed scripts |
| `scripts/25_build_grid_atlas.py` | Private backup only | Maps/diagnostics may expose targets, paths or restricted basemap choices; replaced with safe figures |
| `scripts/25_build_zoomable_command_map.py` | Private backup only | Maps/diagnostics may expose targets, paths or restricted basemap choices; replaced with safe figures |
| `scripts/27_global_geospatial_truth_audit.py` | Private backup only | Maps/diagnostics may expose targets, paths or restricted basemap choices; replaced with safe figures |
| `scripts/28_build_interactive_geological_command_map.py` | Private backup only | Maps/diagnostics may expose targets, paths or restricted basemap choices; replaced with safe figures |
| `scripts/30_terramind_target_embeddings.py` | Private backup only | Foundation-model token-extraction prototype; outputs unverified |
| `scripts/31_terramind_xgboost_fusion.py` | Private backup only | Contrived score, not XGBoost inference; excluded |
| `scripts/99_sanity_check_outputs.py` | Private backup only | Historical orchestration/prototype; depends on private outputs or removed scripts |
| `scripts/_common.py` | Included | Retained generic implementation; external-data execution not reproduced |
| `scripts/diagnostics_audit.py` | Private backup only | Maps/diagnostics may expose targets, paths or restricted basemap choices; replaced with safe figures |
| `scripts/run_monte_carlo_top10.py` | Included | Retained; exercised with synthetic inputs (release corrections documented) |
| `scripts/run_monte_carlo_v2.py` | Private backup only | v2 implementation with absent inputs/results and target-specific selections; not verified |
| `scripts/run_step1_5.py` | Private backup only | Historical orchestration/prototype; depends on private outputs or removed scripts |
| `scripts/run_step1_pipeline.py` | Private backup only | Historical orchestration/prototype; depends on private outputs or removed scripts |
| `scripts/run_step2_minimal.py` | Private backup only | Historical orchestration/prototype; depends on private outputs or removed scripts |
| `scripts/scratch_visualize.py` | Private backup only | Maps/diagnostics may expose targets, paths or restricted basemap choices; replaced with safe figures |
| `scripts/v2_01_magnetics.py` | Private backup only | v2 implementation with absent inputs/results and target-specific selections; not verified |
| `scripts/v2_02_till_glacial.py` | Private backup only | v2 implementation with absent inputs/results and target-specific selections; not verified |
| `scripts/v2_03_capture_gate.py` | Private backup only | v2 implementation with absent inputs/results and target-specific selections; not verified |
| `scripts/v2_04_finalize_report.py` | Private backup only | v2 implementation with absent inputs/results and target-specific selections; not verified |
| `tests/test_step1.py` | Included | Original five tests pass |
