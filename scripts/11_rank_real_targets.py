"""
11 — Rank real targets  (STEP 2 STUB — not yet implemented).

PURPOSE
    Combine the validated prospectivity score with the Step 1 legal mask and the
    restriction masks to rank GENUINE, PURSUABLE targets. Cluster top cells into
    coherent targets, then falsify single-signal / restricted / artefact targets.

INPUTS
    data/outputs/prospectivity_scores.gpkg   (script 09, validated by 10)
    data/outputs/open_cells.gpkg             (Step 1 legal mask)
    data/raw/restrictions/*                   (protected/Natura/Sámi/water masks)
    data/processed/evidence_layers/           (to check multi-layer convergence)

OUTPUTS
    data/outputs/tables/top20_targets.csv
    data/outputs/tables/falsification_report.csv
    data/outputs/ranked_real_targets.gpkg

WHY IT MATTERS
    This is where geology meets law. A high model score on already-taken or
    protected ground is worthless. Only multi-layer-convergent, OPEN, non-falsified
    targets survive. Single-signal anomalies are killed here.

DATA NEEDED BEFORE THIS CAN RUN
    A validated model (scripts 09/10), Step 1 outputs (already done), and the
    restriction layers (currently placeholders in 02b).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import get_logger, load_config  # noqa: E402

log = get_logger("11_rank_targets")


def main() -> int:
    load_config()
    log.warning("STEP 2 STUB: 11_rank_real_targets is not implemented yet.")
    log.warning("Requires validated model + Step 1 legal mask + restriction masks; kill single-signal targets.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
