"""
02b — Protected / restricted-area mask (PLACEHOLDER).

WHY THIS EXISTS
    Tukes rights (script 02) tell us what ground is legally taken by mining titles.
    But ground can also be effectively unavailable for environmental / social /
    statutory reasons that are NOT in the Tukes cadastre, e.g.:
        - Natura 2000 sites
        - other protected areas / nature reserves
        - Sámi homeland area
        - national parks / wilderness areas
        - water bodies / large lakes
        - urban areas / infrastructure
        - reindeer-herding constraints (where data exists)

    A real "is this cell pursuable?" answer needs BOTH masks. This script is the
    framework for the second mask. It does NOT invent data: until the layers are
    placed under data/raw/restrictions/, it just reports what is missing and exits
    cleanly so the pipeline keeps running.

WHAT IT DOES NOW
    - Checks data/raw/restrictions/ for the expected layers.
    - Prints clear instructions for any that are absent.
    - Writes data/raw/restrictions/README_RESTRICTIONS.md (a TODO checklist) if
      it is not already there.
    - Never crashes if data is missing — restriction masking is a later milestone.

WHAT IT WILL DO LATER
    Load each restriction layer, reproject to EPSG:3067, union them, intersect with
    the AOI grid, and add a `restricted_overlap_pct` / `is_restricted` flag so
    Step 2 ranking can exclude environmentally/socially unavailable ground too.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import get_logger, get_path, load_config  # noqa: E402

log = get_logger("02b_restrictions")

# Expected future restriction layers. `filename_hint` is just guidance for the
# human placing the data; the future loader will glob these folders.
EXPECTED_LAYERS = [
    ("natura2000",        "Natura 2000 protected sites (SAC/SPA)"),
    ("protected_areas",   "Other protected areas / nature reserves"),
    ("sami_homeland",     "Sámi homeland area boundary"),
    ("national_parks",    "National parks & wilderness areas"),
    ("water_bodies",      "Lakes / rivers / major water bodies"),
    ("urban_infrastructure", "Urban areas & infrastructure (optional)"),
    ("reindeer_herding",  "Reindeer-herding constraint areas (if available)"),
]

README_TEXT = """# Restriction layers — TODO (Step 1 placeholder)

This folder will hold the *non-cadastre* restriction layers that determine whether
ground is realistically pursuable, on top of the Tukes mining rights handled by
`scripts/02_mask_taken_areas.py`.

Drop each dataset into its own subfolder here, in any GDAL-readable vector format
(`.gpkg`, `.shp`, …). The future loader will reproject everything to **EPSG:3067**.

Expected subfolders:

| subfolder                | what it is                                   | required? | suggested source |
|--------------------------|----------------------------------------------|-----------|------------------|
| `natura2000/`            | Natura 2000 SAC/SPA sites                     | required  | SYKE / Finnish Environment Institute, EEA |
| `protected_areas/`       | Other protected areas / nature reserves       | required  | SYKE / Metsähallitus |
| `sami_homeland/`         | Sámi homeland area boundary                    | required  | Sámi Parliament / statutory boundary |
| `national_parks/`        | National parks & wilderness areas              | required  | Metsähallitus |
| `water_bodies/`          | Lakes / rivers / major water bodies            | optional  | NLS / SYKE Ranta10, MML |
| `urban_infrastructure/`  | Urban areas & infrastructure                   | optional  | NLS topographic database |
| `reindeer_herding/`      | Reindeer-herding constraint areas              | optional  | Paliskuntain yhdistys (if available) |

Until these exist, restriction masking is skipped and the pipeline relies on the
Tukes legal mask only. **Do not invent these layers** — use the official sources.
"""


def main() -> int:
    cfg = load_config()
    restrictions_dir = get_path(cfg, "restrictions", create=True)

    # Write the TODO checklist if absent.
    readme = restrictions_dir / "README_RESTRICTIONS.md"
    if not readme.exists():
        readme.write_text(README_TEXT, encoding="utf-8")
        log.info("Wrote restriction TODO checklist: %s", readme)

    log.info("Checking for restriction layers under %s ...", restrictions_dir)
    present, missing = [], []
    for folder, desc in EXPECTED_LAYERS:
        sub = restrictions_dir / folder
        has_data = sub.exists() and any(
            sub.rglob(f"*.{ext}") for ext in ("gpkg", "shp", "geojson", "json")
        )
        (present if has_data else missing).append((folder, desc))

    if present:
        log.info("Found %d restriction layer folder(s) with data:", len(present))
        for folder, desc in present:
            log.info("   [present] %-22s %s", folder, desc)

    if missing:
        log.warning("Missing %d restriction layer(s) — restriction masking SKIPPED:",
                    len(missing))
        for folder, desc in missing:
            log.warning("   [missing] %-22s %s", folder, desc)
        log.warning("To add them, create data/raw/restrictions/<folder>/ and drop the")
        log.warning("vector data inside. See %s for sources.", readme.name)

    # Placeholder always succeeds — missing data is expected at this stage.
    log.info("Restriction placeholder complete (no masking performed yet).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
