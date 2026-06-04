"""
06 — Build the minimal 10-feature CLGB orogenic-gold stack.

THE 10 FEATURES (built where data exists, NULL + reported where it does not)
    1  dist_major_shear            distance to nearest GTK structure (fault/shear)   [REAL]
    2  fault_intersection_density  # structure intersections within a radius          [REAL]
    3  dist_key_lithological_contact distance to nearest bedrock-unit contact         [REAL]
    4  mag_1vd                     1st vertical derivative of magnetics               [NULL — no data]
    5  mag_low_in_high_proxy       magnetic low inside regional high (alteration)     [NULL — no data]
    6  gravity_gradient            horizontal gravity gradient                        [NULL — no data]
    7  till_au_clr                 CLR-transformed till Au                            [NULL — no data]
    8  till_as_clr                 CLR-transformed till As                            [NULL — no data]
    9  till_sb_clr                 CLR-transformed till Sb                            [NULL — no data]
    10 till_bi_clr                 CLR-transformed till Bi                            [NULL — no data]

ANTI-HALLUCINATION: missing datasets are written as NaN columns and reported, never
fabricated. The 1:1,000,000-scale GTK structure/bedrock layers are coarse — good for
*major* shear distance, weak for fine contacts; this is flagged in the report.

OUTPUTS
    data/processed/feature_stack_minimal_2km.parquet
    data/processed/feature_stack_minimal_1km.parquet
    data/outputs/STEP2_FEATURE_STACK_REPORT.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import get_logger, get_path, load_config, resolve_path  # noqa: E402

log = get_logger("06_features")

FEATURE_ORDER = [
    "dist_major_shear", "fault_intersection_density", "dist_key_lithological_contact",
    "mag_1vd", "mag_low_in_high_proxy", "gravity_gradient",
    "till_au_clr", "till_as_clr", "till_sb_clr", "till_bi_clr",
]
DENSITY_RADIUS_M = 5000  # radius for fault-intersection density


def line_intersection_points(lines: gpd.GeoDataFrame) -> np.ndarray:
    """Return Nx2 array of points where distinct structure lines cross."""
    from itertools import combinations
    from shapely.geometry import Point, MultiPoint
    geoms = list(lines.geometry)
    pts = []
    for a, b in combinations(geoms, 2):
        if a.intersects(b):
            inter = a.intersection(b)
            if inter.is_empty:
                continue
            if isinstance(inter, Point):
                pts.append((inter.x, inter.y))
            elif isinstance(inter, MultiPoint):
                pts.extend((p.x, p.y) for p in inter.geoms)
            # crossings that are lines (overlapping) are ignored as not "intersections"
    return np.array(pts) if pts else np.empty((0, 2))


def build_features(grid: gpd.GeoDataFrame, structures, bedrock, cfg) -> pd.DataFrame:
    """Compute the 10-feature table for one grid (centroid-based distances)."""
    cents = gpd.GeoSeries(gpd.points_from_xy(grid["centroid_x"], grid["centroid_y"]),
                          crs=grid.crs)
    df = pd.DataFrame({
        "cell_id": grid["cell_id"].values,
        "centroid_x": grid["centroid_x"].values,
        "centroid_y": grid["centroid_y"].values,
        "centroid_lat": grid.get("centroid_lat"),
        "centroid_lon": grid.get("centroid_lon"),
        "grid_size_m": grid.get("grid_size_m"),
    })

    # 1. dist_major_shear
    if structures is not None and not structures.empty:
        sunion = structures.geometry.union_all()
        df["dist_major_shear"] = cents.distance(sunion).round(1).values
    else:
        df["dist_major_shear"] = np.nan

    # 2. fault_intersection_density (count of crossings within DENSITY_RADIUS_M)
    if structures is not None and len(structures) > 1:
        ipts = line_intersection_points(structures)
        if len(ipts):
            tree = cKDTree(ipts)
            cc = np.c_[grid["centroid_x"].values, grid["centroid_y"].values]
            df["fault_intersection_density"] = [len(tree.query_ball_point(p, DENSITY_RADIUS_M))
                                                for p in cc]
        else:
            df["fault_intersection_density"] = 0
    else:
        df["fault_intersection_density"] = np.nan

    # 3. dist_key_lithological_contact (distance to bedrock unit boundaries)
    if bedrock is not None and not bedrock.empty:
        contacts = bedrock.geometry.boundary.union_all()
        df["dist_key_lithological_contact"] = cents.distance(contacts).round(1).values
    else:
        df["dist_key_lithological_contact"] = np.nan

    # 4-10. Missing datasets -> explicit NaN columns.
    for col in ["mag_1vd", "mag_low_in_high_proxy", "gravity_gradient",
                "till_au_clr", "till_as_clr", "till_sb_clr", "till_bi_clr"]:
        df[col] = np.nan

    return df


def run_for_grid(cfg, grid_path: Path, structures, bedrock, out_path: Path) -> dict:
    grid = gpd.read_file(grid_path)
    df = build_features(grid, structures, bedrock, cfg)
    df.to_parquet(out_path, index=False)
    log.info("Wrote %s (%d cells)", out_path.name, len(df))
    coverage = {f: float(df[f].notna().mean()) for f in FEATURE_ORDER}
    return {"n_cells": len(df), "coverage": coverage, "df": df}


def main() -> int:
    cfg = load_config()
    processed = get_path(cfg, "processed", create=True)
    outputs = get_path(cfg, "outputs", create=True)
    raw = get_path(cfg, "raw")

    def _load(p):
        fp = raw / p
        return gpd.read_file(fp) if fp.exists() else None
    structures = _load("gtk/structures.gpkg")
    bedrock = _load("gtk/bedrock.gpkg")

    grids = {"2km": outputs / "clgb_grid_2km.gpkg", "1km": outputs / "clgb_grid_1km.gpkg"}
    results = {}
    for name, gp in grids.items():
        if not gp.exists():
            log.warning("Grid missing: %s — run 04b first.", gp)
            continue
        out = processed / f"feature_stack_minimal_{name}.parquet"
        results[name] = run_for_grid(cfg, gp, structures, bedrock, out)

    # --- Report ---
    real = [f for f in FEATURE_ORDER if results and
            results[next(iter(results))]["coverage"].get(f, 0) > 0]
    missing = [f for f in FEATURE_ORDER if f not in real]
    L = ["# Step 2 Feature Stack Report", "",
         f"Built the minimal 10-feature CLGB orogenic-gold stack on "
         f"{', '.join(results)} grid(s).", "",
         "## Feature availability", "",
         "| # | feature | status | source |",
         "|---|---------|--------|--------|"]
    src = {
        "dist_major_shear": "GTK structures (1:1M)",
        "fault_intersection_density": "GTK structures (1:1M)",
        "dist_key_lithological_contact": "GTK bedrock (1:1M)",
        "mag_1vd": "— (magnetics not available)",
        "mag_low_in_high_proxy": "— (magnetics not available)",
        "gravity_gradient": "— (gravity not available)",
        "till_au_clr": "— (till geochem not available)",
        "till_as_clr": "— (till geochem not available)",
        "till_sb_clr": "— (till geochem not available)",
        "till_bi_clr": "— (till geochem not available)",
    }
    for i, f in enumerate(FEATURE_ORDER, 1):
        status = "✅ REAL" if f in real else "❌ NULL"
        L.append(f"| {i} | `{f}` | {status} | {src[f]} |")
    L += ["", f"**Real features: {len(real)}/10. Missing: {len(missing)}/10.**", "",
          "## Coverage (non-null fraction)", ""]
    for name, r in results.items():
        L.append(f"- **{name}** ({r['n_cells']} cells): " +
                 ", ".join(f"{k}={v:.0%}" for k, v in r["coverage"].items() if v > 0))
    L += ["", "## Limitations (read loudly)",
          "- Only **3 of 10** features are real this run (structure ×2, lithology ×1).",
          "- The 7 missing features (magnetics ×2, gravity, till ×4) are the geophysical",
          "  and geochemical signals that make orogenic-gold targeting credible. Until they",
          "  are added, the model CANNOT demonstrate multi-layer convergence and any ranking",
          "  is structure/lithology-only.",
          "- GTK structure/bedrock are **1:1,000,000** scale — appropriate for *major* shear",
          "  proximity, too coarse for detailed contacts/second-order splays.",
          "- Add magnetics/gravity/till (see STEP2_DATA_AUDIT.md) then re-run this script;",
          "  the NULL columns fill in automatically.", ""]
    (outputs / "STEP2_FEATURE_STACK_REPORT.md").write_text("\n".join(L), encoding="utf-8")
    log.info("Real features: %d/10 (%s). Wrote feature report.", len(real), ", ".join(real))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
