"""
23 - Audit Step 2.2A review candidates.

Inspects cells currently labelled `model_supported_review_candidate` and classifies
them as review candidates, not targets. The audit merges actual feature-stack values
back into the candidate table and identifies whether each cell has multi-layer
support or is dominated by one signal.

Outputs
    data/outputs/STEP2_2B_REVIEW_CANDIDATE_AUDIT.md
    data/outputs/review_candidates_audited.csv
    data/outputs/review_candidates_audited.gpkg
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import get_logger, get_path, load_config  # noqa: E402

log = get_logger("23_candidate_audit")

MODEL_FEATURES = [
    "dist_major_shear",
    "fault_intersection_density",
    "dist_key_lithological_contact",
    "gravity_gradient",
    "till_au_clr",
    "till_as_clr",
    "till_sb_clr",
]


def _norm_high(s: pd.Series) -> pd.Series:
    s = s.astype(float)
    lo, hi = s.min(), s.max()
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return pd.Series(0.0, index=s.index)
    return ((s - lo) / (hi - lo)).clip(0, 1)


def _norm_low(s: pd.Series) -> pd.Series:
    return 1.0 - _norm_high(s)


def load_importances(outputs: Path) -> dict[str, float]:
    path = outputs / "STEP2_MODEL_FEATURE_IMPORTANCE.json"
    if not path.exists():
        return {}
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
        return {k: float(v) for k, v in meta.get("2km", {}).get("feature_importances", {}).items()}
    except Exception:  # noqa: BLE001
        return {}


def contribution_scores(all_features: pd.DataFrame, audit: pd.DataFrame, importances: dict[str, float]):
    feature_scores = pd.DataFrame(index=all_features.index)
    if "dist_major_shear" in all_features:
        feature_scores["dist_major_shear"] = _norm_low(all_features["dist_major_shear"])
    if "fault_intersection_density" in all_features:
        feature_scores["fault_intersection_density"] = _norm_high(all_features["fault_intersection_density"].fillna(0))
    if "dist_key_lithological_contact" in all_features:
        feature_scores["dist_key_lithological_contact"] = _norm_low(all_features["dist_key_lithological_contact"])
    if "gravity_gradient" in all_features:
        feature_scores["gravity_gradient"] = _norm_high(all_features["gravity_gradient"])
    for col in ["till_au_clr", "till_as_clr", "till_sb_clr"]:
        if col in all_features:
            feature_scores[col] = _norm_high(all_features[col]).fillna(0.0)

    contrib = pd.DataFrame(index=audit.index)
    for feature in MODEL_FEATURES:
        if feature not in feature_scores:
            continue
        contrib[feature] = feature_scores.loc[audit.index, feature].fillna(0.0) * importances.get(feature, 0.0)
    top_names = []
    top_fracs = []
    for _, row in contrib.iterrows():
        positive = row[row > 0].sort_values(ascending=False)
        total = float(positive.sum())
        if positive.empty or total <= 0:
            top_names.append("")
            top_fracs.append(0.0)
        else:
            top_names.append(";".join(f"{k}:{v:.4f}" for k, v in positive.head(3).items()))
            top_fracs.append(float(positive.iloc[0] / total))
    return top_names, top_fracs


def main() -> int:
    cfg = load_config()
    processed = get_path(cfg, "processed")
    outputs = get_path(cfg, "outputs", create=True)

    cand_path = outputs / "geology_ranked_modelling_candidates.gpkg"
    if not cand_path.exists():
        raise FileNotFoundError(f"Candidate table missing: {cand_path}")
    candidates = gpd.read_file(cand_path).to_crs(3067)
    review = candidates[candidates["final_status"] == "model_supported_review_candidate"].copy()
    features = pd.read_parquet(processed / "feature_stack_minimal_2km.parquet")
    features = features.set_index("cell_id")

    selected_cols = [
        "dist_major_shear",
        "fault_intersection_density",
        "dist_key_lithological_contact",
        "gravity_gradient",
        "till_au_clr",
        "till_as_clr",
        "till_sb_clr",
        "till_au_clr_shift_500m",
        "till_as_clr_shift_500m",
        "till_sb_clr_shift_500m",
        "till_au_clr_shift_1km",
        "till_as_clr_shift_1km",
        "till_sb_clr_shift_1km",
        "till_au_clr_shift_2km",
        "till_as_clr_shift_2km",
        "till_sb_clr_shift_2km",
    ]
    selected_cols = [c for c in selected_cols if c in features.columns]
    audit = review.merge(features[selected_cols], left_on="cell_id", right_index=True, how="left",
                         suffixes=("", "_feature"))
    audit = audit.set_index("cell_id", drop=False)

    gravity_threshold = float(features["gravity_gradient"].quantile(0.75))
    till_thresholds = {
        c: float(features[c].dropna().quantile(0.75))
        for c in ["till_au_clr", "till_as_clr", "till_sb_clr"]
        if c in features and features[c].notna().any()
    }

    audit["structure_signal"] = (
        (audit["dist_major_shear"] <= 2000)
        | (audit["fault_intersection_density"].fillna(0) > 0)
    )
    audit["lithology_signal"] = audit["dist_key_lithological_contact"] <= 1000
    audit["structure_lithology_domain"] = audit["structure_signal"] | audit["lithology_signal"]
    audit["gravity_signal"] = audit["gravity_gradient"] >= gravity_threshold
    till_signal = pd.Series(False, index=audit.index)
    for col, threshold in till_thresholds.items():
        till_signal = till_signal | (audit[col].notna() & (audit[col] >= threshold))
    audit["till_signal"] = till_signal
    audit["signal_domain_count"] = (
        audit[["structure_lithology_domain", "gravity_signal", "till_signal"]].sum(axis=1).astype(int)
    )
    audit["multi_layer_convergence"] = audit["signal_domain_count"] >= 2

    importances = load_importances(outputs)
    top_contrib, top_frac = contribution_scores(features, audit, importances)
    audit["top_contributing_features"] = top_contrib
    audit["top_contribution_fraction"] = np.round(top_frac, 4)
    audit["single_signal_hallucination_flag"] = audit["top_contribution_fraction"] >= 0.75

    def status(row):
        if row["single_signal_hallucination_flag"]:
            return "single_signal_hallucination"
        if row["multi_layer_convergence"]:
            return "multi_layer_review_candidate"
        if row["gravity_signal"] and not row["structure_lithology_domain"] and not row["till_signal"]:
            return "gravity_only_candidate"
        if row["till_signal"] and not row["structure_lithology_domain"] and not row["gravity_signal"]:
            return "till_only_candidate"
        if row["structure_lithology_domain"] and not row["gravity_signal"] and not row["till_signal"]:
            return "structure_only_candidate"
        return "insufficient_data"

    audit["audit_status"] = audit.apply(status, axis=1)

    out_cols = [
        "cell_id",
        "centroid_lat",
        "centroid_lon",
        "cluster_id",
        "legal_status_conservative",
        "legal_status_strict_active_only",
        "restriction_status",
        "model_score",
        "baseline_score",
        "model_minus_baseline",
        "gravity_gradient",
        "till_au_clr",
        "till_as_clr",
        "till_sb_clr",
        "till_au_clr_shift_500m",
        "till_as_clr_shift_500m",
        "till_sb_clr_shift_500m",
        "till_au_clr_shift_1km",
        "till_as_clr_shift_1km",
        "till_sb_clr_shift_1km",
        "till_au_clr_shift_2km",
        "till_as_clr_shift_2km",
        "till_sb_clr_shift_2km",
        "dist_major_shear",
        "dist_key_lithological_contact",
        "fault_intersection_density",
        "top_contributing_features",
        "top_contribution_fraction",
        "structure_signal",
        "lithology_signal",
        "structure_lithology_domain",
        "gravity_signal",
        "till_signal",
        "signal_domain_count",
        "multi_layer_convergence",
        "false_positive_flags",
        "single_signal_hallucination_flag",
        "audit_status",
        "geometry",
    ]
    out_cols = [c for c in out_cols if c in audit.columns]
    out = gpd.GeoDataFrame(audit[out_cols].copy(), geometry="geometry", crs=review.crs)
    out = out.reset_index(drop=True)
    csv_path = outputs / "review_candidates_audited.csv"
    gpkg_path = outputs / "review_candidates_audited.gpkg"
    out.drop(columns="geometry").to_csv(csv_path, index=False)
    out.to_file(gpkg_path, layer="review_candidates_audited", driver="GPKG")

    counts = out["audit_status"].value_counts().to_dict()
    lines = [
        "# Step 2.2B Review Candidate Audit",
        "",
        "These are review candidates only. They are not targets and no target memos are allowed from this audit.",
        "",
        "## Thresholds Used",
        "",
        f"- Gravity support: `gravity_gradient >= {gravity_threshold:.4g}` (75th percentile of all 2 km cells).",
        "- Structure/lithology support: within 2 km of major structure, nonzero structure intersection density, or within 1 km of a lithological contact.",
        f"- Till support: any available Au/As/Sb CLR value above its 75th percentile among non-null till cells: {till_thresholds}.",
        "- Single-signal hallucination: top approximate feature contribution >= 75%.",
        "",
        "## Status Counts",
        "",
        "| audit_status | cells |",
        "|--------------|-------|",
    ]
    for key, value in sorted(counts.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {key} | {value} |")

    lines += [
        "",
        "## Summary",
        "",
        f"- Review candidates audited: {len(out)}",
        f"- Multi-layer review candidates: {int((out['audit_status'] == 'multi_layer_review_candidate').sum())}",
        f"- Gravity-only candidates: {int((out['audit_status'] == 'gravity_only_candidate').sum())}",
        f"- Till-only candidates: {int((out['audit_status'] == 'till_only_candidate').sum())}",
        f"- Structure-only candidates: {int((out['audit_status'] == 'structure_only_candidate').sum())}",
        f"- Single-signal hallucinations: {int((out['audit_status'] == 'single_signal_hallucination').sum())}",
        "- Allowed for target memo: NO.",
        "",
        "## Top Rows by Geology Composite / Existing Review Order",
        "",
        "| cell_id | lat | lon | audit_status | model | baseline | gravity_gradient | till present | top contributing features | flags |",
        "|---------|-----|-----|--------------|-------|----------|------------------|--------------|---------------------------|-------|",
    ]
    top = out.head(25)
    for _, row in top.iterrows():
        till_present = bool(pd.notna(row.get("till_au_clr")) or pd.notna(row.get("till_as_clr")) or pd.notna(row.get("till_sb_clr")))
        lines.append(
            f"| {row['cell_id']} | {row['centroid_lat']:.5f} | {row['centroid_lon']:.5f} | "
            f"{row['audit_status']} | {row['model_score']} | {row['baseline_score']} | "
            f"{row['gravity_gradient']:.4g} | {till_present} | "
            f"{row['top_contributing_features']} | {row['false_positive_flags']} |"
        )

    lines += [
        "",
        "## Interpretation",
        "",
        "- Most review cells have no till value because till coverage is sparse; absence of till support is not evidence against a cell, but it prevents multi-layer geochemical convergence.",
        "- Numeric magnetics are still missing, so no candidate has magnetic support.",
        "- Candidate statuses should not be upgraded until ablation and top-k validation are stronger.",
        "",
    ]
    report_path = outputs / "STEP2_2B_REVIEW_CANDIDATE_AUDIT.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    log.info("Wrote %s, %s, %s", report_path, csv_path, gpkg_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
