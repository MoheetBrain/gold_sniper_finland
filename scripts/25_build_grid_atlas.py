"""
25 - Build a numbered CLGB 2 km grid atlas.

This is an orientation product only. It does not change model outputs, does not
promote review candidates, and does not create target memos.

Outputs
    data/outputs/clgb_grid_2km_numbered.gpkg
    data/outputs/clgb_grid_2km_number_lookup.csv
    data/outputs/clgb_grid_2km_numbered_overview.png
    data/outputs/clgb_grid_2km_numbered_atlas.pdf
    data/outputs/clgb_grid_2km_numbered.qgz
    data/outputs/clgb_settlement_labels.gpkg
    data/outputs/GRID_ATLAS_REPORT.md
"""
from __future__ import annotations

import json
import math
import sys
import time
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages
from pyproj import Transformer
from scipy.spatial import cKDTree
from shapely.geometry import Point, box

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import get_logger, get_path, load_config  # noqa: E402

log = get_logger("25_grid_atlas")

PROJECT_CRS = "EPSG:3067"
WGS84 = "EPSG:4326"
PLACE_BUFFER_M = 20000
ATLAS_TILE_M = 36000

STATUS_COLORS = {
    "restricted_area": "#e8a1a1",
    "legally_blocked": "#b9bec7",
    "insufficient_data": "#f4f1e8",
    "structure_only_candidate": "#f2c14e",
    "structure_gravity_review_candidate": "#4c78a8",
    "multi_layer_review_candidate": "#4c78a8",
}
STATUS_EDGES = {
    "restricted_area": "#9b2f2f",
    "legally_blocked": "#626975",
    "insufficient_data": "#d5cfbf",
    "structure_only_candidate": "#9a6b00",
    "structure_gravity_review_candidate": "#0f3d6e",
    "multi_layer_review_candidate": "#0f3d6e",
}
PLACE_RANK = {
    "city": 0,
    "town": 1,
    "village": 2,
    "hamlet": 3,
    "locality": 4,
}

# Fallback labels are used only if Overpass is unavailable. Coordinates are WGS84.
FALLBACK_PLACES = [
    ("Kittila", 67.6555, 24.9088, "town"),
    ("Sodankyla", 67.4167, 26.6000, "town"),
    ("Sirkka", 67.8050, 24.8250, "village"),
    ("Levi", 67.8060, 24.8020, "locality"),
    ("Kiistala", 67.5530, 25.4190, "village"),
    ("Kaukonen", 67.5410, 24.6450, "village"),
    ("Kaukinen", 67.6090, 24.7610, "village"),
    ("Kongas", 67.8270, 25.1040, "village"),
    ("Tepasto", 67.9770, 25.2660, "village"),
    ("Raattama", 68.0930, 24.1580, "village"),
    ("Muonio", 67.9550, 23.6820, "town"),
    ("Kolari", 67.3300, 23.7770, "town"),
    ("Pokka", 68.1670, 25.8000, "village"),
    ("Sattanen", 67.4550, 26.9000, "village"),
    ("Kelujarvi", 67.4770, 27.0980, "village"),
    ("Kersilo", 67.2930, 26.7400, "village"),
    ("Jeesio", 67.6880, 26.7060, "village"),
    ("Unari", 67.1470, 26.1130, "village"),
]


def assign_map_numbers(grid: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Assign row-major map numbers from northwest to southeast."""
    out = grid.copy()
    # Round to avoid tiny floating noise in row sorting.
    out["_row_y"] = out["centroid_y"].round(3)
    out = out.sort_values(["_row_y", "centroid_x"], ascending=[False, True]).reset_index(drop=True)
    out["map_number"] = np.arange(1, len(out) + 1, dtype=int)
    out = out.drop(columns="_row_y")
    return out


def load_candidate_context(outputs: Path) -> pd.DataFrame:
    cand_path = outputs / "geology_ranked_modelling_candidates.gpkg"
    if not cand_path.exists():
        return pd.DataFrame(columns=["cell_id"])
    cand = gpd.read_file(cand_path).drop(columns="geometry", errors="ignore")
    keep = [
        "cell_id",
        "cluster_id",
        "legal_status_conservative",
        "restriction_status",
        "final_status",
        "model_score",
        "baseline_score",
        "model_minus_baseline",
    ]
    keep = [c for c in keep if c in cand.columns]
    context = cand[keep].copy()
    context = context.rename(columns={
        "legal_status_conservative": "legal_status",
        "final_status": "base_candidate_status",
    })

    audit_path = outputs / "review_candidates_audited.csv"
    if audit_path.exists():
        audit = pd.read_csv(audit_path)
        audit_keep = ["cell_id", "audit_status", "multi_layer_convergence"]
        audit_keep = [c for c in audit_keep if c in audit.columns]
        context = context.merge(audit[audit_keep], on="cell_id", how="left")
    else:
        context["audit_status"] = np.nan
        context["multi_layer_convergence"] = False

    def candidate_status(row):
        base = row.get("base_candidate_status", "insufficient_data")
        audit = row.get("audit_status")
        if base == "model_supported_review_candidate":
            if audit == "multi_layer_review_candidate":
                return "structure_gravity_review_candidate"
            if audit == "structure_only_candidate":
                return "structure_only_candidate"
            if isinstance(audit, str) and audit:
                return audit
            return "insufficient_data"
        return base

    context["candidate_status"] = context.apply(candidate_status, axis=1)
    return context


def aoi_bbox_wgs84(aoi_geom_3067):
    to_wgs = Transformer.from_crs(PROJECT_CRS, WGS84, always_xy=True)
    minx, miny, maxx, maxy = aoi_geom_3067.bounds
    xs, ys = to_wgs.transform([minx, maxx], [miny, maxy])
    west, east = min(xs), max(xs)
    south, north = min(ys), max(ys)
    return south, west, north, east


def fetch_overpass_places(aoi_buffer_geom, outputs: Path) -> tuple[gpd.GeoDataFrame | None, str]:
    cache_path = outputs / "osm_settlements_clgb_overpass.json"
    south, west, north, east = aoi_bbox_wgs84(aoi_buffer_geom)
    node_query = f"""
    [out:json][timeout:45];
    node["place"~"^(city|town|village|hamlet|locality)$"]({south},{west},{north},{east});
    out tags qt;
    """
    full_query = f"""
    [out:json][timeout:75];
    (
      node["place"~"^(city|town|village|hamlet|locality)$"]({south},{west},{north},{east});
      way["place"~"^(city|town|village|hamlet|locality)$"]({south},{west},{north},{east});
      relation["place"~"^(city|town|village|hamlet|locality)$"]({south},{west},{north},{east});
    );
    out center tags;
    """
    data = None
    source = ""
    if cache_path.exists():
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            source = f"OpenStreetMap Overpass cache ({cache_path.name})"
        except Exception:  # noqa: BLE001
            data = None
    if data is None:
        try:
            import requests

            endpoints = [
                "https://overpass-api.de/api/interpreter",
                "https://overpass.kumi.systems/api/interpreter",
            ]
            last_error = ""
            for query_label, query in [
                ("settlement nodes", node_query),
                ("settlement nodes/areas", full_query),
            ]:
                for url in endpoints:
                    try:
                        resp = requests.post(url, data={"data": query}, timeout=90)
                        if resp.status_code == 200:
                            candidate = resp.json()
                            if candidate.get("elements"):
                                data = candidate
                                cache_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
                                source = f"OpenStreetMap Overpass API, {query_label} ({url})"
                                break
                            last_error = f"{url}: HTTP 200 but no settlement elements"
                        else:
                            last_error = f"{url}: HTTP {resp.status_code}"
                    except Exception as exc:  # noqa: BLE001
                        last_error = f"{url}: {type(exc).__name__}: {exc}"
                    time.sleep(1)
                if data is not None:
                    break
            if data is None:
                log.warning("Overpass settlement fetch failed: %s", last_error)
        except Exception as exc:  # noqa: BLE001
            log.warning("requests/Overpass unavailable: %s: %s", type(exc).__name__, exc)

    if data is None:
        return None, "fallback"

    rows = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name") or tags.get("name:fi") or tags.get("name:en")
        place = tags.get("place")
        if not name or place not in PLACE_RANK:
            continue
        lon = el.get("lon")
        lat = el.get("lat")
        if lon is None or lat is None:
            center = el.get("center") or {}
            lon = center.get("lon")
            lat = center.get("lat")
        if lon is None or lat is None:
            continue
        rows.append({
            "name": name,
            "place": place,
            "population": tags.get("population"),
            "source": "OpenStreetMap",
            "geometry": Point(float(lon), float(lat)),
        })
    if not rows:
        return None, "fallback"
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs=WGS84).to_crs(PROJECT_CRS)
    return gdf, source or "OpenStreetMap Overpass API"


def fallback_places() -> gpd.GeoDataFrame:
    rows = [
        {"name": name, "place": place, "population": None, "source": "fallback curated settlement list",
         "geometry": Point(lon, lat)}
        for name, lat, lon, place in FALLBACK_PLACES
    ]
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=WGS84).to_crs(PROJECT_CRS)


def dedupe_places(places: gpd.GeoDataFrame, aoi_buffer_geom) -> gpd.GeoDataFrame:
    if places.empty:
        return places
    places = places[places.geometry.within(aoi_buffer_geom)].copy()
    if places.empty:
        return places
    places["place_rank"] = places["place"].map(PLACE_RANK).fillna(99).astype(int)
    places["name_key"] = places["name"].astype(str).str.casefold()
    places = places.sort_values(["name_key", "place_rank"]).drop_duplicates("name_key", keep="first")
    places = places.sort_values(["place_rank", "name"]).reset_index(drop=True)
    places["settlement_id"] = np.arange(1, len(places) + 1, dtype=int)
    return places.drop(columns=["name_key"])


def assign_nearest_places(grid: gpd.GeoDataFrame, places: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    out = grid.copy()
    if places.empty:
        out["nearest_town"] = ""
        out["distance_to_nearest_town_km"] = np.nan
        return out
    tree = cKDTree(np.c_[places.geometry.x, places.geometry.y])
    dist, idx = tree.query(np.c_[out["centroid_x"], out["centroid_y"]], k=1)
    out["nearest_town"] = places.iloc[idx]["name"].to_numpy()
    out["distance_to_nearest_town_km"] = (dist / 1000.0).round(2)
    return out


def plot_grid(ax, grid: gpd.GeoDataFrame, *, label_numbers: bool, label_size: float = 5.0):
    for status, part in grid.groupby("candidate_status", dropna=False):
        status = status if isinstance(status, str) else "insufficient_data"
        color = STATUS_COLORS.get(status, "#f4f1e8")
        edge = STATUS_EDGES.get(status, "#d5cfbf")
        part.plot(ax=ax, color=color, edgecolor=edge, linewidth=0.25)
    if label_numbers:
        for row in grid.itertuples():
            ax.text(row.centroid_x, row.centroid_y, str(row.map_number),
                    ha="center", va="center", fontsize=label_size, color="#202020")


def plot_places(ax, places: gpd.GeoDataFrame, extent_geom, *, label_size: float = 7.0):
    if places.empty:
        return
    subset = places[places.geometry.within(extent_geom)].copy()
    if subset.empty:
        return
    subset.plot(ax=ax, color="#111111", markersize=8, zorder=5)
    for row in subset.itertuples():
        ax.text(row.geometry.x + 450, row.geometry.y + 450, row.name,
                fontsize=label_size, color="#111111", zorder=6,
                bbox={"facecolor": "white", "alpha": 0.65, "edgecolor": "none", "pad": 0.8})


def add_legend(ax):
    import matplotlib.patches as mpatches

    labels = [
        ("restricted_area", "restricted_area"),
        ("legally_blocked", "legally_blocked"),
        ("insufficient_data", "insufficient_data"),
        ("structure_only_candidate", "structure_only_candidate"),
        ("structure_gravity_review_candidate", "structure_gravity_review_candidate"),
    ]
    patches = [
        mpatches.Patch(facecolor=STATUS_COLORS[k], edgecolor=STATUS_EDGES[k], label=v)
        for k, v in labels
    ]
    ax.legend(handles=patches, loc="lower left", fontsize=8, frameon=True)


def make_overview(grid: gpd.GeoDataFrame, places: gpd.GeoDataFrame, out_path: Path):
    fig, ax = plt.subplots(figsize=(13, 11))
    plot_grid(ax, grid, label_numbers=False)
    review = grid[grid["candidate_status"].isin(["structure_only_candidate", "structure_gravity_review_candidate"])]
    if not review.empty:
        review_centroids = gpd.GeoDataFrame(
            review[["map_number", "candidate_status"]].copy(),
            geometry=gpd.points_from_xy(review["centroid_x"], review["centroid_y"]),
            crs=grid.crs,
        )
        for status, marker, color in [
            ("structure_gravity_review_candidate", "*", "#08306b"),
            ("structure_only_candidate", "o", "#8c510a"),
        ]:
            part = review_centroids[review_centroids["candidate_status"] == status]
            if not part.empty:
                part.plot(ax=ax, marker=marker, color=color, markersize=45, zorder=7)
    xmin, ymin, xmax, ymax = grid.total_bounds
    extent = box(xmin - 8000, ymin - 8000, xmax + 8000, ymax + 8000)
    plot_places(ax, places, extent, label_size=7)
    add_legend(ax)
    ax.set_xlim(xmin - 8000, xmax + 8000)
    ax.set_ylim(ymin - 8000, ymax + 8000)
    ax.set_aspect("equal")
    ax.set_title("CLGB 2 km Numbered Grid Overview", fontsize=15)
    ax.set_xlabel("Easting EPSG:3067 (m)")
    ax.set_ylabel("Northing EPSG:3067 (m)")
    ax.grid(alpha=0.2, linewidth=0.4)
    fig.tight_layout()
    fig.savefig(out_path, dpi=180)
    plt.close(fig)


def atlas_tiles(grid: gpd.GeoDataFrame):
    xmin, ymin, xmax, ymax = grid.total_bounds
    xs = np.arange(math.floor(xmin / ATLAS_TILE_M) * ATLAS_TILE_M, xmax + ATLAS_TILE_M, ATLAS_TILE_M)
    ys = np.arange(math.floor(ymin / ATLAS_TILE_M) * ATLAS_TILE_M, ymax + ATLAS_TILE_M, ATLAS_TILE_M)
    tiles = []
    for y0 in sorted(ys[:-1], reverse=True):
        for x0 in xs[:-1]:
            geom = box(x0, y0, x0 + ATLAS_TILE_M, y0 + ATLAS_TILE_M)
            if grid.intersects(geom).any():
                tiles.append(geom)
    return tiles


def make_atlas_pdf(grid: gpd.GeoDataFrame, places: gpd.GeoDataFrame, out_path: Path) -> int:
    tiles = atlas_tiles(grid)
    with PdfPages(out_path) as pdf:
        for page_no, tile in enumerate(tiles, 1):
            tile_grid = grid[grid.intersects(tile)].copy()
            fig, ax = plt.subplots(figsize=(11, 11))
            plot_grid(ax, tile_grid, label_numbers=True, label_size=4.2)
            plot_places(ax, places, tile.buffer(3500), label_size=7)
            add_legend(ax)
            xmin, ymin, xmax, ymax = tile.bounds
            ax.set_xlim(xmin - 1000, xmax + 1000)
            ax.set_ylim(ymin - 1000, ymax + 1000)
            ax.set_aspect("equal")
            ax.set_title(f"CLGB 2 km Numbered Grid Atlas - Page {page_no}/{len(tiles)}", fontsize=13)
            ax.set_xlabel("Easting EPSG:3067 (m)")
            ax.set_ylabel("Northing EPSG:3067 (m)")
            ax.grid(alpha=0.25, linewidth=0.35)
            fig.tight_layout()
            pdf.savefig(fig, dpi=180)
            plt.close(fig)
    return len(tiles)


def write_qgis_project(outputs: Path, grid_layer: str, places_layer: str) -> Path:
    qgs_name = "clgb_grid_2km_numbered.qgs"
    qgz_path = outputs / "clgb_grid_2km_numbered.qgz"
    qgs = f"""<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.34" projectname="CLGB 2km Numbered Grid Atlas">
  <title>CLGB 2km Numbered Grid Atlas</title>
  <projectCrs>
    <spatialrefsys>
      <wkt>PROJCRS[&quot;ETRS89 / TM35FIN(E,N)&quot;]</wkt>
      <proj4>+proj=utm +zone=35 +ellps=GRS80 +units=m +no_defs</proj4>
      <srsid>3067</srsid>
      <srid>3067</srid>
      <authid>EPSG:3067</authid>
      <description>ETRS89 / TM35FIN(E,N)</description>
      <projectionacronym>utm</projectionacronym>
      <ellipsoidacronym>EPSG:7019</ellipsoidacronym>
      <geographicflag>false</geographicflag>
    </spatialrefsys>
  </projectCrs>
  <maplayers>
    <maplayer type="vector" geometry="Polygon">
      <id>clgb_grid_2km_numbered</id>
      <layername>clgb_grid_2km_numbered</layername>
      <datasource>{escape(grid_layer)}</datasource>
      <provider encoding="UTF-8">ogr</provider>
    </maplayer>
    <maplayer type="vector" geometry="Point">
      <id>clgb_settlement_labels</id>
      <layername>clgb_settlement_labels</layername>
      <datasource>{escape(places_layer)}</datasource>
      <provider encoding="UTF-8">ogr</provider>
    </maplayer>
  </maplayers>
</qgis>
"""
    with zipfile.ZipFile(qgz_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(qgs_name, qgs)
    return qgz_path


def build_report(outputs: Path, numbered: gpd.GeoDataFrame, places: gpd.GeoDataFrame,
                 place_source: str, atlas_pages: int) -> None:
    review = numbered[numbered["candidate_status"].isin([
        "structure_only_candidate", "structure_gravity_review_candidate"
    ])].copy()
    multilayer = numbered[numbered["candidate_status"] == "structure_gravity_review_candidate"].copy()
    lines = [
        "# Grid Atlas Report",
        "",
        "This is a spatial-orientation product only. It does not create target memos and does not upgrade any review candidate to target status.",
        "",
        "## Numbering Method",
        "",
        "- Grid: CLGB 2 km grid.",
        "- Sort order: descending `centroid_y` (north to south).",
        "- Within each row: ascending `centroid_x` (west to east).",
        "- `map_number` starts at 1 in the northwest/top-left and increments row-by-row.",
        "- Numbering is independent of the original `cell_id`; the lookup CSV is the crosswalk.",
        "",
        "## Counts",
        "",
        f"- Total 2 km squares: **{len(numbered)}**",
        f"- Total numbered squares: **{numbered['map_number'].notna().sum()}**",
        f"- Atlas pages: **{atlas_pages}**",
        f"- Towns/settlements labelled: **{len(places)}**",
        f"- Place-name source: **{place_source}**",
        "",
        "## Nearest Town Assignment",
        "",
        "- Settlement points were projected to EPSG:3067.",
        "- For each grid-cell centroid, nearest settlement was assigned by Euclidean distance in metres.",
        "- Distance is reported as `distance_to_nearest_town_km` in the lookup CSV.",
        "",
        "## Candidate Counts",
        "",
        f"- Review candidates: **{len(review)}**",
        f"- Structure-gravity / multi-layer review candidates: **{len(multilayer)}**",
        f"- Structure-only candidates: **{int((numbered['candidate_status'] == 'structure_only_candidate').sum())}**",
        "",
        "## The 16 Multi-Layer Review Candidates",
        "",
        "| map_number | cell_id | nearest_town | distance_km | centroid_lat | centroid_lon |",
        "|------------|---------|--------------|-------------|--------------|--------------|",
    ]
    for row in multilayer.sort_values("map_number").itertuples():
        lines.append(
            f"| {row.map_number} | {row.cell_id} | {row.nearest_town} | "
            f"{row.distance_to_nearest_town_km:.2f} | {row.centroid_lat:.6f} | {row.centroid_lon:.6f} |"
        )
    lines += [
        "",
        "## Outputs",
        "",
        "- `clgb_grid_2km_numbered.gpkg`: numbered grid with candidate and nearest-place attributes.",
        "- `clgb_grid_2km_number_lookup.csv`: master lookup table.",
        "- `clgb_grid_2km_numbered_overview.png`: clean overview.",
        "- `clgb_grid_2km_numbered_atlas.pdf`: zoomed numbered atlas pages.",
        "- `clgb_settlement_labels.gpkg`: settlement label points.",
        "- `clgb_grid_2km_numbered.qgz`: QGIS-ready project package.",
        "",
        "## Candidate Claim Freeze",
        "",
        "- No gold targets exist yet.",
        "- No target memos are allowed from this atlas.",
        "- Allowed review labels only: `structure_gravity_review_candidate`, `structure_only_candidate`, `insufficient_data`, plus legal/restriction masks for orientation.",
        "",
    ]
    (outputs / "GRID_ATLAS_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    cfg = load_config()
    outputs = get_path(cfg, "outputs", create=True)
    grid_path = outputs / "clgb_grid_2km.gpkg"
    if not grid_path.exists():
        raise FileNotFoundError(f"2 km grid missing: {grid_path}")

    grid = gpd.read_file(grid_path).to_crs(PROJECT_CRS)
    numbered = assign_map_numbers(grid)
    context = load_candidate_context(outputs)
    numbered = numbered.merge(context, on="cell_id", how="left")
    numbered["legal_status"] = numbered["legal_status"].fillna("unknown")
    numbered["restriction_status"] = numbered["restriction_status"].fillna("unknown")
    numbered["candidate_status"] = numbered["candidate_status"].fillna("insufficient_data")
    numbered["cluster_id"] = numbered["cluster_id"] if "cluster_id" in numbered.columns else None

    aoi_buffer = box(*numbered.total_bounds).buffer(PLACE_BUFFER_M)
    places, place_source = fetch_overpass_places(aoi_buffer, outputs)
    if places is None:
        places = fallback_places()
        place_source = "fallback curated settlement list (Overpass unavailable)"
    places = dedupe_places(places, aoi_buffer)
    numbered = assign_nearest_places(numbered, places)

    grid_out = outputs / "clgb_grid_2km_numbered.gpkg"
    places_out = outputs / "clgb_settlement_labels.gpkg"
    numbered.to_file(grid_out, layer="clgb_grid_2km_numbered", driver="GPKG")
    places.to_file(places_out, layer="clgb_settlement_labels", driver="GPKG")

    lookup_cols = [
        "map_number",
        "cell_id",
        "centroid_x",
        "centroid_y",
        "centroid_lat",
        "centroid_lon",
        "cluster_id",
        "legal_status",
        "restriction_status",
        "candidate_status",
        "nearest_town",
        "distance_to_nearest_town_km",
    ]
    numbered[lookup_cols].to_csv(outputs / "clgb_grid_2km_number_lookup.csv", index=False)

    make_overview(numbered, places, outputs / "clgb_grid_2km_numbered_overview.png")
    atlas_pages = make_atlas_pdf(numbered, places, outputs / "clgb_grid_2km_numbered_atlas.pdf")
    write_qgis_project(
        outputs,
        "clgb_grid_2km_numbered.gpkg|layername=clgb_grid_2km_numbered",
        "clgb_settlement_labels.gpkg|layername=clgb_settlement_labels",
    )
    build_report(outputs, numbered, places, place_source, atlas_pages)

    log.info("Numbered %d cells; settlement labels=%d; atlas pages=%d",
             len(numbered), len(places), atlas_pages)
    log.info("Wrote grid atlas outputs to %s", outputs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
