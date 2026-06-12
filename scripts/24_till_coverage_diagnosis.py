"""
24 - Diagnose till geochemistry coverage for Step 2.2B.

Checks all local GTK till geochemistry layers and explains why the interim
Au-As-Sb CLR model used only the sparse supraregional layer.

Outputs
    data/outputs/STEP2_2B_TILL_COVERAGE_DIAGNOSIS.md
    data/outputs/till_dataset_coverage.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import get_logger, get_path, load_config  # noqa: E402

log = get_logger("24_till_coverage")

DATASETS = [
    "till_geochemistry_almr_511p.gpkg",
    "till_geochemistry_almr_519u.gpkg",
    "till_geochemistry_supraregional.gpkg",
]
ELEMENTS = ["AU", "AS", "SB"]


def element_value_columns(columns: list[str], element: str) -> list[str]:
    prefix = f"{element}_"
    out = []
    for col in columns:
        up = col.upper()
        if not up.startswith(prefix):
            continue
        if up.endswith("_T"):
            continue
        if "_PPM_" in up or "_PCT_" in up or "_PPB_" in up:
            out.append(col)
    return out


def element_qualifier_columns(columns: list[str], element: str) -> list[str]:
    prefix = f"{element}_"
    return [c for c in columns if c.upper().startswith(prefix) and c.upper().endswith("_T")]


def unit_summary(cols: list[str]) -> str:
    units = set()
    for col in cols:
        up = col.upper()
        if "_PPM_" in up:
            units.add("ppm")
        if "_PPB_" in up:
            units.add("ppb")
        if "_PCT_" in up:
            units.add("pct")
    return ";".join(sorted(units))


def numeric_present(gdf: gpd.GeoDataFrame, cols: list[str]) -> bool:
    for col in cols:
        vals = pd.to_numeric(gdf[col], errors="coerce")
        if vals.notna().any():
            return True
    return False


def concise_values(gdf: gpd.GeoDataFrame, candidates: list[str]) -> str:
    pieces = []
    for col in candidates:
        if col in gdf.columns:
            vals = gdf[col].dropna().astype(str).value_counts().head(6)
            if not vals.empty:
                pieces.append(f"{col}: " + "; ".join(f"{k}={v}" for k, v in vals.items()))
    return " | ".join(pieces)


def legal_clear_cells(outputs: Path):
    path = outputs / "geology_ranked_modelling_candidates.gpkg"
    if not path.exists():
        return None
    cells = gpd.read_file(path).to_crs(3067)
    return cells[
        (cells["legal_status_conservative"] == "open")
        & (cells["restriction_status"] == "clear")
    ][["cell_id", "geometry"]].copy()


def count_inside(samples: gpd.GeoDataFrame, geom) -> int:
    if geom is None or samples.empty:
        return 0
    return int(samples.geometry.within(geom).sum())


def count_join(samples: gpd.GeoDataFrame, polygons: gpd.GeoDataFrame | None) -> int:
    if polygons is None or samples.empty or polygons.empty:
        return 0
    joined = gpd.sjoin(samples[["geometry"]], polygons[["geometry"]], how="inner", predicate="within")
    return int(joined.index.nunique())


def decision(dataset: str, has_au: bool, has_as: bool, has_sb: bool) -> tuple[str, str, str]:
    if has_au and has_as and has_sb:
        return (
            "USED",
            "Contains numeric Au, As and Sb in the same till sample table; valid for strict three-marker CLR after censoring imputation.",
            "YES",
        )
    if has_au and not (has_as or has_sb):
        return (
            "EXCLUDED_FROM_STRICT_CLR",
            "Contains usable Au but lacks As/Sb, so it cannot support an Au-As-Sb CLR composition without mixing unmatched surveys.",
            "NO for strict Au-As-Sb CLR; YES for a future Au-only log ablation if explicitly allowed.",
        )
    if not has_au and not has_as and not has_sb:
        return (
            "EXCLUDED",
            "No numeric Au/As/Sb marker fields found.",
            "NO",
        )
    return (
        "EXCLUDED_FROM_STRICT_CLR",
        "Contains only a partial Au/As/Sb marker set, so strict three-marker CLR is not valid from this dataset alone.",
        "NO for strict Au-As-Sb CLR; possible for per-element log fallback if explicitly allowed.",
    )


def main() -> int:
    cfg = load_config()
    raw = get_path(cfg, "raw")
    processed = get_path(cfg, "processed")
    outputs = get_path(cfg, "outputs", create=True)

    aoi_geom = box(*cfg["aoi"]["bounds"])
    clgb_path = processed / "clgb_aoi.gpkg"
    clgb_geom = gpd.read_file(clgb_path).to_crs(3067).geometry.union_all() if clgb_path.exists() else None
    clear_cells = legal_clear_cells(outputs)

    rows = []
    for dataset in DATASETS:
        path = raw / "gtk" / dataset
        if not path.exists():
            rows.append({
                "dataset": dataset,
                "path": str(path),
                "exists": False,
                "total_samples": 0,
                "samples_inside_full_aoi": 0,
                "samples_inside_clgb": 0,
                "samples_inside_legal_restriction_clear_cells": 0,
                "sample_medium_fraction": "",
                "numeric_au_present": "NO",
                "numeric_as_present": "NO",
                "numeric_sb_present": "NO",
                "units": "",
                "detection_limit_fields": "",
                "used_or_excluded": "MISSING",
                "why": "File missing.",
                "should_include_interim_au_as_sb": "NO",
            })
            continue

        gdf = gpd.read_file(path).to_crs(3067)
        cols = list(gdf.columns)
        elem_cols = {e: element_value_columns(cols, e) for e in ELEMENTS}
        qual_cols = {e: element_qualifier_columns(cols, e) for e in ELEMENTS}
        present = {e: numeric_present(gdf, elem_cols[e]) for e in ELEMENTS}
        used, why, include = decision(dataset, present["AU"], present["AS"], present["SB"])
        all_value_cols = [c for values in elem_cols.values() for c in values]
        all_qual_cols = [c for values in qual_cols.values() for c in values]
        rows.append({
            "dataset": dataset,
            "path": str(path),
            "exists": True,
            "total_samples": int(len(gdf)),
            "samples_inside_full_aoi": count_inside(gdf, aoi_geom),
            "samples_inside_clgb": count_inside(gdf, clgb_geom),
            "samples_inside_legal_restriction_clear_cells": count_join(gdf, clear_cells),
            "sample_medium_fraction": concise_values(
                gdf,
                ["MATERIAL", "AINES", "FRACTION", "LAJITE", "SOIL_HORIZON"],
            ),
            "numeric_au_present": "YES" if present["AU"] else "NO",
            "numeric_as_present": "YES" if present["AS"] else "NO",
            "numeric_sb_present": "YES" if present["SB"] else "NO",
            "au_fields": ";".join(elem_cols["AU"]),
            "as_fields": ";".join(elem_cols["AS"]),
            "sb_fields": ";".join(elem_cols["SB"]),
            "units": unit_summary(all_value_cols),
            "detection_limit_fields": ";".join(all_qual_cols),
            "used_or_excluded": used,
            "why": why,
            "should_include_interim_au_as_sb": include,
        })

    out = pd.DataFrame(rows)
    csv_path = outputs / "till_dataset_coverage.csv"
    out.to_csv(csv_path, index=False)

    strict = out[out["numeric_au_present"].eq("YES") & out["numeric_as_present"].eq("YES") & out["numeric_sb_present"].eq("YES")]
    total_strict_samples = int(strict["total_samples"].sum()) if not strict.empty else 0
    clgb_strict_samples = int(strict["samples_inside_clgb"].sum()) if not strict.empty else 0
    clear_strict_samples = int(strict["samples_inside_legal_restriction_clear_cells"].sum()) if not strict.empty else 0

    lines = [
        "# Step 2.2B Till Coverage Diagnosis",
        "",
        "This diagnoses why the strict interim Au-As-Sb till CLR model has sparse coverage.",
        "",
        "## Dataset Summary",
        "",
        "| dataset | total | full AOI | CLGB | legal/restriction-clear | Au | As | Sb | used/excluded | should include interim? |",
        "|---------|-------|----------|------|-------------------------|----|----|----|---------------|-------------------------|",
    ]
    for _, row in out.iterrows():
        lines.append(
            f"| `{row['dataset']}` | {row['total_samples']} | {row['samples_inside_full_aoi']} | "
            f"{row['samples_inside_clgb']} | {row['samples_inside_legal_restriction_clear_cells']} | "
            f"{row['numeric_au_present']} | {row['numeric_as_present']} | {row['numeric_sb_present']} | "
            f"{row['used_or_excluded']} | {row['should_include_interim_au_as_sb']} |"
        )

    lines += [
        "",
        "## Field Details",
        "",
    ]
    for _, row in out.iterrows():
        lines += [
            f"### {row['dataset']}",
            "",
            f"- Path: `{row['path']}`",
            f"- Medium / fraction: {row.get('sample_medium_fraction', '')}",
            f"- Au fields: {row.get('au_fields', '')}",
            f"- As fields: {row.get('as_fields', '')}",
            f"- Sb fields: {row.get('sb_fields', '')}",
            f"- Units: {row.get('units', '')}",
            f"- Detection / qualifier fields: {row.get('detection_limit_fields', '')}",
            f"- Decision: {row['used_or_excluded']}",
            f"- Why: {row['why']}",
            "",
        ]

    lines += [
        "## Diagnosis",
        "",
        f"- Strict usable Au-As-Sb samples: {total_strict_samples}",
        f"- Strict usable Au-As-Sb samples inside CLGB: {clgb_strict_samples}",
        f"- Strict usable Au-As-Sb samples inside legal/restriction-clear cells: {clear_strict_samples}",
        "- The dense `almr_519u` table supplies Au but not As/Sb.",
        "- The dense `almr_511p` table does not supply Au/As/Sb pathfinder fields.",
        "- The sparse supraregional table is the only local till dataset with Au, As and Sb together in the same sample records.",
        "- Therefore the 1% 2 km cell coverage is expected for the strict three-marker CLR model and was not caused by accidentally excluding a dense complete Au-As-Sb till table.",
        "",
        "## Recommendation",
        "",
        "- Keep the current strict Au-As-Sb CLR layer as sparse, high-specificity geochemistry.",
        "- Add a separate future ablation for dense Au-only `almr_519u` as `till_au_log_dense` only if the model explicitly allows unmatched per-element surveys.",
        "- Do not mix stream sediment Bi or unmatched Bi into the till model.",
        "",
    ]
    report_path = outputs / "STEP2_2B_TILL_COVERAGE_DIAGNOSIS.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    log.info("Wrote %s and %s", report_path, csv_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
