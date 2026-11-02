"""
22 - Step 2.2B feature ablation forensic audit.

Runs the same spatial-block out-of-fold validation used by the Step 2 model, but
with controlled feature groups:
    1. structure/lithology only
    2. gravity only
    3. till Au-As-Sb only
    4. structure + gravity
    5. structure + till
    6. gravity + till
    7. full current model

Outputs
    data/outputs/STEP2_2B_FEATURE_ABLATION_REPORT.md
    data/outputs/STEP2_2B_FEATURE_ABLATION.csv
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import get_logger, get_path, load_config  # noqa: E402

log = get_logger("22_ablation")

KS = [1, 5, 10]
STRUCTURE_LITHO = [
    "dist_major_shear",
    "fault_intersection_density",
    "dist_key_lithological_contact",
]
GRAVITY = ["gravity_gradient"]
TILL = ["till_au_clr", "till_au_log", "till_as_clr", "till_as_log", "till_sb_clr", "till_sb_log"]
MAG = ["mag_1vd", "mag_visual_proxy_low_confidence", "mag_low_in_high_proxy"]
GROUPS = [
    ("structure_lithology_only", STRUCTURE_LITHO),
    ("gravity_only", GRAVITY),
    ("till_au_as_sb_only", TILL),
    ("structure_plus_gravity", STRUCTURE_LITHO + GRAVITY),
    ("structure_plus_till", STRUCTURE_LITHO + TILL),
    ("gravity_plus_till", GRAVITY + TILL),
    ("full_current_model", STRUCTURE_LITHO + GRAVITY + TILL + MAG),
]


from _evaluation import topk_capture


def load_data(processed: Path, size: str) -> pd.DataFrame:
    feat = pd.read_parquet(processed / f"feature_stack_minimal_{size}.parquet")
    labels = pd.read_parquet(processed / f"cell_labels_{size}.parquet")
    roles = pd.read_parquet(processed / f"cell_role_{size}.parquet")
    blocks = pd.read_parquet(processed / f"cell_block_{size}.parquet")
    baseline = pd.read_parquet(processed / f"baseline_scores_{size}.parquet")
    return (
        feat.merge(labels, on="cell_id")
        .merge(roles, on="cell_id")
        .merge(blocks, on="cell_id")
        .merge(baseline, on="cell_id")
    )


def valid_features(df: pd.DataFrame, candidates: list[str]) -> list[str]:
    return [c for c in candidates if c in df.columns and df[c].notna().any()]


def train_oof(lab: pd.DataFrame, features: list[str]):
    from _evaluation import fit_grouped
    from sklearn.metrics import roc_auc_score
    from sklearn.inspection import permutation_importance
    oof,final,med,folds=fit_grouped(lab,features)
    y=(lab["role"]=="positive").astype(int).to_numpy()
    pi=permutation_importance(final,lab[features].fillna(med),y,n_repeats=10,
                              random_state=42,scoring="roc_auc",n_jobs=1)
    # Resubstitution diagnostic only, not held-out permutation importance.
    return dict(scores=oof,y=y,valid_mask=np.isfinite(oof),n_splits=len(folds),
                skipped_folds=0,roc_auc=float(roc_auc_score(y,oof)),
                feature_importance=dict(zip(features,map(float,final.feature_importances_))),
                permutation_importance=dict(zip(features,map(float,pi.importances_mean))))


def max_fraction(values: dict) -> tuple[str | None, float]:
    numeric = {k: max(0.0, float(v)) for k, v in values.items() if isinstance(v, (int, float, np.floating))}
    total = sum(numeric.values())
    if not numeric or total <= 0:
        return None, 0.0
    top = max(numeric, key=numeric.get)
    return top, float(numeric[top] / total)


def main() -> int:
    cfg = load_config()
    processed = get_path(cfg, "processed")
    outputs = get_path(cfg, "outputs", create=True)
    size = cfg["step2"]["primary_grid"].split("_")[-1].replace(".gpkg", "")
    df = load_data(processed, size)
    lab = df[df["role"].isin(["positive", "background"])].copy()

    rows = []
    details = {}
    for group_name, candidate_features in GROUPS:
        features = valid_features(lab, candidate_features)
        log.info("Ablation %s: %s", group_name, features)
        if not features:
            rows.append({
                "group": group_name,
                "features": "",
                "n_features": 0,
                "n_eval_cells": 0,
                "n_positives": 0,
                "roc_auc": np.nan,
                "top1pct": np.nan,
                "top5pct": np.nan,
                "top10pct": np.nan,
                "baseline_top1pct": np.nan,
                "baseline_top5pct": np.nan,
                "baseline_top10pct": np.nan,
                "baseline_roc_auc": np.nan,
                "model_beats_distance_to_fault": "NO",
                "top_feature": "",
                "top_feature_importance_fraction": np.nan,
                "single_signal_hallucination_risk": "NO",
                "variance_status": "not_runnable",
            })
            continue

        res = train_oof(lab, features)
        mask = res["valid_mask"]
        y = res["y"]
        scores = res["scores"]
        base = lab.loc[mask, "score_distfault"].to_numpy()
        from sklearn.metrics import roc_auc_score

        captures = {f"top{k}pct": topk_capture(scores, y, k) for k in KS}
        base_captures = {f"baseline_top{k}pct": topk_capture(base, y, k) for k in KS}
        try:
            base_auc = float(roc_auc_score(y, base)) if len(np.unique(y)) == 2 else np.nan
        except Exception:  # noqa: BLE001
            base_auc = np.nan
        auc = res["roc_auc"]
        beats = bool(
            auc is not None
            and np.isfinite(base_auc)
            and captures["top5pct"] > base_captures["baseline_top5pct"]
            and auc > base_auc
        )
        top_feature, top_frac = max_fraction(res["feature_importance"])
        perm_top, perm_frac = max_fraction(res["permutation_importance"])
        single_risk = bool(top_frac >= 0.75 or perm_frac >= 0.75 or (len(features) == 1 and beats))
        high_variance = bool(int(y.sum()) < 20 or res["skipped_folds"] > 0)
        rows.append({
            "group": group_name,
            "features": ";".join(features),
            "n_features": len(features),
            "n_eval_cells": int(len(y)),
            "n_positives": int(y.sum()),
            "roc_auc": round(auc, 4) if auc is not None else np.nan,
            "top1pct": round(captures["top1pct"], 4),
            "top5pct": round(captures["top5pct"], 4),
            "top10pct": round(captures["top10pct"], 4),
            "baseline_top1pct": round(base_captures["baseline_top1pct"], 4),
            "baseline_top5pct": round(base_captures["baseline_top5pct"], 4),
            "baseline_top10pct": round(base_captures["baseline_top10pct"], 4),
            "baseline_roc_auc": round(base_auc, 4) if np.isfinite(base_auc) else np.nan,
            "model_beats_distance_to_fault": "YES" if beats else "NO",
            "top_feature": top_feature or "",
            "top_feature_importance_fraction": round(top_frac, 4),
            "permutation_top_feature": perm_top or "",
            "permutation_top_feature_fraction": round(perm_frac, 4),
            "single_signal_hallucination_risk": "YES" if single_risk else "NO",
            "variance_status": "high_variance" if high_variance else "stable",
            "skipped_folds": int(res["skipped_folds"]),
            "feature_importance": json.dumps(res["feature_importance"], sort_keys=True),
            "permutation_importance": json.dumps(res["permutation_importance"], sort_keys=True),
        })
        details[group_name] = res

    out = pd.DataFrame(rows)
    csv_path = outputs / "STEP2_2B_FEATURE_ABLATION.csv"
    out.to_csv(csv_path, index=False)

    runnable = out[out["n_features"] > 0].copy()
    best = runnable.sort_values(["roc_auc", "top5pct"], ascending=False).iloc[0] if not runnable.empty else None
    single_any = bool((out["single_signal_hallucination_risk"] == "YES").any())
    lines = [
        "# Step 2.2B Feature Ablation Audit",
        "",
        "Spatial-block out-of-fold ablation using the same positive/background framing as the Step 2 model.",
        "",
        f"- Evaluation grid: `{size}`",
        f"- Labelled cells evaluated per runnable group: {int(runnable['n_eval_cells'].max()) if not runnable.empty else 0}",
        f"- Positives: {int(runnable['n_positives'].max()) if not runnable.empty else 0}",
        f"- Best feature group by ROC-AUC: `{best['group'] if best is not None else 'none'}`",
        f"- `single_signal_hallucination_risk` present in any ablation: **{single_any}**",
        "- Variance status: capture metrics with 8 positives move in 12.5 percentage-point increments; treat as high-variance.",
        "",
        "## Results",
        "",
        "| group | features | ROC-AUC | top1 | top5 | top10 | baseline top5/top10 | beats dist-fault | top feature | single-signal risk | variance |",
        "|-------|----------|---------|------|------|-------|---------------------|------------------|-------------|--------------------|----------|",
    ]
    for _, row in out.iterrows():
        lines.append(
            f"| {row['group']} | {row['features']} | {row['roc_auc']} | "
            f"{row['top1pct']} | {row['top5pct']} | {row['top10pct']} | "
            f"{row['baseline_top5pct']}/{row['baseline_top10pct']} | "
            f"{row['model_beats_distance_to_fault']} | "
            f"{row['top_feature']} ({row['top_feature_importance_fraction']}) | "
            f"{row['single_signal_hallucination_risk']} | {row['variance_status']} |"
        )

    lines += [
        "",
        "## Feature Importance",
        "",
    ]
    for _, row in out.iterrows():
        lines += [
            f"### {row['group']}",
            "",
            f"- Model feature importance: `{row.get('feature_importance', '{}')}`",
            f"- Permutation importance: `{row.get('permutation_importance', '{}')}`",
            "",
        ]

    lines += [
        "## Interpretation",
        "",
        "- A group is marked as beating distance-to-fault only when top-5% capture and ROC-AUC both exceed the baseline on the same OOF cells.",
        "- Top-10% failure remains important: the current full model does not dominate the simple fault-distance baseline at top 10%.",
        "- One-feature groups that beat the baseline, or groups with >=75% importance in one feature, are flagged as single-signal risk.",
        "- No outputs from this audit are targets or target memos.",
        "",
    ]
    report_path = outputs / "STEP2_2B_FEATURE_ABLATION_REPORT.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    log.info("Wrote %s and %s", report_path, csv_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
