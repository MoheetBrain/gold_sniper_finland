"""
09 — Train baseline XGBoost model  (STEP 2 STUB — not yet implemented).

PURPOSE
    Train an explainable baseline prospectivity model on the feature stack + labels,
    using positive-unlabelled-aware training, and produce a 0-1 prospectivity score
    per AOI cell with SHAP explanations.

INPUTS
    data/processed/evidence_layers/   feature stack (structure, geophysics, geochem)
    data/processed/labels/model_labels.parquet

OUTPUTS
    models/xgboost.json
    data/outputs/prospectivity_scores.gpkg   (per-cell 0-1 score)
    data/outputs/tables/shap_feature_importance.csv

WHY IT MATTERS
    XGBoost is a strong, fast, explainable baseline. SHAP tells us WHICH evidence
    drives each score, so a geologist can sanity-check that high scores come from
    structure+geophysics+geochemistry convergence, not one runaway feature.

DATA NEEDED BEFORE THIS CAN RUN
    Feature stack (scripts 06/07) and labels (script 08). Must NOT be run before the
    spatial-CV design (script 10) is settled, to avoid leakage.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import get_logger, load_config  # noqa: E402

log = get_logger("09_xgboost")


def main() -> int:
    load_config()
    log.warning("STEP 2 STUB: 09_train_baseline_xgboost is not implemented yet.")
    log.warning("Needs feature stack (06/07) + labels (08); use PU-aware training + SHAP.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
