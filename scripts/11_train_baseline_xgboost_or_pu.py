"""
11 — Minimal XGBoost (PU-style) model with spatial-block out-of-fold prediction.

APPROACH (deliberately minimal, no deep learning)
    Positives = CLGB orogenic-gold cells. Unlabelled background = the "negative" class
    in a PU-style framing (treated as unlabelled, not confirmed barren). We train
    XGBoost and produce honest OUT-OF-FOLD scores using GroupKFold over 20 km spatial
    blocks (no spatial leakage). A final model trained on all labelled cells scores the
    remaining cells (buffer-excluded etc.) for ranking completeness only.

HONESTY GUARDS
    - Uses ONLY real (non-null) features; if <2 real features or <4 positive cells it
      refuses to train and writes a clear 'insufficient data' result.
    - OOF scores (not in-sample) are what 11b evaluates.

OUTPUTS
    data/processed/model_scores_<grid>.parquet   (cell_id, model_score, in_cv)
    data/outputs/STEP2_MODEL_REPORT.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import get_logger, get_path, load_config  # noqa: E402

log = get_logger("11_model")

CANDIDATE_FEATURES = [
    "dist_major_shear", "fault_intersection_density", "dist_key_lithological_contact",
    "mag_1vd", "mag_low_in_high_proxy", "gravity_gradient",
    "till_au_clr", "till_as_clr", "till_sb_clr", "till_bi_clr",
]
MIN_POSITIVES = 4


def load_grid_data(processed: Path, size: str):
    feat = pd.read_parquet(processed / f"feature_stack_minimal_{size}.parquet")
    labels = pd.read_parquet(processed / f"cell_labels_{size}.parquet")
    roles = pd.read_parquet(processed / f"cell_role_{size}.parquet")
    blocks = pd.read_parquet(processed / f"cell_block_{size}.parquet")
    df = feat.merge(labels, on="cell_id").merge(roles, on="cell_id").merge(blocks, on="cell_id")
    return df


def train_oof(df: pd.DataFrame, features: list[str]):
    """GroupKFold OOF probabilities over spatial blocks for the labelled set."""
    from sklearn.model_selection import GroupKFold
    from xgboost import XGBClassifier

    lab = df[df["role"].isin(["positive", "background"])].copy()
    lab["y"] = (lab["role"] == "positive").astype(int)
    X = lab[features].fillna(lab[features].median())
    y = lab["y"].values
    groups = lab["spatial_block_id"].values

    n_pos = int(y.sum())
    n_splits = min(5, lab["spatial_block_id"].nunique(), max(2, n_pos))
    gkf = GroupKFold(n_splits=n_splits)
    oof = np.full(len(lab), np.nan)
    spw = max(1.0, (len(y) - n_pos) / max(1, n_pos))

    for tr, te in gkf.split(X, y, groups):
        if y[tr].sum() == 0:
            continue  # no positive in this training fold — skip
        model = XGBClassifier(n_estimators=200, max_depth=3, learning_rate=0.08,
                              subsample=0.9, colsample_bytree=0.9, eval_metric="logloss",
                              scale_pos_weight=spw, random_state=42, n_jobs=2)
        model.fit(X.iloc[tr], y[tr])
        oof[te] = model.predict_proba(X.iloc[te])[:, 1]
    lab["model_score"] = oof
    lab["in_cv"] = True

    # Final model on all labelled cells -> score the rest (ranking completeness only).
    final = XGBClassifier(n_estimators=200, max_depth=3, learning_rate=0.08,
                         subsample=0.9, colsample_bytree=0.9, eval_metric="logloss",
                         scale_pos_weight=spw, random_state=42, n_jobs=2)
    final.fit(X, y)
    rest = df[~df["cell_id"].isin(lab["cell_id"])].copy()
    if not rest.empty:
        Xr = rest[features].fillna(X.median())
        rest["model_score"] = final.predict_proba(Xr)[:, 1]
        rest["in_cv"] = False
    importances = dict(zip(features, final.feature_importances_.round(4)))
    scores = pd.concat([lab[["cell_id", "model_score", "in_cv"]],
                        rest[["cell_id", "model_score", "in_cv"]]], ignore_index=True)
    return scores, importances, n_pos, n_splits


def main() -> int:
    cfg = load_config()
    processed = get_path(cfg, "processed")
    outputs = get_path(cfg, "outputs")

    report = ["# Step 2 Model Report", "",
              "Minimal XGBoost (PU-style) with spatial-block out-of-fold scoring. No deep",
              "learning. OOF scores feed the baseline comparison in 11b.", ""]
    status_any = False
    for gname in ["clgb_grid_2km", "clgb_grid_1km"]:
        size = gname.split("_")[-1]
        try:
            df = load_grid_data(processed, size)
        except FileNotFoundError:
            continue
        real = [f for f in CANDIDATE_FEATURES if f in df and df[f].notna().any()]
        n_pos = int((df["role"] == "positive").sum())
        report += [f"## {gname}", "",
                   f"- Real features used: {real or 'NONE'}",
                   f"- Positive cells: {n_pos}"]
        if len(real) < 2 or n_pos < MIN_POSITIVES:
            report += [f"- **RESULT: insufficient data to train** "
                       f"(need ≥2 real features and ≥{MIN_POSITIVES} positives).", ""]
            log.warning("%s: insufficient data (features=%d, positives=%d)",
                        gname, len(real), n_pos)
            # still emit a scores file with NaN model_score so downstream is robust
            pd.DataFrame({"cell_id": df["cell_id"], "model_score": np.nan,
                          "in_cv": False}).to_parquet(
                processed / f"model_scores_{size}.parquet", index=False)
            continue
        scores, imp, n_pos, n_splits = train_oof(df, real)
        scores.to_parquet(processed / f"model_scores_{size}.parquet", index=False)
        status_any = True
        report += [f"- Spatial-block folds: {n_splits}",
                   f"- Feature importances: {imp}",
                   f"- OOF scores written for {int(scores['in_cv'].sum())} labelled cells.", ""]
        log.info("%s: trained (features=%d, positives=%d, folds=%d)",
                 gname, len(real), n_pos, n_splits)

    report += ["## Caveat",
               "- With ~8 positives and 3 structure/lithology-only features, the model has",
               "  little to learn beyond 'near a fault'. Treat scores as indicative; the",
               "  decisive question is whether it beats distance-to-fault (see 11b).", ""]
    (outputs / "STEP2_MODEL_REPORT.md").write_text("\n".join(report), encoding="utf-8")
    log.info("Wrote STEP2_MODEL_REPORT.md (trained=%s)", status_any)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
