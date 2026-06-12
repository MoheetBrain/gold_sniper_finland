"""
run_step2_minimal — Orchestrate Step 2 and emit geology-ranked MODELLING CANDIDATES.

Runs 05->06->07->08->09->10->11->11b->11c and 04c (restriction shield), then fuses
everything on the 2 km CLGB grid into ranked modelling candidates gated by:
    Tukes legal status (conservative + strict-active)  AND
    restriction masks (Natura 2000 / protected / water) AND
    feature/validation sufficiency.

NOTHING here is a "gold target". Outputs are modelling candidates / review items only.

OUTPUTS
    data/outputs/geology_ranked_modelling_candidates.gpkg
    data/outputs/top_20_geology_ranked_modelling_candidates.csv
    data/outputs/STEP2_LEGAL_RESTRICTION_STATUS.md
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import get_logger, get_path, import_script, load_config  # noqa: E402

log = get_logger("run_step2")
SCRIPTS = Path(__file__).resolve().parent
_m02 = import_script("02_mask_taken_areas.py", "m02")
_m02c = import_script("02c_classify_tukes_status.py", "m02c")

STEPS = ["05_load_gtk_layers.py", "21_validate_local_geophysics.py",
         "06c_process_magnetics.py", "06d_process_gravity.py",
         "19_build_interim_till_features_au_as_sb.py", "06_build_minimal_feature_stack.py",
         "07_build_clgb_positive_labels.py", "08_build_unlabelled_background.py",
         "09_make_spatial_blocks.py", "10_distance_to_fault_baseline.py",
         "11_train_baseline_xgboost_or_pu.py", "11b_topk_capture_metrics.py",
         "04c_build_restriction_masks.py"]


def _norm(s: pd.Series) -> pd.Series:
    s = s.astype(float)
    lo, hi = s.min(), s.max()
    return (s - lo) / (hi - lo) if hi > lo else pd.Series(0.0, index=s.index)


def _component_average(df: pd.DataFrame, cols: list[str]) -> pd.Series:
    valid = [c for c in cols if c in df.columns and df[c].notna().any()]
    if not valid:
        return pd.Series(np.nan, index=df.index)
    return pd.concat([_norm(df[c]) for c in valid], axis=1).mean(axis=1).round(4)


def _weighted_composite(df: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    num = pd.Series(0.0, index=df.index)
    den = pd.Series(0.0, index=df.index)
    for col, weight in weights.items():
        if col not in df.columns:
            continue
        valid = df[col].notna()
        num.loc[valid] += df.loc[valid, col].astype(float) * weight
        den.loc[valid] += weight
    out = num / den.replace(0, np.nan)
    return out.round(4)


def _till_score(df: pd.DataFrame, label: str) -> pd.Series:
    cols = []
    for element in ["au", "as", "sb"]:
        for suffix in ["clr", "log"]:
            col = f"till_{element}_{suffix}_{label}"
            if col in df.columns:
                cols.append(col)
    if label == "raw" and not cols:
        for element in ["au", "as", "sb"]:
            for suffix in ["clr", "log"]:
                col = f"till_{element}_{suffix}"
                if col in df.columns:
                    cols.append(col)
    return _component_average(df, cols)


def main(run_steps: bool = True) -> int:
    cfg = load_config()
    processed = get_path(cfg, "processed")
    outputs = get_path(cfg, "outputs")
    size = cfg["step2"]["primary_grid"].split("_")[-1].replace(".gpkg", "")

    if run_steps:
        for s in STEPS:
            log.info(">>> %s", s)
            subprocess.run([sys.executable, str(SCRIPTS / s)], check=True)

    # --- Assemble the 2 km grid with everything ---
    grid = gpd.read_file(outputs / cfg["step2"]["primary_grid"])
    feat = pd.read_parquet(processed / f"feature_stack_minimal_{size}.parquet")
    labels = pd.read_parquet(processed / f"cell_labels_{size}.parquet")
    roles = pd.read_parquet(processed / f"cell_role_{size}.parquet")
    model = pd.read_parquet(processed / f"model_scores_{size}.parquet")
    base = pd.read_parquet(processed / f"baseline_scores_{size}.parquet")
    df = (grid.merge(feat, on="cell_id", suffixes=("", "_f"))
          .merge(labels, on="cell_id").merge(roles, on="cell_id")
          .merge(model, on="cell_id").merge(base, on="cell_id"))

    # --- Tukes legal status on 2 km (conservative + strict-active) ---
    rights = _m02c.load_classified_rights(cfg)
    cons = _m02.compute_cell_status(grid, rights, cfg).set_index("cell_id")["legal_status"]
    strict = _m02.compute_cell_status(grid, rights[rights["legal_class"] == "active"], cfg)\
        .set_index("cell_id")["legal_status"]
    df["legal_status_conservative"] = df["cell_id"].map(cons)
    df["legal_status_strict_active_only"] = df["cell_id"].map(strict)

    # --- Restriction overlap on 2 km (hard layers) ---
    rmask = processed / "restriction_masks.gpkg"
    if rmask.exists():
        rm = gpd.read_file(rmask)
        hard = rm[rm["is_hard"]] if "is_hard" in rm.columns else rm
        hpoly = hard.geometry.union_all() if not hard.empty else None
        df["restriction_overlap_pct"] = df.geometry.apply(
            lambda g: round(g.intersection(hpoly).area / g.area * 100, 2) if (hpoly and g.area) else 0.0)
    else:
        df["restriction_overlap_pct"] = 0.0
    thr = float(cfg["restrictions"].get("restricted_max_open_pct", 1.0))
    df["restriction_status"] = np.where(df["restriction_overlap_pct"] > thr,
                                        "restricted", "clear")

    # --- Component scores (transparent; null where data missing) ---
    df["structural_score"] = (
        0.6 * _norm(1.0 / (1.0 + df["dist_major_shear"] / 1000.0)) +
        0.4 * _norm(df["fault_intersection_density"].fillna(0))
    ).round(4)
    df["lithology_score"] = _norm(1.0 / (1.0 + df["dist_key_lithological_contact"] / 1000.0)).round(4)
    df["geophysics_score"] = _component_average(
        df,
        ["mag_1vd", "mag_visual_proxy_low_confidence", "mag_low_in_high_proxy",
         "gravity_gradient"],
    )
    df["till_geochem_score_raw"] = _till_score(df, "raw")
    df["till_geochem_score_shifted_500m"] = _till_score(df, "shift_500m")
    df["till_geochem_score_shifted_1km"] = _till_score(df, "shift_1km")
    df["till_geochem_score_shifted_2km"] = _till_score(df, "shift_2km")
    has_till = df["till_geochem_score_raw"].notna().any()
    df["glacial_correction_confidence"] = np.where(
        has_till, "provisional_ablation_sparse_till", "n/a (no till data)"
    )
    df["distance_to_major_shear"] = df["dist_major_shear"].round(1)
    df["baseline_score"] = df["score_distfault"].round(4)
    df["model_score"] = df["model_score"].round(4)
    df["model_minus_baseline"] = (df["model_score"] - df["baseline_score"]).round(4)

    # Transparent geology composite used for ordering; weights are renormalized per cell
    # when sparse till values are absent.
    df["geology_composite"] = _weighted_composite(df, {
        "structural_score": 0.35,
        "lithology_score": 0.20,
        "geophysics_score": 0.25,
        "till_geochem_score_raw": 0.20,
    })
    df["topk_percentile"] = (df["geology_composite"].rank(pct=True) * 100).round(1)

    # --- Validation verdict drives honesty of statuses ---
    verdict = {}
    vj = outputs / "STEP2_VALIDATION.json"
    if vj.exists():
        verdict = json.loads(vj.read_text())
    model_beats = bool(verdict.get("model_beats_distfault"))
    enough = bool(verdict.get("enough_data"))
    magnetics_low_confidence = bool(verdict.get("magnetics_low_confidence"))
    single_signal = bool(verdict.get("single_signal_hallucination"))

    # --- False-positive flags ---
    def flags(row):
        f = []
        if not model_beats:
            f.append("model_failed_baseline")
        if magnetics_low_confidence:
            f.append("magnetics_low_confidence")
        if single_signal:
            f.append("single_signal_hallucination")
        if pd.isna(row.get("mag_1vd", np.nan)):
            f.append("no_numeric_mag_1vd")
        if pd.isna(row.get("mag_low_in_high_proxy", np.nan)):
            f.append("no_defensible_mag_low_in_high")
        if pd.isna(row.get("gravity_gradient", np.nan)):
            f.append("no_gravity_gradient")
        if pd.isna(row.get("till_geochem_score_raw", np.nan)):
            f.append("no_cell_till_au_as_sb")
        if row["fault_intersection_density"] in (0, np.nan):
            f.append("no_structural_intersection")
        if not row.get("geophysics_score", np.nan) == row.get("geophysics_score", np.nan):
            f.append("no_geophysics")
        return ";".join(f)
    df["false_positive_flags"] = df.apply(flags, axis=1)

    # --- Final status (honest precedence) ---
    def final_status(row):
        if row["restriction_status"] == "restricted":
            return "restricted_area"
        if row["legal_status_conservative"] != "open":
            return "legally_blocked"
        if not enough:
            return "insufficient_data"
        if model_beats and row["topk_percentile"] >= 90:
            return "model_supported_review_candidate"
        if row["topk_percentile"] >= 90:
            return "needs_manual_geology_review"
        return "insufficient_data"
    df["final_status"] = df.apply(final_status, axis=1)
    df["cluster_id"] = None  # (clusters are computed per-mask in Step 1.5; left null here)

    # --- Output columns (exact spec) ---
    cols = ["cell_id", "cluster_id", "centroid_lat", "centroid_lon",
            "legal_status_conservative", "legal_status_strict_active_only",
            "restriction_status", "structural_score", "lithology_score",
            "geophysics_score", "till_geochem_score_raw",
            "till_geochem_score_shifted_500m", "till_geochem_score_shifted_1km",
            "till_geochem_score_shifted_2km", "glacial_correction_confidence",
            "distance_to_major_shear", "model_score", "baseline_score",
            "model_minus_baseline", "topk_percentile", "false_positive_flags",
            "final_status", "geology_composite", "restriction_overlap_pct", "geometry"]
    out = gpd.GeoDataFrame(df[cols], geometry="geometry", crs=grid.crs)
    out.to_file(outputs / "geology_ranked_modelling_candidates.gpkg",
                layer="geology_ranked_modelling_candidates", driver="GPKG")

    # Top 20: open + unrestricted, ranked by transparent geology composite.
    pursue = out[(out["legal_status_conservative"] == "open") &
                 (out["restriction_status"] == "clear")].copy()
    top20 = pursue.sort_values("geology_composite", ascending=False).head(20)
    top20.drop(columns="geometry").to_csv(
        outputs / "top_20_geology_ranked_modelling_candidates.csv", index=False)
    log.info("Candidates: %d cells | open+clear=%d | top20 written", len(out), len(pursue))

    # --- Legal/restriction status report ---
    sc = out["final_status"].value_counts().to_dict()
    L = ["# Step 2 Legal & Restriction Status", "",
         "No candidate is 'legally available' unless it passes Tukes cadastre AND",
         "restriction masks (Natura 2000 / protected areas / water).", "",
         "## 2 km CLGB candidate status counts", "",
         "| final_status | cells |", "|--------------|-------|"]
    for k, v in sorted(sc.items(), key=lambda x: -x[1]):
        L.append(f"| {k} | {v} |")
    n_open = int((out["legal_status_conservative"] == "open").sum())
    n_clear = int((out["restriction_status"] == "clear").sum())
    L += ["",
          f"- Tukes-open (conservative) 2 km cells: **{n_open}** / {len(out)}",
          f"- Restriction-clear 2 km cells: **{n_clear}** / {len(out)}",
          f"- **Open AND restriction-clear: {len(pursue)}** (the only legally-plausible set)",
          "",
          "## Gates applied",
          "1. Tukes cadastre (conservative): excludes active+pending+cooling-off rights.",
          "2. Restriction mask: Natura 2000, protected/conservation areas, groundwater.",
          f"3. Validation verdict: {verdict.get('verdict', 'unknown')}. Candidates are",
          "   geology-composite ordered and flagged; no output is a gold target.",
          "",
          "## What still blocks 'legally available'",
          "- Restriction set lacks Sámi Homeland, national parks/wilderness, surface water",
          "  bodies (lakes/rivers) and infrastructure — add before any reservation claim.",
          "- Groundwater areas are treated as HARD here (conservative); confirm their true",
          "  legal effect on exploration.", ""]
    (outputs / "STEP2_LEGAL_RESTRICTION_STATUS.md").write_text("\n".join(L), encoding="utf-8")
    log.info("Wrote STEP2_LEGAL_RESTRICTION_STATUS.md | statuses=%s", sc)
    return 0


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-run-steps", action="store_true",
                    help="skip re-running 05-11c/04c; just rebuild the ranking")
    a = ap.parse_args()
    raise SystemExit(main(run_steps=not a.no_run_steps))
