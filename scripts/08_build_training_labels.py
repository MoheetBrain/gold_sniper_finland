"""
08 — Build training labels  (STEP 2 STUB — not yet implemented).

PURPOSE
    Convert known gold deposits/occurrences into POSITIVE labels and define the
    UNLABELLED background. Crucially: background is *unlabelled*, NOT negative.

INPUTS
    data/raw/gtk_mineral_occurrences/   known deposits / occurrences (points)
    data/processed/aoi_grid.gpkg
    data/processed/evidence_layers/     (to attach features to labelled cells)

OUTPUTS
    data/processed/labels/labels_positive.gpkg
    data/processed/labels/model_labels.parquet   (cell_id, label, confidence)

WHY IT MATTERS GEOLOGICALLY / STATISTICALLY
    Most of the belt is unexplored. Treating every un-mineralised cell as a true
    negative teaches the model that unexplored = barren, which is false and will
    bury new discoveries. We label known deposits positive and keep the rest
    unlabelled for positive-unlabelled / semi-supervised learning.

DATA NEEDED BEFORE THIS CAN RUN
    GTK mineral occurrence DB (#2). Separate economic deposits from minor showings
    where the data allows.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import get_logger, load_config  # noqa: E402

log = get_logger("08_labels")


def main() -> int:
    load_config()
    log.warning("STEP 2 STUB: 08_build_training_labels is not implemented yet.")
    log.warning("Background is UNLABELLED, not negative. Needs GTK mineral occurrences (#2).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
