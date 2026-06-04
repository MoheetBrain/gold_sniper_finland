"""
12 — Make target memos  (STEP 2 STUB — not yet implemented).

PURPOSE
    Generate a conservative, geologist-readable memo per top-ranked target: location
    & legal status, deposit model fit, evidence layers, model score + uncertainty,
    false-positive checks, validation plan, and commercial/partner fit.

INPUTS
    data/outputs/ranked_real_targets.gpkg   (script 11)
    data/outputs/tables/falsification_report.csv
    evidence layers + maps for figures

OUTPUTS
    data/outputs/target_memos/<TARGET_ID>_memo.md  (+ figures; PDF optional later)

WHY IT MATTERS
    The product of this project is not a heatmap — it is a defensible target package
    a junior explorer / consultant can review. Language must be conservative:
    "AI-assisted prospectivity ranking identified a structurally plausible orogenic
    gold target with multi-layer geophysical and geochemical support" — never
    "AI found gold".

DATA NEEDED BEFORE THIS CAN RUN
    Ranked, falsified targets from script 11 and their evidence/figures.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import get_logger, load_config  # noqa: E402

log = get_logger("12_memos")


def main() -> int:
    load_config()
    log.warning("STEP 2 STUB: 12_make_target_memos is not implemented yet.")
    log.warning("Conservative geology language only. Requires ranked targets from script 11.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
