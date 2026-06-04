"""
01 — Build the Central Lapland AOI grid.

WHAT THIS DOES
    Creates a regular square grid of cells covering the AOI bounding box defined in
    configs/config.yaml, in EPSG:3067 (ETRS89 / TM35FIN). This grid is the unit of
    analysis for the whole project: in Step 1 we mark each cell open/taken; in
    Step 2 each cell gets geology/geophysics/geochemistry features and a score.

OUTPUT
    data/processed/aoi_grid.gpkg   (layer: aoi_grid)
    columns: cell_id, area_km2, centroid_x, centroid_y, geometry

WHY A GRID (not free-form polygons)
    A fixed grid gives every later step a common, reproducible spatial index, makes
    overlap/area maths simple, and maps cleanly onto reservation-sized blocks.

The AOI is intentionally broad (Kittilä/Ikkari -> Sodankylä, across the Sirkka and
Kiistala shear corridors). Tighten configs/config.yaml: aoi.bounds to focus later.
"""
from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import PROJECT_CRS, get_logger, get_path, load_config  # noqa: E402

log = get_logger("01_make_aoi_grid")


def build_grid(bounds: list[float], cell_size_m: float, crs: str) -> gpd.GeoDataFrame:
    """
    Build a square grid covering `bounds` = [xmin, ymin, xmax, ymax] in metres.

    Cells are generated left->right, bottom->top. cell_id is a stable string of the
    form 'r{row}_c{col}' so it is human-readable and reproducible. The final row/col
    may be clipped to the AOI box so edge cells can be smaller than cell_size_m;
    area_km2 reflects the true (possibly clipped) cell area.
    """
    xmin, ymin, xmax, ymax = bounds
    if not (xmax > xmin and ymax > ymin):
        raise ValueError(f"AOI bounds must have xmax>xmin and ymax>ymin, got {bounds}")
    if cell_size_m <= 0:
        raise ValueError(f"cell_size_m must be positive, got {cell_size_m}")

    cells = []
    cell_ids = []
    row = 0
    y = ymin
    while y < ymax:
        col = 0
        x = xmin
        y_top = min(y + cell_size_m, ymax)  # clip top edge to AOI
        while x < xmax:
            x_right = min(x + cell_size_m, xmax)  # clip right edge to AOI
            cells.append(box(x, y, x_right, y_top))
            cell_ids.append(f"r{row}_c{col}")
            col += 1
            x += cell_size_m
        row += 1
        y += cell_size_m

    gdf = gpd.GeoDataFrame({"cell_id": cell_ids}, geometry=cells, crs=crs)

    # Attributes used everywhere downstream.
    gdf["area_km2"] = gdf.geometry.area / 1_000_000.0  # m^2 -> km^2
    centroids = gdf.geometry.centroid
    gdf["centroid_x"] = centroids.x
    gdf["centroid_y"] = centroids.y

    # Tidy column order.
    return gdf[["cell_id", "area_km2", "centroid_x", "centroid_y", "geometry"]]


def main() -> int:
    cfg = load_config()
    crs = cfg["project"].get("crs", PROJECT_CRS)
    bounds = cfg["aoi"]["bounds"]
    cell_size = float(cfg["aoi"]["cell_size_m"])

    log.info("AOI bounds (EPSG:3067): %s", bounds)
    log.info("Cell size: %.0f m (%.1f km)", cell_size, cell_size / 1000.0)

    grid = build_grid(bounds, cell_size, crs)
    log.info("Built grid: %d cells, total area %.1f km^2",
             len(grid), grid["area_km2"].sum())

    processed_dir = get_path(cfg, "processed", create=True)
    out_path = processed_dir / "aoi_grid.gpkg"
    grid.to_file(out_path, layer="aoi_grid", driver="GPKG")
    log.info("Wrote %s (layer: aoi_grid)", out_path)

    # Sanity: confirm CRS round-trips.
    check = gpd.read_file(out_path, layer="aoi_grid")
    assert str(check.crs).upper().endswith("3067"), f"CRS mismatch: {check.crs}"
    log.info("Verified output CRS = %s", check.crs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
