"""
06 - Build the minimal CLGB orogenic-gold feature stack.

Core feature slots for Step 2.2A:
    1  dist_major_shear
    2  fault_intersection_density
    3  dist_key_lithological_contact
    4  mag_1vd OR mag_visual_proxy_low_confidence
    5  mag_low_in_high_proxy OR null if not defensible
    6  gravity_gradient
    7  till_au_clr OR till_au_log
    8  till_as_clr OR till_as_log
    9  till_sb_clr OR till_sb_log
    10 till_bi_clr optional/null

Missing datasets are written as NaN columns and reported. Visual-only magnetic
products are not silently promoted to numeric geophysics.

Outputs
    data/processed/feature_stack_minimal_2km.parquet
    data/processed/feature_stack_minimal_1km.parquet
    data/outputs/STEP2_FEATURE_STACK_REPORT.md
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import get_logger, get_path, load_config  # noqa: E402

log = get_logger("06_features")

DENSITY_RADIUS_M = 5000

CORE_FEATURES = [
    "dist_major_shear",
    "fault_intersection_density",
    "dist_key_lithological_contact",
    "mag_1vd",
    "mag_visual_proxy_low_confidence",
    "mag_low_in_high_proxy",
    "gravity_gradient",
    "till_au_clr",
    "till_au_log",
    "till_as_clr",
    "till_as_log",
    "till_sb_clr",
    "till_sb_log",
    "till_bi_clr",
]
LOW_CONFIDENCE_FEATURES = {"mag_visual_proxy_low_confidence"}
TILL_VARIANT_PREFIXES = ("till_au_", "till_as_", "till_sb_")


def line_intersection_points(lines: gpd.GeoDataFrame) -> np.ndarray:
    from itertools import combinations
    from shapely.geometry import MultiPoint, Point

    geoms = list(lines.geometry)
    pts = []
    for a, b in combinations(geoms, 2):
        if not a.intersects(b):
            continue
        inter = a.intersection(b)
        if inter.is_empty:
            continue
        if isinstance(inter, Point):
            pts.append((inter.x, inter.y))
        elif isinstance(inter, MultiPoint):
            pts.extend((p.x, p.y) for p in inter.geoms)
    return np.array(pts) if pts else np.empty((0, 2))


def build_base_features(grid: gpd.GeoDataFrame, structures, bedrock) -> pd.DataFrame:
    cents = gpd.GeoSeries(gpd.points_from_xy(grid["centroid_x"], grid["centroid_y"]), crs=grid.crs)
    df = pd.DataFrame({
        "cell_id": grid["cell_id"].values,
        "centroid_x": grid["centroid_x"].values,
        "centroid_y": grid["centroid_y"].values,
        "centroid_lat": grid.get("centroid_lat"),
        "centroid_lon": grid.get("centroid_lon"),
        "grid_size_m": grid.get("grid_size_m"),
    })

    if structures is not None and not structures.empty:
        df["dist_major_shear"] = cents.distance(structures.geometry.union_all()).round(1).values
    else:
        df["dist_major_shear"] = np.nan

    if structures is not None and len(structures) > 1:
        ipts = line_intersection_points(structures)
        if len(ipts):
            tree = cKDTree(ipts)
            cc = np.c_[grid["centroid_x"].values, grid["centroid_y"].values]
            df["fault_intersection_density"] = [
                len(tree.query_ball_point(p, DENSITY_RADIUS_M)) for p in cc
            ]
        else:
            df["fault_intersection_density"] = 0
    else:
        df["fault_intersection_density"] = np.nan

    if bedrock is not None and not bedrock.empty:
        df["dist_key_lithological_contact"] = cents.distance(
            bedrock.geometry.boundary.union_all()
        ).round(1).values
    else:
        df["dist_key_lithological_contact"] = np.nan
    return df


def merge_optional(df: pd.DataFrame, path: Path, columns: list[str], provenance: dict,
                   source_label: str) -> pd.DataFrame:
    if not path.exists():
        for col in columns:
            if col not in df:
                df[col] = np.nan
            provenance[col] = f"NULL - missing {path.name}"
        return df

    src = pd.read_parquet(path)
    keep = ["cell_id"] + [c for c in src.columns if c in columns or c.startswith(TILL_VARIANT_PREFIXES)]
    df = df.merge(src[keep], on="cell_id", how="left")
    for col in columns:
        if col not in df:
            df[col] = np.nan
        if df[col].notna().any():
            provenance[col] = source_label
        else:
            provenance[col] = f"NULL - {source_label} produced no defensible values"
    return df


def classify_features(df: pd.DataFrame) -> dict:
    status = {}
    for col in CORE_FEATURES:
        if col not in df:
            df[col] = np.nan
        has_data = bool(df[col].notna().any())
        if has_data and col in LOW_CONFIDENCE_FEATURES:
            status[col] = "LOW_CONFIDENCE_PROXY"
        elif has_data:
            status[col] = "REAL"
        else:
            status[col] = "NULL"
    return status


def run_for_grid(name: str, grid_path: Path, structures, bedrock, processed: Path) -> dict:
    grid = gpd.read_file(grid_path)
    df = build_base_features(grid, structures, bedrock)
    provenance = {
        "dist_major_shear": "GTK structures (1:1M)",
        "fault_intersection_density": "GTK structures (1:1M)",
        "dist_key_lithological_contact": "GTK bedrock boundaries (1:1M)",
    }

    if name == "2km":
        df = merge_optional(
            df,
            processed / "magnetics_features_2km.parquet",
            ["mag_1vd", "mag_visual_proxy_low_confidence", "mag_low_in_high_proxy"],
            provenance,
            "local GTK aeromagnetic ECW validation/processing",
        )
        df = merge_optional(
            df,
            processed / "gravity_features_2km.parquet",
            ["gravity_gradient"],
            provenance,
            "local Bouguer BA_FIN.XYZ gradient sampled to 2 km grid",
        )
        df = merge_optional(
            df,
            processed / "till_features_au_as_sb_2km.parquet",
            ["till_au_clr", "till_au_log", "till_as_clr", "till_as_log",
             "till_sb_clr", "till_sb_log", "till_bi_clr"],
            provenance,
            "GTK till geochemistry supraregional Au-As-Sb ablation",
        )
    else:
        for col in CORE_FEATURES:
            if col not in df:
                df[col] = np.nan
                provenance[col] = "NULL - processor currently built only for 2 km grid"

    status = classify_features(df)
    out_path = processed / f"feature_stack_minimal_{name}.parquet"
    df.to_parquet(out_path, index=False)
    coverage = {f: float(df[f].notna().mean()) for f in CORE_FEATURES}
    log.info("Wrote %s (%d cells)", out_path.name, len(df))
    return {"df": df, "status": status, "coverage": coverage, "provenance": provenance}


def _feature_slot_status(status: dict) -> list[tuple[str, str]]:
    mag_slot = (
        "mag_1vd OR mag_visual_proxy_low_confidence",
        "REAL" if status.get("mag_1vd") == "REAL" else
        "LOW_CONFIDENCE_PROXY" if status.get("mag_visual_proxy_low_confidence") == "LOW_CONFIDENCE_PROXY"
        else "NULL",
    )
    low_slot = ("mag_low_in_high_proxy", status.get("mag_low_in_high_proxy", "NULL"))
    gravity = ("gravity_gradient", status.get("gravity_gradient", "NULL"))
    au = ("till_au_clr OR till_au_log",
          "REAL" if status.get("till_au_clr") == "REAL" or status.get("till_au_log") == "REAL" else "NULL")
    arsenic = ("till_as_clr OR till_as_log",
               "REAL" if status.get("till_as_clr") == "REAL" or status.get("till_as_log") == "REAL" else "NULL")
    antimony = ("till_sb_clr OR till_sb_log",
                "REAL" if status.get("till_sb_clr") == "REAL" or status.get("till_sb_log") == "REAL" else "NULL")
    bi = ("till_bi_clr (optional)", "OPTIONAL_NULL" if status.get("till_bi_clr") == "NULL" else status.get("till_bi_clr"))
    return [
        ("dist_major_shear", status.get("dist_major_shear", "NULL")),
        ("fault_intersection_density", status.get("fault_intersection_density", "NULL")),
        ("dist_key_lithological_contact", status.get("dist_key_lithological_contact", "NULL")),
        mag_slot,
        low_slot,
        gravity,
        au,
        arsenic,
        antimony,
        bi,
    ]


def main() -> int:
    cfg = load_config()
    raw = get_path(cfg, "raw")
    processed = get_path(cfg, "processed", create=True)
    outputs = get_path(cfg, "outputs", create=True)

    def _load(rel):
        path = raw / rel
        return gpd.read_file(path) if path.exists() else None

    structures = _load("gtk/structures.gpkg")
    bedrock = _load("gtk/bedrock.gpkg")

    grids = {
        "2km": outputs / "clgb_grid_2km.gpkg",
        "1km": outputs / "clgb_grid_1km.gpkg",
    }
    results = {}
    for name, path in grids.items():
        if path.exists():
            results[name] = run_for_grid(name, path, structures, bedrock, processed)
        else:
            log.warning("Grid missing: %s", path)

    if not results:
        log.error("No grids available; run 04b first.")
        return 2

    primary = results.get("2km") or next(iter(results.values()))
    slot_status = _feature_slot_status(primary["status"])
    real_count = sum(1 for _, s in slot_status if s == "REAL")
    low_count = sum(1 for _, s in slot_status if s == "LOW_CONFIDENCE_PROXY")
    null_count = sum(1 for _, s in slot_status if s == "NULL")
    optional_null_count = sum(1 for _, s in slot_status if s == "OPTIONAL_NULL")
    sufficient = real_count >= 6 and primary["status"].get("gravity_gradient") == "REAL" and (
        primary["status"].get("till_au_clr") == "REAL" or primary["status"].get("till_au_log") == "REAL"
    )

    meta = {
        "real_features_count": real_count,
        "low_confidence_proxy_features_count": low_count,
        "null_features_count": null_count,
        "optional_null_features_count": optional_null_count,
        "feature_quality_sufficient_for_validation": bool(sufficient),
        "slot_status": dict(slot_status),
        "provenance": primary["provenance"],
    }
    (outputs / "STEP2_FEATURE_STACK_METADATA.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )

    lines = [
        "# Step 2 Feature Stack Report",
        "",
        "Built the Step 2.2A CLGB feature stack with explicit nulls and provenance.",
        "",
        "## Core Feature Availability",
        "",
        "| # | feature slot | status | provenance | coverage |",
        "|---|--------------|--------|------------|----------|",
    ]
    for i, (feature, stat) in enumerate(slot_status, 1):
        if " OR " in feature:
            parts = [p.strip() for p in feature.split(" OR ")]
            cov = max(primary["coverage"].get(p, 0.0) for p in parts)
            prov = "; ".join(primary["provenance"].get(p, "") for p in parts if primary["provenance"].get(p))
        else:
            cov = primary["coverage"].get(feature.replace(" (optional)", ""), 0.0)
            prov = primary["provenance"].get(feature.replace(" (optional)", ""), "")
        lines.append(f"| {i} | `{feature}` | {stat} | {prov} | {cov:.1%} |")

    lines += [
        "",
        "## Counts",
        "",
        f"- Real features: {real_count}",
        f"- Low-confidence proxy features: {low_count}",
        f"- Null features: {null_count}",
        f"- Optional/null features: {optional_null_count}",
        f"- Feature quality sufficient for validation: {'YES' if sufficient else 'PARTIAL'}",
        "",
        "## Notes",
        "",
        "- Bi is no longer required for this interim run and remains optional/null.",
        "- Magnetics is visual-only/unreadable in this environment, so no numeric magnetic "
        "features were fabricated.",
        "- Gravity is real but regional: Bouguer XYZ, 2.5 km source grid, sampled to 2 km cells.",
        "- Till Au/As/Sb are real but sparse because CLR uses only till samples containing all "
        "three markers.",
        "",
    ]
    (outputs / "STEP2_FEATURE_STACK_REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    log.info(
        "Feature counts: real=%d low_conf=%d null=%d optional_null=%d",
        real_count, low_count, null_count, optional_null_count,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
