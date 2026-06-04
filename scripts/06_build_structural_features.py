"""
06 — Build structural features  (STEP 2 STUB — not yet implemented).

PURPOSE
    Turn structures + magnetics + DEM into per-cell structural evidence layers:
    distance-to-major-shear, distance-to-splay, fault-intersection density,
    lineament density, and magnetic derivatives (1VD, tilt, analytic signal) plus
    magnetic-low (alteration / magnetite-destruction) z-scores.

INPUTS
    data/interim/reprojected/ structures (faults/shears), magnetic grid, DEM
    data/processed/aoi_grid.gpkg

OUTPUTS
    data/processed/evidence_layers/  structural feature rasters / per-cell table
    e.g. dist_to_major_shear, lineament_density, mag_tilt, mag_low_zscore

WHY IT MATTERS GEOLOGICALLY
    Orogenic gold is structurally controlled. Second-order splays, fault bends/jogs
    and intersections localise fluid flow; magnetic-destruction zones flag
    hydrothermal alteration. These are the highest-value predictors in the model.

DATA NEEDED BEFORE THIS CAN RUN
    GTK fault/shear/lineament vectors (#5), magnetics (#3/#4), DEM (#8), and the
    standardised stack from script 05.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import get_logger, load_config  # noqa: E402

log = get_logger("06_structural")


def main() -> int:
    load_config()
    log.warning("STEP 2 STUB: 06_build_structural_features is not implemented yet.")
    log.warning("Needs GTK structures + magnetics + DEM (see docs/STEP2_DATA_REQUIREMENTS.md).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
