"""
04 — Cluster clean-open cells into open-ground blocks.

WHY THIS MATTERS
    One isolated open 5 km cell surrounded by taken ground is commercially weak.
    A contiguous block of clean-open cells is far more interesting (room for a
    coherent target / reservation). This groups edge-adjacent clean-open cells into
    clusters and measures each one.

METHOD
    Take clean-open cells (is_clean_open == True), union them, and explode into
    connected components. Cells touching only at a corner are NOT merged (we want
    edge-connectivity), so each cluster is a genuinely contiguous block.

OUTPUTS
    data/outputs/clean_open_clusters.gpkg   (layer: clean_open_clusters)
    data/outputs/clean_open_clusters.csv

    Per cluster: cluster_id, n_cells, area_km2, centroid_x/y, bbox, compactness
    (area / bbox-area; 1.0 = solid rectangle), and distance to the nearest Tukes right.

By default it clusters the CONSERVATIVE clean-open set (the cautious view). Point it
at a different cell file via --cells if you want the strict-active view.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import get_logger, get_path, load_config  # noqa: E402

log = get_logger("04_cluster")


def load_clean_open(outputs_dir: Path, cells_file: str) -> gpd.GeoDataFrame:
    """Load a cell GeoPackage and keep only clean-open cells."""
    path = outputs_dir / cells_file
    if not path.exists():
        raise FileNotFoundError(f"{path} not found — run 02 / 02c first.")
    layer = path.stem
    gdf = gpd.read_file(path, layer=layer)
    if "is_clean_open" in gdf.columns:
        gdf = gdf[gdf["is_clean_open"].astype(bool)].copy()
    return gdf


def cluster_cells(clean: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Union clean-open cells and explode into edge-connected clusters."""
    if clean.empty:
        return gpd.GeoDataFrame(
            {"cluster_id": []}, geometry=[], crs=clean.crs)
    union = clean.geometry.union_all()
    parts = gpd.GeoSeries([union], crs=clean.crs).explode(index_parts=False).reset_index(drop=True)
    clusters = gpd.GeoDataFrame(geometry=parts, crs=clean.crs)
    clusters["cluster_id"] = [f"clu_{i:04d}" for i in range(len(clusters))]
    return clusters


def attribute_clusters(clusters: gpd.GeoDataFrame, clean: gpd.GeoDataFrame,
                       rights: gpd.GeoDataFrame | None) -> gpd.GeoDataFrame:
    """Compute per-cluster stats + distance to nearest Tukes right."""
    # Count clean cells per cluster via point-in-polygon on cell centroids.
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
    bounds = clusters.geometry.bounds
    clusters["bbox_xmin"] = bounds["minx"].round(1)
    clusters["bbox_ymin"] = bounds["miny"].round(1)
    clusters["bbox_xmax"] = bounds["maxx"].round(1)
    clusters["bbox_ymax"] = bounds["maxy"].round(1)
    bbox_area = ((bounds["maxx"] - bounds["minx"]) * (bounds["maxy"] - bounds["miny"]))
    clusters["compactness"] = (clusters.geometry.area / bbox_area).round(3)
    # A multi-cell block that fills its bbox is contiguous & solid; low compactness = ragged.
    clusters["shape_note"] = clusters["compactness"].apply(
        lambda c: "solid" if c >= 0.95 else ("blocky" if c >= 0.6 else "ragged"))

    # Distance from each cluster to the nearest Tukes right polygon.
    if rights is not None and not rights.empty:
        nearest = gpd.sjoin_nearest(
            clusters[["cluster_id", "geometry"]], rights[["geometry"]],
            how="left", distance_col="dist_to_right_m")
        # sjoin_nearest can return duplicates; keep the min per cluster.
        dist = nearest.groupby("cluster_id")["dist_to_right_m"].min()
        clusters["dist_to_nearest_right_m"] = clusters["cluster_id"].map(dist).round(1)
    else:
        clusters["dist_to_nearest_right_m"] = None

    return clusters.sort_values(["n_cells", "area_km2"], ascending=False).reset_index(drop=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cells", default="open_cells_conservative.gpkg",
                    help="cell GeoPackage in data/outputs/ to cluster (clean-open subset)")
    args = ap.parse_args()

    cfg = load_config()
    outputs = get_path(cfg, "outputs", create=True)
    processed = get_path(cfg, "processed")

    # Fall back to the original open_cells.gpkg if the conservative one isn't there yet.
    cells_file = args.cells
    if not (outputs / cells_file).exists():
        log.warning("%s not found; falling back to open_cells.gpkg", cells_file)
        cells_file = "open_cells.gpkg"

    clean = load_clean_open(outputs, cells_file)
    log.info("Clustering %d clean-open cells from %s", len(clean), cells_file)

    rights_path = processed / "tukes_all_rights.gpkg"
    rights = gpd.read_file(rights_path) if rights_path.exists() else None

    clusters = cluster_cells(clean)
    if not clusters.empty:
        clusters = attribute_clusters(clusters, clean, rights)

    gpkg = outputs / "clean_open_clusters.gpkg"
    clusters.to_file(gpkg, layer="clean_open_clusters", driver="GPKG")
    csv = outputs / "clean_open_clusters.csv"
    (clusters.drop(columns="geometry") if not clusters.empty else clusters).to_csv(csv, index=False)
    log.info("Wrote %s (%d clusters) and %s", gpkg.name, len(clusters), csv.name)

    if not clusters.empty:
        top = clusters.head(5)[["cluster_id", "n_cells", "area_km2",
                                "dist_to_nearest_right_m", "shape_note"]]
        log.info("Largest clusters:\n%s", top.to_string(index=False))
        log.info("Total clusters=%d | single-cell clusters=%d | largest=%.0f km² (%d cells)",
                 len(clusters), int((clusters["n_cells"] == 1).sum()),
                 clusters["area_km2"].max(), int(clusters["n_cells"].max()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
