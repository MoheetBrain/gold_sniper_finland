"""
04 — Cluster clean-open cells into open-ground blocks (grid- and mask-parameterised).

WHY THIS MATTERS
    One isolated open cell is commercially weak; a contiguous block of clean-open
    cells is interesting. This groups edge-adjacent clean-open cells into clusters
    and measures each one, so Step 1.5 can rank coherent open ground.

    NOTE: clusters are *legal/geographic candidate clusters* (open-ground blocks),
    NOT gold targets. Gold targets only exist after Step 2 feature convergence.

MASK MODES (which rights count as "taken")
    conservative   : exclude ALL Tukes rights (active+pending+cooling-off)  [= Scenario A]
    strict_active  : exclude ONLY active (voimassa) rights
    scenario_b     : exclude everything EXCEPT gold-panning (placer reported separately)

USAGE
    # default — reproduces the 5 km conservative clusters used by the pipeline:
    python scripts/04_cluster_open_cells.py
    # finer grid + a chosen mask, with restriction overlap:
    python scripts/04_cluster_open_cells.py \
        --grid data/outputs/clgb_grid_2km.gpkg --mode strict_active --tag 2km_strict \
        --restrictions data/processed/restriction_masks.gpkg

OUTPUT
    data/outputs/clean_open_clusters[_<tag>].gpkg / .csv
    Per cluster: cluster_id, n_cells, area_km2, centroid_x/y, centroid_lat/lon, bbox,
    compactness, dist_to_nearest_active_right_m, dist_to_nearest_pending_right_m,
    restriction_overlap_pct, mode, grid_size_m.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import geopandas as gpd
from pyproj import Transformer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import get_logger, get_path, import_script, load_config  # noqa: E402

log = get_logger("04_cluster")
_m02 = import_script("02_mask_taken_areas.py", "m02")
_m02c = import_script("02c_classify_tukes_status.py", "m02c")
TO_WGS84 = Transformer.from_crs("EPSG:3067", "EPSG:4326", always_xy=True)


def select_rights(rights: gpd.GeoDataFrame, mode: str, panning_stem: str) -> gpd.GeoDataFrame:
    """Subset the classified rights according to the mask mode."""
    stem = rights["source_layer"].str.split("_").str[0]
    if mode == "conservative":
        return rights
    if mode == "strict_active":
        return rights[rights["legal_class"] == "active"]
    if mode == "scenario_b":
        return rights[stem != panning_stem]
    raise ValueError(f"unknown mode {mode}")


def cluster_cells(clean: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Union clean-open cells and explode into edge-connected clusters."""
    if clean.empty:
        return gpd.GeoDataFrame({"cluster_id": []}, geometry=[], crs=clean.crs)
    union = clean.geometry.union_all()
    parts = gpd.GeoSeries([union], crs=clean.crs).explode(index_parts=False).reset_index(drop=True)
    clusters = gpd.GeoDataFrame(geometry=parts, crs=clean.crs)
    clusters["cluster_id"] = [f"clu_{i:04d}" for i in range(len(clusters))]
    return clusters


def _nearest_dist(clusters, sub):
    """Min distance from each cluster to the nearest polygon in sub (by cluster_id)."""
    if sub is None or sub.empty or clusters.empty:
        return {cid: None for cid in clusters["cluster_id"]}
    nn = gpd.sjoin_nearest(clusters[["cluster_id", "geometry"]],
                          sub[["geometry"]].copy(), how="left", distance_col="d")
    return nn.groupby("cluster_id")["d"].min().round(1).to_dict()


def attribute_clusters(clusters, clean, rights, restrictions, mode, grid_size_m):
    if clusters.empty:
        return clusters
    cell_pts = clean.copy()
    cell_pts["geometry"] = cell_pts.geometry.centroid
    joined = gpd.sjoin(cell_pts, clusters, predicate="within", how="left")
    n_cells = joined.groupby("cluster_id").size()

    clusters = clusters.copy()
    clusters["n_cells"] = clusters["cluster_id"].map(n_cells).fillna(0).astype(int)
    clusters["area_km2"] = (clusters.geometry.area / 1e6).round(3)
    cent = clusters.geometry.centroid
    clusters["centroid_x"] = cent.x.round(1)
    clusters["centroid_y"] = cent.y.round(1)
    lon, lat = TO_WGS84.transform(cent.x.values, cent.y.values)
    clusters["centroid_lat"] = lat.round(6)
    clusters["centroid_lon"] = lon.round(6)
    b = clusters.geometry.bounds
    clusters["bbox_xmin"], clusters["bbox_ymin"] = b["minx"].round(1), b["miny"].round(1)
    clusters["bbox_xmax"], clusters["bbox_ymax"] = b["maxx"].round(1), b["maxy"].round(1)
    bbox_area = (b["maxx"] - b["minx"]) * (b["maxy"] - b["miny"])
    clusters["compactness"] = (clusters.geometry.area / bbox_area).round(3)

    active = rights[rights["legal_class"] == "active"]
    pending = rights[rights["legal_class"] == "pending"]
    da = _nearest_dist(clusters, active)
    dp = _nearest_dist(clusters, pending)
    clusters["dist_to_nearest_active_right_m"] = clusters["cluster_id"].map(da)
    clusters["dist_to_nearest_pending_right_m"] = clusters["cluster_id"].map(dp)

    # Restriction overlap %.
    if restrictions is not None and not restrictions.empty:
        rpoly = restrictions.geometry.union_all()
        clusters["restriction_overlap_pct"] = clusters.geometry.apply(
            lambda g: round(g.intersection(rpoly).area / g.area * 100, 3) if g.area else 0.0)
    else:
        clusters["restriction_overlap_pct"] = 0.0

    clusters["mode"] = mode
    clusters["grid_size_m"] = grid_size_m
    return clusters.sort_values(["n_cells", "area_km2"], ascending=False).reset_index(drop=True)


def run_clustering(cfg, grid_path, mode, restrictions_path=None):
    """Compute clean-open clusters for one grid + mask mode. Returns GeoDataFrame."""
    grid = gpd.read_file(grid_path)
    grid_size_m = int(grid["grid_size_m"].iloc[0]) if "grid_size_m" in grid.columns else 0
    rights = _m02c.load_classified_rights(cfg)
    panning_stem = cfg["gold_panning"]["layer_stem"]
    rights_subset = select_rights(rights, mode, panning_stem)

    status = _m02.compute_cell_status(grid, rights_subset, cfg)
    clean = status[status["is_clean_open"]].copy()
    log.info("[%s | %s] %d clean-open cells of %d",
             Path(grid_path).stem, mode, len(clean), len(grid))

    restrictions = None
    if restrictions_path and Path(restrictions_path).exists():
        try:
            restrictions = gpd.read_file(restrictions_path)
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not read restrictions %s: %s", restrictions_path, exc)

    clusters = cluster_cells(clean)
    clusters = attribute_clusters(clusters, clean, rights, restrictions, mode, grid_size_m)
    return clusters


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid", default=None, help="grid GeoPackage (default 5km aoi_grid)")
    ap.add_argument("--mode", default="conservative",
                    choices=["conservative", "strict_active", "scenario_b"])
    ap.add_argument("--tag", default=None, help="output suffix (default: derived/none)")
    ap.add_argument("--restrictions", default=None, help="restriction mask gpkg (optional)")
    args = ap.parse_args()

    cfg = load_config()
    processed = get_path(cfg, "processed")
    outputs = get_path(cfg, "outputs", create=True)
    grid_path = Path(args.grid) if args.grid else (processed / "aoi_grid.gpkg")
    if not grid_path.exists():
        log.error("Grid not found: %s", grid_path)
        return 2

    clusters = run_clustering(cfg, grid_path, args.mode, args.restrictions)

    suffix = f"_{args.tag}" if args.tag else ""
    gpkg = outputs / f"clean_open_clusters{suffix}.gpkg"
    csv = outputs / f"clean_open_clusters{suffix}.csv"
    layer = f"clean_open_clusters{suffix}"
    clusters.to_file(gpkg, layer=layer, driver="GPKG")
    (clusters.drop(columns="geometry") if not clusters.empty else clusters).to_csv(csv, index=False)
    log.info("Wrote %s (%d clusters) and %s", gpkg.name, len(clusters), csv.name)
    if not clusters.empty:
        cols = ["cluster_id", "n_cells", "area_km2", "dist_to_nearest_active_right_m",
                "restriction_overlap_pct"]
        log.info("Largest:\n%s", clusters.head(5)[cols].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
