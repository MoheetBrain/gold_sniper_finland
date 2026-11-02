"""
04b — Refine the AOI to the Central Lapland Greenstone Belt (CLGB) + finer grids.

WHY
    The 5 km AOI box includes non-greenstone basement that is low-priority for
    orogenic gold. This script clips the search space to the greenstone-prospective
    corridor and rebuilds finer grids (2 km regional, 1 km detail) inside it, so
    Step 2 modelling is not wasted on irrelevant ground.

CLGB SOURCE (in priority order)
    1. REAL GTK bedrock geology, if `clgb.gtk_bedrock_path` exists: the script
       dissolves polygons whose lithology field matches `clgb.greenstone_keywords`.
    2. FALLBACK manual envelope polygon (`clgb.manual_envelope_3067`): an APPROXIMATE
       geographic swath around the Kittilä–Sirkka–Kiistala–Sodankylä corridor. This
       is NOT geology and is clearly labelled as such. Replace it with GTK data.

    The script does NOT invent geology: with no GTK file it tells you exactly what to
    supply and uses the transparent, config-defined envelope meanwhile.

OUTPUTS
    data/processed/clgb_aoi.gpkg          (the CLGB clip polygon + provenance)
    data/outputs/clgb_grid_2km.gpkg       (2 km grid, cells whose centroid is in CLGB)
    data/outputs/clgb_grid_1km.gpkg       (1 km grid, same rule)

Every grid cell carries: cell_id, area_km2, centroid_x, centroid_y, centroid_lat,
centroid_lon, grid_size_m.
"""
from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
from pyproj import Transformer
from shapely.geometry import Polygon

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (PROJECT_CRS, get_logger, get_path,  # noqa: E402
                     import_script, load_config, resolve_path)

log = get_logger("04b_clgb")
_m01 = import_script("01_make_aoi_grid.py", "m01")
TO_WGS84 = Transformer.from_crs("EPSG:3067", "EPSG:4326", always_xy=True)


def build_clgb_polygon(cfg: dict) -> gpd.GeoDataFrame:
    """Return a single-polygon GeoDataFrame for the CLGB clip, GTK if available."""
    crs = cfg["project"].get("crs", PROJECT_CRS)
    clgb_cfg = cfg["clgb"]
    bedrock_path = resolve_path(clgb_cfg["gtk_bedrock_path"])

    if bedrock_path.exists():
        log.info("Using REAL GTK bedrock geology: %s", bedrock_path)
        bed = gpd.read_file(bedrock_path)
        if bed.crs is None:
            raise ValueError("Bedrock CRS missing; obtain source metadata rather than guessing")
        bed = bed.to_crs(crs)
        field = clgb_cfg.get("greenstone_field") or ""
        kws = [k.lower() for k in clgb_cfg.get("greenstone_keywords", [])]
        if not field or field not in bed.columns:
            log.error("greenstone_field '%s' not in bedrock columns %s",
                      field, list(bed.columns))
            log.error("Set clgb.greenstone_field in config to the lithology column.")
            raise SystemExit(2)
        mask = bed[field].astype(str).str.lower().apply(
            lambda v: any(k in v for k in kws))
        green = bed[mask]
        if green.empty:
            log.error("No greenstone lithologies matched keywords %s in field '%s'.",
                      kws, field)
            raise SystemExit(2)
        poly = green.geometry.union_all()
        source = f"GTK bedrock ({bedrock_path.name}); field={field}"
        log.info("Greenstone polygons matched: %d", len(green))
    else:
        log.warning("=" * 70)
        log.warning("GTK bedrock not found at %s", bedrock_path)
        log.warning("Falling back to the APPROXIMATE manual CLGB envelope (NOT geology).")
        log.warning("To use real geology: place a polygon layer at the path above and set")
        log.warning("clgb.greenstone_field + clgb.greenstone_keywords in config.yaml.")
        log.warning("=" * 70)
        verts = [tuple(v) for v in clgb_cfg["manual_envelope_3067"]]
        poly = Polygon(verts)
        source = "MANUAL approximate envelope (config.clgb.manual_envelope_3067) — NOT geology"

    gdf = gpd.GeoDataFrame(
        {"name": ["CLGB_clip"], "source": [source]},
        geometry=[poly], crs=crs)
    gdf["area_km2"] = gdf.geometry.area / 1e6
    return gdf


def make_grid(cfg: dict, cell_size_m: int) -> gpd.GeoDataFrame:
    """Build a full-AOI grid at cell_size_m, with lat/lon + grid_size_m columns."""
    crs = cfg["project"].get("crs", PROJECT_CRS)
    grid = _m01.build_grid(cfg["aoi"]["bounds"], cell_size_m, crs)
    lon, lat = TO_WGS84.transform(grid["centroid_x"].values, grid["centroid_y"].values)
    grid["centroid_lat"] = lat.round(6)
    grid["centroid_lon"] = lon.round(6)
    grid["grid_size_m"] = cell_size_m
    return grid


def clip_grid_to_clgb(grid: gpd.GeoDataFrame, clgb: gpd.GeoDataFrame,
                      keep_rule: str) -> gpd.GeoDataFrame:
    """Keep cells inside the CLGB polygon (centroid_within or intersects)."""
    poly = clgb.geometry.union_all()
    if keep_rule == "intersects":
        keep = grid.geometry.intersects(poly)
    else:  # centroid_within (default) — clean boundary, no slivers
        cent = gpd.GeoSeries(gpd.points_from_xy(grid["centroid_x"], grid["centroid_y"]),
                             crs=grid.crs)
        keep = cent.within(poly)
    out = grid[keep].copy().reset_index(drop=True)
    return out


def main() -> int:
    cfg = load_config()
    processed = get_path(cfg, "processed", create=True)
    outputs = get_path(cfg, "outputs", create=True)
    keep_rule = cfg["clgb"].get("keep_rule", "centroid_within")

    clgb = build_clgb_polygon(cfg)
    clgb.to_file(processed / "clgb_aoi.gpkg", layer="clgb_aoi", driver="GPKG")
    log.info("Wrote clgb_aoi.gpkg — CLGB area %.0f km² (source: %s)",
             clgb["area_km2"].iloc[0], clgb["source"].iloc[0])

    for size, name in [(int(cfg["grids"]["regional_rank_m"]), "clgb_grid_2km.gpkg"),
                       (int(cfg["grids"]["target_detail_m"]), "clgb_grid_1km.gpkg")]:
        grid = make_grid(cfg, size)
        clipped = clip_grid_to_clgb(grid, clgb, keep_rule)
        # Re-id cells sequentially within the CLGB for cleanliness.
        clipped["cell_id"] = [f"g{size//1000}k_{i:05d}" for i in range(len(clipped))]
        layer = name.replace(".gpkg", "")
        clipped.to_file(outputs / name, layer=layer, driver="GPKG")
        log.info("Wrote %s — %d cells (%.0f km²) at %d m",
                 name, len(clipped), clipped["area_km2"].sum(), size)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
