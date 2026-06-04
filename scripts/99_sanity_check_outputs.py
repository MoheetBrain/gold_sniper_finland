"""
99 — Sanity checks for Step 1 outputs.

Run AFTER run_step1_pipeline.py. Verifies the pipeline produced internally
consistent, readable, correctly-projected outputs. Exits non-zero if any check
fails, so it doubles as a lightweight CI/regression gate.

Checks:
    - config loads
    - AOI grid exists, is readable in GeoPandas, and is EPSG:3067
    - Tukes rights file exists & readable IF downloads succeeded (else just warn)
    - open / partly_taken / taken GeoPackages exist and are readable
    - all geometries are valid
    - no CRS mismatch across outputs
    - open + partly_taken + taken == total grid count
    - demo ranking exists and is readable
"""
from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import get_logger, get_path, load_config  # noqa: E402

log = get_logger("99_sanity")


class Checker:
    """Tiny pass/fail accumulator with readable logging."""

    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0
        self.warned = 0

    def ok(self, msg: str) -> None:
        self.passed += 1
        log.info("PASS  %s", msg)

    def warn(self, msg: str) -> None:
        self.warned += 1
        log.warning("WARN  %s", msg)

    def fail(self, msg: str) -> None:
        self.failed += 1
        log.error("FAIL  %s", msg)

    def check(self, cond: bool, msg: str) -> bool:
        (self.ok if cond else self.fail)(msg)
        return cond


def _read(path: Path, layer: str, chk: Checker) -> gpd.GeoDataFrame | None:
    if not chk.check(path.exists(), f"exists: {path.name}"):
        return None
    try:
        gdf = gpd.read_file(path, layer=layer)
        chk.ok(f"readable in GeoPandas: {path.name} ({len(gdf)} features)")
        return gdf
    except Exception as exc:  # noqa: BLE001
        chk.fail(f"unreadable: {path.name} — {exc}")
        return None


def main() -> int:
    chk = Checker()

    # 1. Config loads.
    try:
        cfg = load_config()
        chk.ok("config.yaml loads")
    except Exception as exc:  # noqa: BLE001
        log.error("Cannot load config: %s", exc)
        return 1

    processed = get_path(cfg, "processed")
    outputs = get_path(cfg, "outputs")
    target_crs = cfg["project"].get("crs", "EPSG:3067")

    # 2. AOI grid.
    grid = _read(processed / "aoi_grid.gpkg", "aoi_grid", chk)
    total_cells = None
    if grid is not None:
        total_cells = len(grid)
        chk.check(str(grid.crs).upper().endswith("3067"),
                  f"AOI grid CRS is EPSG:3067 (got {grid.crs})")
        chk.check(bool(grid.geometry.is_valid.all()), "AOI grid geometries all valid")
        chk.check({"cell_id", "area_km2", "centroid_x", "centroid_y"}.issubset(grid.columns),
                  "AOI grid has expected columns")

    # 3. Tukes rights (only required if downloads succeeded).
    manifest = get_path(cfg, "raw") / "tukes_download_manifest.json"
    rights_path = processed / "tukes_all_rights.gpkg"
    if manifest.exists() and rights_path.exists():
        rights = _read(rights_path, "tukes_all_rights", chk)
        if rights is not None:
            chk.check(str(rights.crs).upper().endswith("3067"),
                      f"rights CRS is EPSG:3067 (got {rights.crs})")
            chk.check(bool(rights.geometry.is_valid.all()), "rights geometries all valid")
    else:
        chk.warn("Tukes rights file absent — assuming downloads were skipped/failed.")

    # 4. Open / partly / taken outputs.
    counts = {}
    for fname, layer in [("open_cells.gpkg", "open_cells"),
                         ("partly_taken_cells.gpkg", "partly_taken_cells"),
                         ("taken_cells.gpkg", "taken_cells")]:
        gdf = _read(outputs / fname, layer, chk)
        if gdf is not None:
            counts[layer] = len(gdf)
            if len(gdf):
                chk.check(str(gdf.crs).upper().endswith("3067"),
                          f"{fname} CRS is EPSG:3067 (got {gdf.crs})")
                chk.check(bool(gdf.geometry.is_valid.all()),
                          f"{fname} geometries all valid")

    # 5. Counts add up.
    if total_cells is not None and len(counts) == 3:
        parts = sum(counts.values())
        chk.check(parts == total_cells,
                  f"open+partly+taken == total grid ({parts} == {total_cells})")

    # 6. Demo ranking.
    _read(outputs / "ranked_open_cells_demo.gpkg", "ranked_open_cells_demo", chk)

    # --- Verdict ---
    log.info("=" * 60)
    log.info("SANITY: %d passed, %d warnings, %d failed",
             chk.passed, chk.warned, chk.failed)
    log.info("=" * 60)
    return 0 if chk.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
