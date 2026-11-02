"""
02 — Build the legal / taken-area mask.

WHAT THIS DOES  (the heart of Step 1)
    1. Finds every shapefile extracted from the Tukes downloads.
    2. Reads them safely, cleans invalid geometries, reprojects to EPSG:3067.
    3. Merges all legal rights (reservations, permits, concessions, claims,
       gold-panning) into one layer: data/processed/tukes_all_rights.gpkg.
    4. Intersects those rights with the AOI grid and, for every cell, computes:
         - taken_area_m2      union area of the cell covered by ANY right
         - taken_overlap_pct  that area as a % of the cell
         - taken_layer_count  how many distinct Tukes layers touch the cell
         - source_layers      which layers touch the cell
    5. Classifies each cell open / partly_taken / taken and flags is_clean_open.
    6. Writes open / partly_taken / taken GeoPackages + cell_legal_status.csv.

WHY THIS COMES BEFORE GEOLOGY
    There is no point ranking a cell for gold if the ground is already reserved,
    permitted or claimed. Step 1 builds the availability filter first so Step 2's
    geology work is only ever spent on ground that could actually be pursued.

IMPORTANT
    `taken_area_m2` uses the UNION of all rights within a cell, so overlapping
    rights are never double-counted and taken_overlap_pct can never exceed 100%.
    `taken_layer_count` counts distinct source layers (so you can see convergence
    of multiple right types on the same ground).
"""
from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import PROJECT_CRS, get_logger, get_path, load_config  # noqa: E402

log = get_logger("02_mask_taken")

# Only treat (multi)polygons as "taken area"; points/lines in the cadastre (if any)
# do not consume ground and would distort overlap maths.
POLYGON_TYPES = {"Polygon", "MultiPolygon"}


def find_vector_files(extract_dir: Path) -> list[Path]:
    """
    Find Tukes vector files to load.

    We prefer .shp (one clean polygon layer per dataset). The Tukes ZIPs also ship
    .mif/.tab copies of the SAME geometries, so loading those too would double-count.
    If a dataset somehow ships only .mif/.tab, we fall back to those.
    """
    shp = sorted(extract_dir.rglob("*.shp"))
    if shp:
        return shp
    log.warning("No .shp files found under %s — falling back to .mif/.tab", extract_dir)
    return sorted(extract_dir.rglob("*.mif")) + sorted(extract_dir.rglob("*.tab"))


def _source_label(path: Path, extract_dir: Path) -> str:
    """A stable, human-readable source label = top extracted folder name."""
    try:
        rel = path.relative_to(extract_dir)
        return rel.parts[0]  # e.g. 'valtaus_2026-06-02'
    except ValueError:
        return path.stem


def load_and_clean(path: Path, extract_dir: Path, target_crs: str) -> gpd.GeoDataFrame | None:
    """
    Read one vector file, keep polygons, fix invalid geometries, reproject.

    Returns a GeoDataFrame with a single `source_layer` attribute, or None if the
    file has nothing usable.
    """
    try:
        gdf = gpd.read_file(path)
    except Exception as exc:  # noqa: BLE001 — one bad file shouldn't kill the run
        log.error("Could not read %s: %s", path.name, exc)
        return None

    if gdf.empty:
        log.warning("Empty layer: %s", path.name)
        return None

    # Missing CRS is a hard error; never silently relabel coordinates.
    if gdf.crs is None:
        raise ValueError("Source CRS missing; obtain metadata instead of assuming coordinates")
    if str(gdf.crs) != target_crs:
        gdf = gdf.to_crs(target_crs)

    # Drop empties / nulls, fix invalid geometries (self-intersections etc.).
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
    invalid = ~gdf.geometry.is_valid
    if invalid.any():
        log.info("%s: repairing %d invalid geometr(y/ies)", path.name, int(invalid.sum()))
        gdf.loc[invalid, gdf.geometry.name] = gdf.loc[invalid, gdf.geometry.name].make_valid()

    # Keep only polygonal features.
    gdf = gdf[gdf.geometry.geom_type.isin(POLYGON_TYPES)].copy()
    if gdf.empty:
        log.warning("%s: no polygon features after cleaning — skipping", path.name)
        return None

    label = _source_label(path, extract_dir)
    # Build from the geometry array first (gives the frame a length/index), then
    # attach the scalar provenance columns.
    out = gpd.GeoDataFrame(geometry=gdf.geometry.values, crs=target_crs)
    out["source_layer"] = label
    out["source_file"] = path.name
    out = out[["source_layer", "source_file", "geometry"]]
    log.info("Loaded %-45s %4d polygons  (%s)", path.name, len(out), label)
    return out


def merge_rights(files: list[Path], extract_dir: Path, target_crs: str) -> gpd.GeoDataFrame:
    """Load + clean every file and concatenate into one rights layer."""
    parts = [g for f in files if (g := load_and_clean(f, extract_dir, target_crs)) is not None]
    if not parts:
        return gpd.GeoDataFrame({"source_layer": [], "source_file": []},
                               geometry=[], crs=target_crs)
    merged = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=target_crs)
    return merged


def compute_cell_status(grid: gpd.GeoDataFrame, rights: gpd.GeoDataFrame,
                        cfg: dict) -> gpd.GeoDataFrame:
    """
    Attach taken-area metrics + legal status to each grid cell.

    Uses a single overlay(intersection) between grid and rights:
      - dissolving the intersection pieces per cell gives the UNION taken area
        (overlapping rights counted once);
      - grouping the pieces per cell gives the distinct source-layer count/list.
    """
    open_max = float(cfg["legal_status"]["open_max_pct"])
    partly_max = float(cfg["legal_status"]["partly_taken_max_pct"])

    grid = grid.copy()
    cell_area_m2 = grid["area_km2"] * 1_000_000.0

    if rights.empty:
        log.warning("No rights polygons loaded — every cell will be marked OPEN.")
        grid["taken_area_m2"] = 0.0
        grid["taken_overlap_pct"] = 0.0
        grid["taken_layer_count"] = 0
        grid["source_layers"] = ""
    else:
        # Intersection pieces: one row per (cell, right) overlap.
        inter = gpd.overlay(
            grid[["cell_id", "geometry"]],
            rights[["source_layer", "geometry"]],
            how="intersection",
            keep_geom_type=True,
        )
        inter = inter[~inter.geometry.is_empty].copy()

        # UNION taken area per cell (dissolve unions overlapping pieces -> no double count).
        if inter.empty:
            taken_area = pd.Series(dtype="float64")
            layer_info = pd.DataFrame(columns=["taken_layer_count", "source_layers"])
        else:
            dissolved = inter.dissolve(by="cell_id")
            taken_area = dissolved.geometry.area  # indexed by cell_id

            # Distinct source layers per cell.
            grp = inter.groupby("cell_id")["source_layer"].agg(
                lambda s: sorted(set(s))
            )
            layer_info = pd.DataFrame({
                "taken_layer_count": grp.apply(len),
                "source_layers": grp.apply(lambda lst: "; ".join(lst)),
            })

        grid = grid.set_index("cell_id")
        grid["taken_area_m2"] = taken_area.reindex(grid.index).fillna(0.0)
        grid = grid.join(layer_info)
        grid["taken_layer_count"] = grid["taken_layer_count"].fillna(0).astype(int)
        grid["source_layers"] = grid["source_layers"].fillna("")
        grid = grid.reset_index()
        cell_area_m2 = grid["area_km2"] * 1_000_000.0

    # Overlap %: clamp tiny float dust to 0; cap at 100 for safety.
    pct = (grid["taken_area_m2"] / cell_area_m2 * 100.0).round(6).clip(upper=100.0)
    grid["taken_overlap_pct"] = pct

    # Classify. open: <=open_max ; partly: (open_max, partly_max] ; taken: >partly_max
    def classify(p: float) -> str:
        if p <= open_max:
            return "open"
        if p <= partly_max:
            return "partly_taken"
        return "taken"

    grid["legal_status"] = grid["taken_overlap_pct"].apply(classify)
    # Stricter flag: only truly untouched cells.
    grid["is_clean_open"] = grid["taken_overlap_pct"] == 0.0

    return grid


def main() -> int:
    cfg = load_config()
    crs = cfg["project"].get("crs", PROJECT_CRS)

    processed_dir = get_path(cfg, "processed", create=True)
    outputs_dir = get_path(cfg, "outputs", create=True)
    extract_dir = get_path(cfg, "tukes_extracted")

    # --- Load AOI grid (must exist; produced by script 01) ---
    grid_path = processed_dir / "aoi_grid.gpkg"
    if not grid_path.exists():
        log.error("AOI grid not found: %s — run 01_make_aoi_grid.py first.", grid_path)
        return 2
    grid = gpd.read_file(grid_path, layer="aoi_grid")
    log.info("Loaded AOI grid: %d cells", len(grid))

    # --- Load + merge Tukes rights ---
    if not extract_dir.exists():
        log.warning("Tukes extracted dir missing: %s (downloads may have failed).",
                    extract_dir)
        files: list[Path] = []
    else:
        files = find_vector_files(extract_dir)
    log.info("Found %d Tukes vector file(s) to load.", len(files))

    rights = merge_rights(files, extract_dir, crs)
    log.info("Merged rights: %d polygons across %d source layer(s).",
             len(rights), rights["source_layer"].nunique() if not rights.empty else 0)

    rights_path = processed_dir / "tukes_all_rights.gpkg"
    if not rights.empty:
        rights.to_file(rights_path, layer="tukes_all_rights", driver="GPKG")
        log.info("Wrote %s", rights_path)
    else:
        log.warning("No rights to write — skipping %s", rights_path)

    # --- Compute per-cell legal status ---
    status = compute_cell_status(grid, rights, cfg)

    counts = status["legal_status"].value_counts().to_dict()
    log.info("Cell status: open=%d  partly_taken=%d  taken=%d  (clean_open=%d)",
             counts.get("open", 0), counts.get("partly_taken", 0),
             counts.get("taken", 0), int(status["is_clean_open"].sum()))

    # --- Write outputs ---
    out_cols = ["cell_id", "area_km2", "centroid_x", "centroid_y",
                "taken_area_m2", "taken_overlap_pct", "taken_layer_count",
                "source_layers", "legal_status", "is_clean_open", "geometry"]
    status = status[out_cols]

    splits = {
        "open_cells.gpkg": ("open_cells", status[status["legal_status"] == "open"]),
        "partly_taken_cells.gpkg": ("partly_taken_cells",
                                    status[status["legal_status"] == "partly_taken"]),
        "taken_cells.gpkg": ("taken_cells", status[status["legal_status"] == "taken"]),
    }
    for fname, (layer, gdf) in splits.items():
        path = outputs_dir / fname
        if gdf.empty:
            # Write an empty layer with the right schema so downstream reads don't crash.
            gpd.GeoDataFrame(gdf, crs=status.crs).to_file(path, layer=layer, driver="GPKG")
            log.warning("%s: 0 cells (wrote empty layer)", fname)
        else:
            gdf.to_file(path, layer=layer, driver="GPKG")
            log.info("Wrote %s (%d cells)", fname, len(gdf))

    # Full CSV (no geometry) for quick inspection / joins.
    csv_path = outputs_dir / "cell_legal_status.csv"
    status.drop(columns="geometry").to_csv(csv_path, index=False)
    log.info("Wrote %s", csv_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
