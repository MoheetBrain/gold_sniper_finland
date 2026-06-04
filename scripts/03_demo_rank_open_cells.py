"""
03 — Demo ranker for open cells.

!!!  THIS SCORE IS FAKE  !!!
    `demo_score` is a reproducible RANDOM number. It is NOT geological, NOT a
    prospectivity estimate, and means NOTHING about gold. Its only purpose is to
    prove the Step 1 plumbing works end-to-end: open cells -> scored -> ranked ->
    exported -> viewable in QGIS. Real scoring arrives in Step 2 (GTK geology,
    geophysics, till geochemistry + ML).

WHAT IT DOES
    - Reads data/outputs/open_cells.gpkg (clean/open ground from script 02).
    - Assigns a deterministic fake score per cell (seeded RNG -> reproducible).
    - Ranks cells (1 = highest demo_score).
    - Writes ranked_open_cells_demo.gpkg and .csv with rank, demo_score,
      taken_overlap_pct, is_clean_open and centroid coordinates.
"""
from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import get_logger, get_path, load_config  # noqa: E402

log = get_logger("03_demo_rank")


def main() -> int:
    cfg = load_config()
    seed = int(cfg["demo_rank"]["random_seed"])
    outputs_dir = get_path(cfg, "outputs", create=True)

    open_path = outputs_dir / "open_cells.gpkg"
    if not open_path.exists():
        log.error("open_cells.gpkg not found: %s — run 02_mask_taken_areas.py first.",
                  open_path)
        return 2

    cells = gpd.read_file(open_path, layer="open_cells")
    if cells.empty:
        log.warning("No open cells to rank — writing empty demo outputs.")

    log.info("Loaded %d open cell(s).", len(cells))
    log.warning("demo_score is FAKE (reproducible random) — NOT geology.")

    # Deterministic fake score: seed RNG by cell_id so it is reproducible AND
    # stable per cell regardless of row order.
    rng = np.random.default_rng(seed)
    if not cells.empty:
        # Sort by cell_id for a stable assignment, then draw scores.
        cells = cells.sort_values("cell_id").reset_index(drop=True)
        cells["demo_score"] = rng.random(len(cells)).round(6)
        cells = cells.sort_values("demo_score", ascending=False).reset_index(drop=True)
        cells["rank"] = np.arange(1, len(cells) + 1)
    else:
        cells["demo_score"] = []
        cells["rank"] = []

    keep = ["rank", "demo_score", "cell_id", "taken_overlap_pct", "is_clean_open",
            "centroid_x", "centroid_y", "geometry"]
    keep = [c for c in keep if c in cells.columns]
    ranked = cells[keep]

    gpkg_path = outputs_dir / "ranked_open_cells_demo.gpkg"
    csv_path = outputs_dir / "ranked_open_cells_demo.csv"
    ranked.to_file(gpkg_path, layer="ranked_open_cells_demo", driver="GPKG")
    ranked.drop(columns="geometry").to_csv(csv_path, index=False)
    log.info("Wrote %s and %s", gpkg_path.name, csv_path.name)

    if not ranked.empty:
        top = ranked.head(5)[["rank", "cell_id", "demo_score"]]
        log.info("Top 5 (FAKE) demo cells:\n%s", top.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
