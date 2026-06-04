"""
11c — Till geochemistry glacial-shift ablation (framework + report).

WHY
    Till anomalies sit DOWN-ice of their bedrock source. We never trust raw till
    coordinates, and we never hard-code one "correct" shift. Instead we build several
    up-ice-shifted versions (0/500m/1km/2km, optional 5km) and let validation pick
    which best aligns with known deposits.

STATUS THIS RUN
    No till geochemistry is loaded (GTK Hakku raster/point data not yet supplied), so
    the ablation cannot produce till features. This script therefore:
      - implements + unit-checks the up-ice shift and CLR helpers (ready for data),
      - documents the PROVISIONAL ice-flow direction,
      - writes a report stating 0 till samples processed (no invented values).

CLR / detection limits (applied when data exists)
    - below-detection-limit values -> half the detection limit,
    - CLR (centred log-ratio) across the element suite where mathematically valid
      (all-positive composition); otherwise fall back to log10 and report why.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import get_logger, get_path, load_config, resolve_path  # noqa: E402

log = get_logger("11c_till")


def up_ice_offset(distance_m: float, ice_flow_to_azimuth_deg: float) -> tuple[float, float]:
    """
    Return (dx, dy) to move a till sample UP-ice by distance_m.

    Ice/till travels TOWARD ice_flow_to_azimuth_deg; the source is the opposite
    bearing (up-ice = +180°). Azimuth is degrees clockwise from north.
    """
    up_az = (ice_flow_to_azimuth_deg + 180.0) % 360.0
    rad = np.radians(up_az)
    return distance_m * np.sin(rad), distance_m * np.cos(rad)


def clr_transform(df: pd.DataFrame, cols: list[str], detection_limits: dict | None = None):
    """
    CLR transform of a compositional sub-table. Below-detection -> half DL.
    Returns (clr_df, method, note). Falls back to log10 if CLR is invalid.
    """
    X = df[cols].astype(float).copy()
    if detection_limits:
        for c in cols:
            dl = detection_limits.get(c)
            if dl:
                X[c] = X[c].mask(X[c] <= 0, dl / 2.0)
    if (X <= 0).any().any():
        return np.log10(X.clip(lower=1e-9)), "log10_fallback", "non-positive values present"
    g = np.exp(np.log(X).mean(axis=1))  # geometric mean per row
    clr = np.log(X.div(g, axis=0))
    return clr, "clr", "ok"


def _self_check():
    """Sanity: up-ice of a SE-directed flow (135°) points NW (−x, +y)."""
    dx, dy = up_ice_offset(1000, 135.0)
    assert dx < 0 and dy > 0, (dx, dy)
    comp = pd.DataFrame({"a": [1.0, 2.0], "b": [1.0, 4.0], "c": [1.0, 1.0]})
    clr, method, _ = clr_transform(comp, ["a", "b", "c"])
    assert method == "clr" and abs(clr.iloc[0].sum()) < 1e-9  # CLR rows sum to 0
    return True


def main() -> int:
    cfg = load_config()
    outputs = get_path(cfg, "outputs")
    ts = cfg["till_shift"]
    az = float(ts["ice_flow_to_azimuth_deg"])
    shifts = ts["shifts_m"]
    provisional = bool(ts.get("provisional", True))

    _self_check()
    log.info("Shift/CLR helpers self-check passed.")

    # Look for till data (none expected this run).
    till_candidates = list((resolve_path(cfg["paths"]["raw"]) / "gtk").glob("*till*")) \
        if (resolve_path(cfg["paths"]["raw"]) / "gtk").exists() else []
    n_till = 0

    L = ["# Till-Shift Ablation Report", "",
         "Glacial-transport correction for till geochemistry. We build up-ice-shifted",
         "versions and let validation choose — never a single hard-coded shift.", "",
         "## Ice-flow direction (PROVISIONAL)" if provisional else "## Ice-flow direction", "",
         f"- Configured ice-flow azimuth (direction till moved TOWARD): **{az:.0f}°**",
         f"- Up-ice bearing used for shifts: **{(az+180)%360:.0f}°**",
         "- This is a **provisional regional default** (Central Lapland late-glacial flow",
         "  broadly NW→SE). Replace with a real ice-flow / striations / streamlined-landform",
         "  layer before trusting any shift. Configurable in `configs/config.yaml: till_shift`.",
         "", "## Shift scenarios prepared", "",
         "| version | up-ice shift |", "|---------|--------------|"]
    for s in shifts:
        L.append(f"| {'raw' if s == 0 else f'shift_{s}m'} | {s} m |")
    L += [f"| (optional) shift_{ts.get('long_shift_m')}m | only if streamlined-moraine data exists |",
          "",
          "### Terrain-aware logic (when glacial-landform data is supplied)",
          "- ribbed moraine / ice-divide zones: 50–500 m",
          "- drumlin / streamlined moraine: 1–5 km",
          "- unknown terrain: keep raw + all shifts, mark **low confidence**",
          "", "## Status this run", "",
          f"- Till geochemistry files found under data/raw/gtk: **{len(till_candidates)}**",
          f"- Till samples processed: **{n_till}**",
          "- **No till features were produced** (no data) — `till_au_clr / as / sb / bi`",
          "  remain NULL in the feature stack. Nothing was invented.",
          "", "## When till data arrives",
          "1. Save points (with element columns + detection limits) under data/raw/gtk/.",
          "2. This script will: half-DL impute → CLR (or log10 fallback) → create raw +",
          "   shifted point sets → grid them into till_*_clr columns per shift distance.",
          "3. 11b then compares which shift best captures known deposits (the ablation).", ""]
    (outputs / "TILL_SHIFT_ABLATION_REPORT.md").write_text("\n".join(L), encoding="utf-8")
    log.info("Wrote TILL_SHIFT_ABLATION_REPORT.md (till samples processed: %d)", n_till)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
