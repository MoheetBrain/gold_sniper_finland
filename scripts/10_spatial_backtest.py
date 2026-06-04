"""
10 — Spatial backtest / validation  (STEP 2 STUB — not yet implemented).

PURPOSE
    Validate the model HONESTLY using spatial cross-validation (leave-one-district-
    out), top-k area capture, and comparison against simple baselines. Hide known
    deposits and check whether the model rediscovers them.

INPUTS
    feature stack + labels + trained model (scripts 06-09)

OUTPUTS
    data/outputs/tables/spatial_cv_results.csv
    data/outputs/tables/topk_capture.csv
    data/outputs/tables/baseline_comparison.csv   (vs distance-to-major-shear etc.)
    data/outputs/figures/capture_curve.png

WHY IT MATTERS
    Random train/test splits leak spatial autocorrelation and produce fake skill.
    The real test: do hidden known deposits fall in the top 5-10% of ranked area,
    and does the ML beat a dumb distance-to-shear baseline? If not -> KILL per the
    architecture's kill criteria.

DATA NEEDED BEFORE THIS CAN RUN
    Everything from scripts 05-09. This is the decision gate for continuing Step 2.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import get_logger, load_config  # noqa: E402

log = get_logger("10_backtest")


def main() -> int:
    load_config()
    log.warning("STEP 2 STUB: 10_spatial_backtest is not implemented yet.")
    log.warning("Use leave-one-district-out CV + top-k capture; must beat distance-to-shear baseline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
