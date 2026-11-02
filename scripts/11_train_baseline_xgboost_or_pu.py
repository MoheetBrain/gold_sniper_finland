"""
11 — Minimal XGBoost (PU-style) model with spatial-block out-of-fold prediction.

APPROACH (deliberately minimal, no deep learning)
    Positives = CLGB orogenic-gold cells. Unlabelled background = the "negative" class
    in a PU-style framing (treated as unlabelled, not confirmed barren). We train
    XGBoost and produce honest OUT-OF-FOLD scores using GroupKFold over 20 km spatial
    blocks (reduced spatial dependence, not proof of independence). A final model trained on all labelled cells scores the
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

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import get_logger, get_path, load_config  # noqa: E402

log = get_logger("11_model")

CANDIDATE_FEATURES = [
    "dist_major_shear", "fault_intersection_density", "dist_key_lithological_contact",
    "mag_1vd", "mag_visual_proxy_low_confidence", "mag_low_in_high_proxy",
    "gravity_gradient",
    "till_au_clr", "till_au_log", "till_as_clr", "till_as_log",
    "till_sb_clr", "till_sb_log", "till_bi_clr",
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
    """Corrected release implementation; historical metrics have NOT been rerun."""
    from _evaluation import fit_grouped
    lab = df[df["role"].isin(["positive", "background"])].copy()
    oof, final, med, folds = fit_grouped(lab, features)
    lab["model_score"] = oof
    lab["in_cv"] = True
    rest = df[~df["cell_id"].isin(lab["cell_id"])].copy()
    rest["model_score"] = (final.predict_proba(rest[features].fillna(med))[:,1]
                           if len(rest) else np.array([],dtype=float))
    rest["in_cv"] = False
    imp = {f:float(v) for f,v in zip(features,final.feature_importances_.round(4))}
    scores = pd.concat([lab[["cell_id","model_score","in_cv"]],
                        rest[["cell_id","model_score","in_cv"]]],ignore_index=True)
    return scores,imp,int((lab["role"]=="positive").sum()),len(folds)


def main() -> int:
    cfg = load_config()
    processed = get_path(cfg, "processed")
    outputs = get_path(cfg, "outputs")

    report = ["# Step 2 Model Report", "",
              "Minimal XGBoost (PU-style) with spatial-block out-of-fold scoring. No deep",
              "learning. OOF scores feed the baseline comparison in 11b.", ""]
    status_any = False
    model_meta = {}
    for gname in ["clgb_grid_2km", "clgb_grid_1km"]:
        size = gname.split("_")[-1]
        try:
            df = load_grid_data(processed, size)
        except FileNotFoundError:
            continue
        real = [f for f in CANDIDATE_FEATURES if f in df and df[f].notna().any()]
        coverage = {f: round(float(df[f].notna().mean()), 4) for f in real}
        n_pos = int((df["role"] == "positive").sum())
        report += [f"## {gname}", "",
                   f"- Real features used: {real or 'NONE'}",
                   f"- Feature coverage: {coverage}",
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
            model_meta[size] = {
                "trained": False,
                "features": real,
                "feature_coverage": coverage,
                "feature_importances": {},
                "positive_cells": n_pos,
                "reason": "insufficient data",
            }
            continue
        scores, imp, n_pos, n_splits = train_oof(df, real)
        scores.to_parquet(processed / f"model_scores_{size}.parquet", index=False)
        status_any = True
        total_imp = float(sum(imp.values()))
        top_feature = max(imp, key=imp.get) if imp else None
        top_fraction = float(imp[top_feature] / total_imp) if top_feature and total_imp > 0 else 0.0
        single_signal = bool(top_fraction >= 0.75)
        model_meta[size] = {
            "trained": True,
            "features": real,
            "feature_coverage": coverage,
            "feature_importances": imp,
            "positive_cells": n_pos,
            "spatial_block_folds": n_splits,
            "top_feature": top_feature,
            "top_feature_importance_fraction": round(top_fraction, 4),
            "single_signal_hallucination": single_signal,
        }
        report += [f"- Spatial-block folds: {n_splits}",
                   f"- Feature importances: {imp}",
                   f"- Top feature importance fraction: {top_feature}={top_fraction:.2f}",
                   f"- single_signal_hallucination: {single_signal}",
                   f"- OOF scores written for {int(scores['in_cv'].sum())} labelled cells.", ""]
        log.info("%s: trained (features=%d, positives=%d, folds=%d)",
                 gname, len(real), n_pos, n_splits)

    (outputs / "STEP2_MODEL_FEATURE_IMPORTANCE.json").write_text(
        json.dumps(model_meta, indent=2), encoding="utf-8"
    )
    report += ["## Caveat",
               "- Positive labels are few, so spatial-block metrics remain high-variance.",
               "- The decisive question is whether the model beats distance-to-fault (see 11b).",
               "- No score is a gold target; scores are modelling-candidate evidence only.", ""]
    (outputs / "STEP2_MODEL_REPORT.md").write_text("\n".join(report), encoding="utf-8")
    log.info("Wrote STEP2_MODEL_REPORT.md (trained=%s)", status_any)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
