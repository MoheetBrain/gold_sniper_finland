"""
05 — Load GTK geology / geophysics layers  (STEP 2 STUB — not yet implemented).

PURPOSE
    Ingest the GTK datasets (bedrock geology, magnetics, gravity, EM, radiometrics)
    and standardise them: reproject to EPSG:3067, clip to the AOI, record metadata.
    This is the Step 2 equivalent of script 00/02 for the *scientific* layers.

INPUTS (place under data/raw/, see docs/STEP2_DATA_REQUIREMENTS.md)
    data/raw/gtk_geology/         bedrock geology polygons
    data/raw/gtk_magnetics/       airborne magnetic grid(s)
    data/raw/gtk_gravity/         gravity grid (optional)
    data/raw/gtk_em/              airborne EM grid (optional)
    data/raw/gtk_radiometrics/    K/U/Th grids (optional)

OUTPUTS
    data/interim/reprojected/     all layers in EPSG:3067, clipped to AOI
    data/raw/metadata/gtk_sources.csv   provenance (source, date, licence)

WHY IT MATTERS GEOLOGICALLY
    Everything downstream (structure, lithology, alteration, scoring) depends on a
    clean, co-registered, common-CRS stack. Garbage-in here poisons the whole model.

DATA NEEDED BEFORE THIS CAN RUN
    At minimum #1 (bedrock geology) and #3 (magnetics) from the Step 2 requirements.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import get_logger, load_config  # noqa: E402

log = get_logger("05_load_gtk")


def main() -> int:
    load_config()
    log.warning("STEP 2 STUB: 05_load_gtk_layers is not implemented yet.")
    log.warning("Provide GTK layers under data/raw/gtk_* (see docs/STEP2_DATA_REQUIREMENTS.md).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
