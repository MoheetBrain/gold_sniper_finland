"""
09 — Assign spatial blocks for spatially grouped cross-validation.

WHY
    Random train/test splits leak spatial autocorrelation: a test cell 2 km from a
    training positive looks "predicted" only because gold clusters spatially. We use
    20 km x 20 km blocks; whole blocks go to train or test, never split. This is the
    ONLY validation we trust for top-k capture.

OUTPUTS
    data/processed/cell_block_<grid>.parquet     (cell_id, spatial_block_id, bx, by)
    data/processed/spatial_blocks_<grid>.gpkg     (block polygons, for QGIS)
    data/outputs/STEP2_SPATIAL_BLOCKS_REPORT.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import numpy as np
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import get_logger, get_path, load_config  # noqa: E402

log = get_logger("09_blocks")


def assign_blocks(grid: gpd.GeoDataFrame, block_m: float):
    """Add bx, by, spatial_block_id from centroid coords on a 20 km lattice."""
    if not np.isfinite(block_m) or block_m <= 0:
        raise ValueError("block_m must be finite and positive")
    grid = grid.copy()
    bx = (grid["centroid_x"] // block_m).astype(int)
    by = (grid["centroid_y"] // block_m).astype(int)
    grid["bx"] = bx
    grid["by"] = by
    grid["spatial_block_id"] = bx.astype(str) + "_" + by.astype(str)
    return grid


def main() -> int:
    cfg = load_config()
    processed = get_path(cfg, "processed")
    outputs = get_path(cfg, "outputs")
    block_m = float(cfg["spatial_blocks"]["block_size_m"])

    report = {}
    for gname in ["clgb_grid_2km", "clgb_grid_1km"]:
        gp = outputs / f"{gname}.gpkg"
        if not gp.exists():
            continue
        grid = assign_blocks(gpd.read_file(gp), block_m)
        size = gname.split("_")[-1]
        grid[["cell_id", "spatial_block_id", "bx", "by"]].to_parquet(
            processed / f"cell_block_{size}.parquet", index=False)

        # Block polygons for QGIS.
        polys, ids = [], []
        for (bx, by), _ in grid.groupby(["bx", "by"]):
            polys.append(box(bx * block_m, by * block_m, (bx + 1) * block_m, (by + 1) * block_m))
            ids.append(f"{bx}_{by}")
        blocks = gpd.GeoDataFrame({"spatial_block_id": ids}, geometry=polys, crs=grid.crs)
        blocks.to_file(processed / f"spatial_blocks_{size}.gpkg",
                       layer=f"spatial_blocks_{size}", driver="GPKG")

        # Positives per block (leakage check).
        n_blocks = grid["spatial_block_id"].nunique()
        pos_blocks = None
        lp = processed / f"cell_labels_{size}.parquet"
        if lp.exists():
            labs = pd.read_parquet(lp)
            m = grid.merge(labs, on="cell_id", how="left")
            pos_blocks = m[m["is_positive"] == True]["spatial_block_id"].nunique()  # noqa: E712
        report[gname] = {"n_cells": len(grid), "n_blocks": n_blocks,
                         "blocks_with_positive": pos_blocks}
        log.info("%s: %d cells, %d blocks (%s with a positive)",
                 gname, len(grid), n_blocks, pos_blocks)

    L = ["# Step 2 Spatial Blocks Report", "",
         f"Block size: **{block_m/1000:.0f} km × {block_m/1000:.0f} km**. Whole blocks go to",
         "train or test — never split — for leave-one-block-out / blocked k-fold CV.", "",
         "| grid | cells | blocks | blocks containing a positive |",
         "|------|-------|--------|------------------------------|"]
    for g, r in report.items():
        L.append(f"| {g} | {r['n_cells']} | {r['n_blocks']} | {r['blocks_with_positive']} |")
    L += ["", "## Leakage risks (read loudly)",
          "- Positives sit in only a handful of blocks, so blocked CV has very few positive",
          "  test folds — metrics are high-variance. Report ranges, not point estimates.",
          "- Do NOT use random k-fold here: adjacent cells would leak between train/test.",
          "- The 20 km block size is a starting choice; sensitivity to block size should be",
          "  checked once more positives/features exist.", ""]
    (outputs / "STEP2_SPATIAL_BLOCKS_REPORT.md").write_text("\n".join(L), encoding="utf-8")
    log.info("Wrote STEP2_SPATIAL_BLOCKS_REPORT.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
