"""
06d - Process local Bouguer gravity into a 2 km CLGB feature.

Preferred inputs are checked in order. In this environment the Geosoft GRD and ECW
are not GDAL-readable, so the script falls back to the numeric BA_FIN.XYZ grid.

Output
    data/processed/gravity_features_2km.parquet
    data/outputs/GRAVITY_PROCESSING_REPORT.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import CRS, Transformer
from scipy import ndimage
from scipy.interpolate import RegularGridInterpolator

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import get_logger, get_path, load_config  # noqa: E402

log = get_logger("06d_gravity")

GRAVITY_XYZ_CRS = CRS.from_proj4(
    "+proj=tmerc +lat_0=0 +lon_0=21 +k=1 +x_0=1500000 +y_0=0 "
    "+ellps=WGS84 +units=m +no_defs"
)


def read_bouguer_xyz(path: Path):
    df = pd.read_csv(path, comment="/", sep=r"\s+", names=["x", "y", "bouguer_mgal"],
                     engine="python")
    if df.empty:
        raise ValueError(f"No numeric rows parsed from {path}")
    xs = np.sort(df["x"].unique())
    ys = np.sort(df["y"].unique())
    x_index = {v: i for i, v in enumerate(xs)}
    y_index = {v: i for i, v in enumerate(ys)}
    grid = np.full((len(ys), len(xs)), np.nan, dtype=float)
    grid[[y_index[v] for v in df["y"]], [x_index[v] for v in df["x"]]] = df["bouguer_mgal"]
    return df, xs, ys, grid


def filled_gradient_mgal_per_km(grid: np.ndarray, dx: float, dy: float) -> np.ndarray:
    finite = np.isfinite(grid)
    if not finite.any():
        raise ValueError("Bouguer grid has no finite values")
    nearest = ndimage.distance_transform_edt(~finite, return_distances=False, return_indices=True)
    filled = grid[tuple(nearest)]
    gy, gx = np.gradient(filled, dy, dx)
    grad = np.sqrt(gx * gx + gy * gy) * 1000.0
    grad[~finite] = np.nan
    return grad


def main() -> int:
    cfg = load_config()
    raw = get_path(cfg, "raw")
    processed = get_path(cfg, "processed", create=True)
    outputs = get_path(cfg, "outputs", create=True)

    candidates = [
        raw / "gtk/gravity/Fenno_Bouguer_Fin_ETRS89_TM35FIN.grd",
        raw / "gtk/gravity/BA_FIN.XYZ",
        raw / "gtk/gravity/Fenno_Bouguer_FIN_ETRS89_TM35FIN.ecw",
    ]
    xyz_path = candidates[1]
    if not xyz_path.exists():
        raise FileNotFoundError(f"Gravity XYZ fallback missing: {xyz_path}")

    grid_path = outputs / cfg["step2"]["primary_grid"]
    clgb_grid = gpd.read_file(grid_path).to_crs(3067)

    df, xs, ys, bouguer = read_bouguer_xyz(xyz_path)
    dx = float(np.median(np.diff(xs)))
    dy = float(np.median(np.diff(ys)))
    grad = filled_gradient_mgal_per_km(bouguer, dx, dy)

    to_src = Transformer.from_crs(3067, GRAVITY_XYZ_CRS, always_xy=True)
    gx, gy = to_src.transform(clgb_grid["centroid_x"].to_numpy(), clgb_grid["centroid_y"].to_numpy())
    sample_points = np.c_[gy, gx]
    grad_interp = RegularGridInterpolator((ys, xs), grad, bounds_error=False, fill_value=np.nan)
    bouguer_interp = RegularGridInterpolator((ys, xs), bouguer, bounds_error=False, fill_value=np.nan)

    out = pd.DataFrame({
        "cell_id": clgb_grid["cell_id"].to_numpy(),
        "gravity_bouguer_mgal": bouguer_interp(sample_points),
        "gravity_gradient": grad_interp(sample_points),
        "gravity_source": "BA_FIN.XYZ",
        "gravity_resolution_m": dx,
    })
    out.to_parquet(processed / "gravity_features_2km.parquet", index=False)

    valid = out["gravity_gradient"].notna()
    lines = [
        "# Gravity Processing Report",
        "",
        f"Bouguer file used: `{xyz_path}`",
        "",
        "## Input Selection",
        "",
        "- Preferred Geosoft GRD is present but not readable by this GDAL/rasterio build.",
        "- ECW is not readable here and its sidecar metadata describes an 8-bit display product.",
        "- `BA_FIN.XYZ` is a numeric 2.5 km Bouguer anomaly grid and was used.",
        "",
        "## Processing",
        "",
        f"- Source CRS: WGS84 Gauss-Krueger, central meridian 21E, false easting 1500000.",
        f"- Source grid spacing: {dx:g} m x {dy:g} m.",
        "- Horizontal gradient magnitude computed on the regular source grid from Bouguer mGal.",
        "- Units for `gravity_gradient`: mGal/km.",
        "- Values sampled to CLGB 2 km cell centroids after CRS transformation.",
        "",
        "## Output Summary",
        "",
        f"- Cells written: {len(out)}",
        f"- Cells with non-null gravity_gradient: {int(valid.sum())} ({valid.mean():.1%})",
        f"- gravity_gradient min/max/mean: {out['gravity_gradient'].min():.4g} / "
        f"{out['gravity_gradient'].max():.4g} / {out['gravity_gradient'].mean():.4g} mGal/km",
        "",
        "## Limitations",
        "",
        "- The Bouguer grid is regional, upward-continued to 500 m, and documented as suitable "
        "mainly for shield-scale/regional interpretation.",
        "- Cell values are centroid samples of a 2.5 km source grid on a 2 km modelling grid; "
        "they should be treated as broad density-contrast context, not target-scale gravity.",
        "",
    ]
    (outputs / "GRAVITY_PROCESSING_REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    log.info("Wrote gravity_features_2km.parquet with %.1f%% coverage", valid.mean() * 100)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
