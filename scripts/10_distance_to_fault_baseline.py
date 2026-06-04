"""
10 — Distance-to-fault (and random) baselines.

WHY
    Orogenic gold is fault/shear-hosted, so "closer to a major shear = more
    prospective" is a strong, dumb baseline. Any ML model MUST beat it to justify its
    existence (the gate is enforced in 11b). We also build a random baseline (floor)
    and an optional distance-to-known-deposit baseline (a leaky reference ceiling —
    not for honest ranking).

SCORES (higher = more prospective)
    score_distfault   = 1 / (1 + dist_major_shear_km)
    score_random      = seeded uniform noise
    score_distdeposit = 1 / (1 + dist_to_nearest_positive_km)   [reference only, leaky]

OUTPUTS
    data/processed/baseline_scores_<grid>.parquet
"""
from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import get_logger, get_path, load_config  # noqa: E402

log = get_logger("10_baseline")


def main() -> int:
    cfg = load_config()
    processed = get_path(cfg, "processed")
    outputs = get_path(cfg, "outputs")
    seed = int(cfg["background"].get("random_seed", 42))

    pos_path = processed / "clgb_positive_labels.gpkg"
    positives = gpd.read_file(pos_path) if pos_path.exists() else None

    for gname in ["clgb_grid_2km", "clgb_grid_1km"]:
        fs = processed / f"feature_stack_minimal_{gname.split('_')[-1]}.parquet"
        gp = outputs / f"{gname}.gpkg"
        if not fs.exists() or not gp.exists():
            continue
        feat = pd.read_parquet(fs)
        grid = gpd.read_file(gp)[["cell_id", "centroid_x", "centroid_y"]]
        df = feat.merge(grid, on="cell_id", suffixes=("", "_g"))

        # distance-to-fault baseline
        if df["dist_major_shear"].notna().any():
            d_km = df["dist_major_shear"] / 1000.0
            df["score_distfault"] = 1.0 / (1.0 + d_km)
        else:
            df["score_distfault"] = np.nan

        # random baseline
        rng = np.random.default_rng(seed)
        df["score_random"] = rng.random(len(df))

        # distance-to-known-deposit (leaky reference)
        if positives is not None and not positives.empty:
            pu = positives.geometry.union_all()
            cents = gpd.GeoSeries(gpd.points_from_xy(df["centroid_x"], df["centroid_y"]),
                                  crs="EPSG:3067")
            dd_km = cents.distance(pu).values / 1000.0
            df["score_distdeposit"] = 1.0 / (1.0 + dd_km)
        else:
            df["score_distdeposit"] = np.nan

        out = df[["cell_id", "score_distfault", "score_random", "score_distdeposit"]]
        out.to_parquet(processed / f"baseline_scores_{gname.split('_')[-1]}.parquet", index=False)
        log.info("%s: wrote baseline scores (distfault valid=%s)",
                 gname, bool(df["score_distfault"].notna().any()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
