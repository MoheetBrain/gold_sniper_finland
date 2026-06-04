"""
08 — Build unlabelled / background cells (positive-unlabelled framing).

WHY
    Unknown ground is NOT barren. We do NOT create true negatives. Instead we mark:
      - positive cells (from script 07),
      - a buffer zone (within positive_exclusion_buffer_m of a positive) which is
        ambiguous and EXCLUDED from background,
      - the remaining cells = UNLABELLED background (used as the "unlabelled" class in
        PU learning, never as confirmed negatives).

BIAS NOTE
    Ideally we would also down-weight cells sampled only along roads / historically
    surveyed corridors. We have no exploration-bias layer yet, so we use ALL remaining
    cells and document the limitation rather than inventing a bias correction.

OUTPUTS
    data/processed/unlabelled_background_cells.gpkg
    data/processed/cell_role_<grid>.parquet     (positive / buffer_excluded / background)
    data/outputs/STEP2_BACKGROUND_SAMPLING_REPORT.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import get_logger, get_path, load_config  # noqa: E402

log = get_logger("08_background")


def assign_roles(grid: gpd.GeoDataFrame, positives: gpd.GeoDataFrame,
                 buffer_m: float) -> gpd.GeoDataFrame:
    """Label each cell positive / buffer_excluded / background."""
    grid = grid.copy()
    cents = gpd.GeoSeries(gpd.points_from_xy(grid["centroid_x"], grid["centroid_y"]),
                          crs=grid.crs)
    if positives is None or positives.empty:
        grid["role"] = "background"
        grid["dist_to_positive_m"] = pd.NA
        return grid

    pos_union = positives.geometry.union_all()
    dist = cents.distance(pos_union)
    grid["dist_to_positive_m"] = dist.round(1).values

    # A cell is positive if it actually contains a positive point.
    contains_pos = grid["geometry"].apply(lambda g: positives.intersects(g).any())
    role = []
    for is_pos, d in zip(contains_pos, dist):
        if is_pos:
            role.append("positive")
        elif d <= buffer_m:
            role.append("buffer_excluded")
        else:
            role.append("background")
    grid["role"] = role
    return grid


def main() -> int:
    cfg = load_config()
    processed = get_path(cfg, "processed")
    outputs = get_path(cfg, "outputs")
    buffer_m = float(cfg["background"]["positive_exclusion_buffer_m"])

    pos_path = processed / "clgb_positive_labels.gpkg"
    positives = gpd.read_file(pos_path) if pos_path.exists() else None

    summary = {}
    bg_to_save = None
    for gname in ["clgb_grid_2km", "clgb_grid_1km"]:
        gp = outputs / f"{gname}.gpkg"
        if not gp.exists():
            continue
        grid = gpd.read_file(gp)
        roled = assign_roles(grid, positives, buffer_m)
        counts = roled["role"].value_counts().to_dict()
        summary[gname] = counts
        size = gname.split("_")[-1]
        roled[["cell_id", "role", "dist_to_positive_m"]].to_parquet(
            processed / f"cell_role_{size}.parquet", index=False)
        if gname == cfg["step2"]["primary_grid"].replace(".gpkg", ""):
            bg_to_save = roled[roled["role"] == "background"].copy()
        log.info("%s roles: %s", gname, counts)

    if bg_to_save is not None:
        bg_to_save.to_file(processed / "unlabelled_background_cells.gpkg",
                           layer="unlabelled_background_cells", driver="GPKG")
        log.info("Wrote unlabelled_background_cells.gpkg (%d cells)", len(bg_to_save))

    L = ["# Step 2 Background / Unlabelled Sampling Report", "",
         "Positive-unlabelled framing: unknown ground is **unlabelled, not barren**.", "",
         f"- Positive exclusion buffer: **{buffer_m:.0f} m** around each positive deposit.",
         "", "## Cell roles per grid", "",
         "| grid | positive | buffer_excluded | background |",
         "|------|----------|-----------------|------------|"]
    for g, c in summary.items():
        L.append(f"| {g} | {c.get('positive',0)} | {c.get('buffer_excluded',0)} | {c.get('background',0)} |")
    L += ["", "## Method",
          "- `positive`: cell contains a CLGB orogenic-gold deposit (script 07).",
          f"- `buffer_excluded`: cell centroid within {buffer_m:.0f} m of a positive — ambiguous,",
          "  excluded from BOTH positive and background to avoid label bleed.",
          "- `background`: everything else — the UNLABELLED class for PU learning. These are",
          "  NOT negatives; many are simply unexplored.",
          "", "## Limitations",
          "- No exploration-bias layer (roads / historical survey corridors), so background",
          "  is uniform over remaining cells. Document & revisit when a bias layer exists.",
          "- With very few positives, the positive/background split is highly imbalanced —",
          "  interpret model output cautiously.", ""]
    (outputs / "STEP2_BACKGROUND_SAMPLING_REPORT.md").write_text("\n".join(L), encoding="utf-8")
    log.info("Wrote STEP2_BACKGROUND_SAMPLING_REPORT.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
