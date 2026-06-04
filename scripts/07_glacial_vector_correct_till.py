"""
07 — Glacial-vectored till geochemistry  (STEP 2 STUB — not yet implemented).

PURPOSE
    Process till geochemistry (Au, As, Sb, Te, Bi, W, ...) into anomaly layers AND
    correct for glacial transport: shift/trace anomalies up-ice toward their likely
    bedrock source using ice-flow vectors, so we score the SOURCE, not the smear.

INPUTS
    data/raw/gtk_till_geochemistry/   till sample points or grids
    data/raw/gtk_quaternary/          glacial flow lines / ice-flow azimuths
    data/processed/aoi_grid.gpkg

OUTPUTS
    data/processed/evidence_layers/   au_anomaly, pathfinder_score (glacially vectored)

WHY IT MATTERS GEOLOGICALLY
    In Finland the bedrock is blanketed by glacial till. A till anomaly often sits
    DOWN-ICE of its bedrock source by hundreds of metres to kilometres. Ignoring
    ice flow points targets at the wrong cell. Pathfinder elements (As, Sb, Te, Bi,
    W) extend the footprint of buried gold systems.

DATA NEEDED BEFORE THIS CAN RUN
    Till geochemistry (#6) AND glacial/Quaternary flow data (#7). Without ice-flow
    vectors, only un-corrected anomalies are possible (flag them as such).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import get_logger, load_config  # noqa: E402

log = get_logger("07_till")


def main() -> int:
    load_config()
    log.warning("STEP 2 STUB: 07_glacial_vector_correct_till is not implemented yet.")
    log.warning("Needs till geochemistry + glacial flow data (see docs/STEP2_DATA_REQUIREMENTS.md).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
