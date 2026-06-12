"""
19 - Build interim Au-As-Sb till geochemistry features.

Rules for this interim CLGB run:
    - Use till geochemistry only.
    - Use Au, As and Sb.
    - Do not substitute stream-sediment Bi; Bi remains null.
    - Create raw and 500 m / 1 km / 2 km up-ice ablation scenarios.

Output
    data/processed/till_features_au_as_sb_2km.parquet
    data/outputs/INTERIM_TILL_AU_AS_SB_REPORT.md
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from shapely.affinity import translate

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import get_logger, get_path, load_config  # noqa: E402

log = get_logger("19_till_au_as_sb")

ELEMENT_COLS = {
    "au": "AU_PPM_519U",
    "as": "AS_PPM_511P",
    "sb": "SB_PPM_511P",
}
SHIFT_LABELS = {0: "raw", 500: "shift_500m", 1000: "shift_1km", 2000: "shift_2km"}


def angular_difference(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def line_bearing_deg(geom) -> float | None:
    if geom.is_empty:
        return None
    coords = list(geom.coords) if geom.geom_type == "LineString" else list(list(geom.geoms)[0].coords)
    if len(coords) < 2:
        return None
    x0, y0 = coords[0][:2]
    x1, y1 = coords[-1][:2]
    return (math.degrees(math.atan2(x1 - x0, y1 - y0)) + 360.0) % 360.0


def up_ice_offset(distance_m: float, flow_to_azimuth_deg: float) -> tuple[float, float]:
    up_az = (flow_to_azimuth_deg + 180.0) % 360.0
    rad = np.radians(up_az)
    return distance_m * np.sin(rad), distance_m * np.cos(rad)


def infer_half_detection(values: pd.Series) -> float:
    pos = pd.to_numeric(values, errors="coerce")
    pos = pos[pos > 0]
    if pos.empty:
        return 1e-9
    return float(pos.min()) / 2.0


def build_transform(samples: gpd.GeoDataFrame):
    work = samples.copy()
    notes = []
    for element, col in ELEMENT_COLS.items():
        raw = pd.to_numeric(work[col], errors="coerce")
        half_dl = infer_half_detection(raw)
        censored = raw.isna() | (raw <= 0)
        work[f"{element}_value"] = raw.mask(censored, half_dl)
        notes.append(f"{element.upper()}: {int(censored.sum())} values imputed to half min positive ({half_dl:g})")

    value_cols = [f"{e}_value" for e in ELEMENT_COLS]
    if work[value_cols].notna().all(axis=1).all() and (work[value_cols] > 0).all().all():
        logs = np.log(work[value_cols].astype(float))
        gm = logs.mean(axis=1)
        for element in ELEMENT_COLS:
            work[f"till_{element}_clr_sample"] = logs[f"{element}_value"] - gm
        method = "CLR"
        feature_suffix = "clr"
        reason = "Au/As/Sb are positive after half-detection-limit imputation."
    else:
        for element in ELEMENT_COLS:
            work[f"till_{element}_log_sample"] = np.log10(work[f"{element}_value"].clip(lower=1e-12))
        method = "LOG"
        feature_suffix = "log"
        reason = "CLR unsafe because complete positive Au/As/Sb rows were not available."
    return work, method, feature_suffix, reason, notes


def attach_flow_directions(samples: gpd.GeoDataFrame, raw: Path, default_flow_to: float):
    out = samples.copy()
    out["flow_to_azimuth_deg"] = float(default_flow_to)
    out["flow_source"] = "config_default"

    striae_path = raw / "gtk/glacial_striae.gpkg"
    if striae_path.exists():
        striae = gpd.read_file(striae_path).to_crs(out.crs)
        if "JAATIKON_TULOSUUNTA" in striae.columns and not striae.empty:
            dirs = pd.to_numeric(striae["JAATIKON_TULOSUUNTA"], errors="coerce")
            valid = dirs.notna()
            striae = striae[valid].copy()
            dirs = dirs[valid].astype(float).to_numpy() % 360.0
            if len(striae):
                tree = cKDTree(np.c_[striae.geometry.x, striae.geometry.y])
                dist, idx = tree.query(np.c_[out.geometry.x, out.geometry.y], k=1)
                use = dist <= 25000.0
                out.loc[use, "flow_to_azimuth_deg"] = dirs[idx[use]]
                out.loc[use, "flow_source"] = "nearest_glacial_stria_25km"

    line_path = raw / "gtk/glacial_lineations.gpkg"
    need = out["flow_source"].eq("config_default")
    if line_path.exists() and need.any():
        lines = gpd.read_file(line_path).to_crs(out.crs)
        bearings = []
        geoms = []
        for geom in lines.geometry:
            b = line_bearing_deg(geom)
            if b is None:
                continue
            b2 = (b + 180.0) % 360.0
            bearings.append(b if angular_difference(b, default_flow_to) <= angular_difference(b2, default_flow_to) else b2)
            geoms.append(geom)
        if geoms:
            mids = np.array([[g.interpolate(0.5, normalized=True).x, g.interpolate(0.5, normalized=True).y]
                             for g in geoms])
            tree = cKDTree(mids)
            sample_xy = np.c_[out.loc[need].geometry.x, out.loc[need].geometry.y]
            dist, idx = tree.query(sample_xy, k=1)
            use_local = dist <= 25000.0
            target_idx = out.index[need][use_local]
            out.loc[target_idx, "flow_to_azimuth_deg"] = np.asarray(bearings)[idx[use_local]]
            out.loc[target_idx, "flow_source"] = "nearest_glacial_lineation_25km"
    return out


def aggregate_scenario(samples: gpd.GeoDataFrame, grid: gpd.GeoDataFrame, shift_m: int,
                       feature_suffix: str) -> pd.DataFrame:
    shifted = samples.copy()
    if shift_m:
        shifted.geometry = [
            translate(geom, xoff=up_ice_offset(shift_m, az)[0],
                      yoff=up_ice_offset(shift_m, az)[1])
            for geom, az in zip(shifted.geometry, shifted["flow_to_azimuth_deg"])
        ]
    joined = gpd.sjoin(
        shifted,
        grid[["cell_id", "geometry"]],
        how="inner",
        predicate="intersects",
    )
    sample_cols = [f"till_{e}_{feature_suffix}_sample" for e in ELEMENT_COLS]
    grouped = joined.groupby("cell_id")[sample_cols].mean()
    grouped.columns = [c.replace("_sample", f"_{SHIFT_LABELS[shift_m]}") for c in grouped.columns]
    grouped[f"till_sample_count_{SHIFT_LABELS[shift_m]}"] = joined.groupby("cell_id").size()
    return grouped.reset_index()


def main() -> int:
    cfg = load_config()
    raw = get_path(cfg, "raw")
    processed = get_path(cfg, "processed", create=True)
    outputs = get_path(cfg, "outputs", create=True)

    grid = gpd.read_file(outputs / cfg["step2"]["primary_grid"]).to_crs(3067)
    supra_path = raw / "gtk/till_geochemistry_supraregional.gpkg"
    if not supra_path.exists():
        raise FileNotFoundError(f"Till supraregional file missing: {supra_path}")
    samples = gpd.read_file(supra_path).to_crs(3067)

    missing = [col for col in ELEMENT_COLS.values() if col not in samples.columns]
    if missing:
        raise KeyError(f"Required till Au/As/Sb fields missing from {supra_path}: {missing}")

    samples, method, suffix, reason, impute_notes = build_transform(samples)
    default_flow = float(cfg["till_shift"].get("ice_flow_to_azimuth_deg", 135.0))
    samples = attach_flow_directions(samples, raw, default_flow)

    out = pd.DataFrame({"cell_id": grid["cell_id"].to_numpy()})
    scenario_tables = []
    for shift_m in [0, 500, 1000, 2000]:
        scenario_tables.append(aggregate_scenario(samples, grid, shift_m, suffix))
    for table in scenario_tables:
        out = out.merge(table, on="cell_id", how="left")

    for element in ELEMENT_COLS:
        out[f"till_{element}_{suffix}"] = out[f"till_{element}_{suffix}_raw"]
    out["till_bi_clr"] = np.nan
    out["till_bi_log"] = np.nan
    out["till_transform"] = method
    out["till_source"] = "GTK till_geochemistry_supraregional.gpkg; Au/As/Sb only"
    out.to_parquet(processed / "till_features_au_as_sb_2km.parquet", index=False)

    flow_counts = samples["flow_source"].value_counts().to_dict()
    coverage = {
        c: float(out[c].notna().mean())
        for c in [f"till_{e}_{suffix}" for e in ELEMENT_COLS]
    }
    lines = [
        "# Interim Till Au-As-Sb Report",
        "",
        f"Input till file: `{supra_path}`",
        "",
        "## Markers Used",
        "",
        f"- Au: YES (`{ELEMENT_COLS['au']}`)",
        f"- As: YES (`{ELEMENT_COLS['as']}`)",
        f"- Sb: YES (`{ELEMENT_COLS['sb']}`)",
        "- Bi: NULL/optional. No till Bi field was used; stream-sediment Bi was not substituted.",
        "",
        "## Transform",
        "",
        f"- Transform used: {method}",
        f"- Reason: {reason}",
        *[f"- {note}" for note in impute_notes],
        "",
        "## Up-Ice Ablation",
        "",
        "- Scenario columns created for raw, 500 m, 1 km and 2 km up-ice shifts.",
        "- Glacial striae were used within 25 km where available; otherwise nearby lineation "
        "orientation was used; otherwise the config default was used.",
        f"- Flow direction sources among samples: {flow_counts}",
        "- No single shift is treated as correct; these are ablation scenarios.",
        "",
        "## Output Coverage",
        "",
        f"- Till samples processed: {len(samples)}",
        f"- 2 km cells: {len(out)}",
        *[f"- {k}: {v:.1%} non-null cells" for k, v in coverage.items()],
        "",
        "## Limitations",
        "",
        "- Au/As/Sb CLR uses the sparse supraregional till table because it contains all "
        "three interim markers in the same till samples.",
        "- The denser Au-only till layer was not mixed into CLR because matching As/Sb values "
        "are not present for those samples.",
        "- Striae direction semantics and lineation orientation are treated as provisional; "
        "validation must compare raw and shifted scenarios rather than trusting one shift.",
        "",
    ]
    (outputs / "INTERIM_TILL_AU_AS_SB_REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    log.info("Wrote till_features_au_as_sb_2km.parquet using %s", method)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
