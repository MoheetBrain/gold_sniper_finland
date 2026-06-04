"""
02c — Classify Tukes rights by legal status, and build status-aware legal masks.

WHY THIS EXISTS  (forensic finding)
    Script 02 treats EVERY Tukes polygon as "taken". But the Tukes shapefiles carry
    a `status` attribute with three distinct legal meanings:

        voimassa  = in force / valid  -> an ACTIVE granted right
        hakemus   = application       -> PENDING, not yet granted
        karenssi  = cooling-off period-> the underlying right has LAPSED/expired and
                                         the area sits in a statutory waiting period

    Lumping these together massively over-counts unavailable ground: ~46% of the
    polygons are pending or cooling-off, not active rights. This script reads the
    real `status` field (it does NOT invent status) and produces two masks that
    bracket the truth:

        strict_active_only : excludes ONLY active (voimassa) rights   [most open]
        conservative       : excludes active + pending + cooling-off + uncertain
                             (i.e. anything not clearly free)          [most cautious]

    `conservative` reproduces script 02's behaviour; `strict_active_only` shows how
    much ground opens up if you trust the status field and only fear active rights.
    The swing categories (pending, cooling-off) MUST be manually verified before any
    reservation decision — see the printed comparison.

OUTPUTS
    data/processed/tukes_rights_classified.gpkg      (all rights + legal_class)
    data/outputs/tukes_status_summary.csv            (counts/area per layer x class)
    data/outputs/open_cells_conservative.gpkg
    data/outputs/open_cells_strict_active_only.gpkg
    data/outputs/cell_legal_status_conservative.csv
    data/outputs/cell_legal_status_strict_active_only.csv
    data/outputs/DIAGNOSTIC_STATUS_COMPARISON.md     (the count comparison)
"""
from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (PROJECT_CRS, get_logger, get_path,  # noqa: E402
                     import_script, load_config)

log = get_logger("02c_classify")

# Reuse the tested loaders/maths from script 02 (no duplication, no drift).
_m02 = import_script("02_mask_taken_areas.py", "m02")

# Raw Tukes status value -> our legal class. The Tukes `status` field is lowercase.
STATUS_TO_CLASS = {
    "voimassa": "active",       # in force / granted
    "hakemus": "pending",       # application
    "karenssi": "cooling_off",  # post-lapse statutory waiting period
}

# Attribute columns we try to carry through (names differ slightly per layer).
# (target_name -> list of possible source column names)
ATTR_ALIASES = {
    "right_id": ["Aluetunnus", "KaivNro"],
    "area_name": ["Alueennimi", "Aluenimi"],
    "holder": ["Hakija", "Haltijanim"],
    "commodities": ["Kivennäise"],
    "received_date": ["Saapumispv"],
    "decision_date": ["Päätöspvm"],
    "valid_until": ["Voimassaol"],
    "lapse_date": ["Raukeamisp"],
    "status_text": ["Aluestatus"],
}


def _pick(row_cols, options):
    for o in options:
        if o in row_cols:
            return o
    return None


def classify_status(raw) -> str:
    """Map a raw Tukes status value to active/pending/cooling_off/uncertain."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return "uncertain"
    return STATUS_TO_CLASS.get(str(raw).strip().lower(), "uncertain")


def load_classified_rights(cfg: dict) -> gpd.GeoDataFrame:
    """
    Load every Tukes shapefile, clean geometries, reproject, and attach a
    `legal_class` derived from the real `status` attribute.

    Reuses script 02's find_vector_files + per-file geometry cleaning, then keeps
    the status + provenance attributes (which script 02 discards).
    """
    crs = cfg["project"].get("crs", PROJECT_CRS)
    extract_dir = get_path(cfg, "tukes_extracted")
    files = _m02.find_vector_files(extract_dir)
    log.info("Classifying %d Tukes vector file(s).", len(files))

    parts = []
    for path in files:
        try:
            gdf = gpd.read_file(path)
        except Exception as exc:  # noqa: BLE001
            log.error("Could not read %s: %s", path.name, exc)
            continue
        if gdf.empty:
            continue

        # CRS + geometry cleaning identical in spirit to script 02.
        if gdf.crs is None:
            log.warning("%s has NO CRS — assuming %s", path.name, crs)
            gdf = gdf.set_crs(crs, allow_override=True)
        if str(gdf.crs) != crs:
            gdf = gdf.to_crs(crs)
        gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
        inv = ~gdf.geometry.is_valid
        if inv.any():
            gdf.loc[inv, gdf.geometry.name] = gdf.loc[inv, gdf.geometry.name].make_valid()
        gdf = gdf[gdf.geometry.geom_type.isin(_m02.POLYGON_TYPES)].copy()
        if gdf.empty:
            continue

        label = _m02._source_label(path, extract_dir)
        cols = set(gdf.columns)
        out = gpd.GeoDataFrame(geometry=gdf.geometry.values, crs=crs)
        out["source_layer"] = label
        out["source_file"] = path.name

        # Status: the lowercase `status` column is the machine-readable field.
        status_col = "status" if "status" in cols else _pick(cols, ["Aluestatus"])
        raw_status = gdf[status_col].values if status_col else [None] * len(gdf)
        out["status_raw"] = [str(s).lower() if s is not None else None for s in raw_status]
        out["legal_class"] = [classify_status(s) for s in raw_status]

        # Carry through useful attributes where present.
        for target, opts in ATTR_ALIASES.items():
            src = _pick(cols, opts)
            out[target] = gdf[src].astype(str).values if src else None

        parts.append(out)

    if not parts:
        return gpd.GeoDataFrame(
            {"source_layer": [], "legal_class": []}, geometry=[], crs=crs)
    merged = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=crs)
    return merged


def status_summary(rights: gpd.GeoDataFrame) -> pd.DataFrame:
    """Per (layer, legal_class) feature counts + total area km²."""
    df = rights.copy()
    df["area_km2"] = df.geometry.area / 1e6
    summ = (df.groupby(["source_layer", "legal_class"])
              .agg(n_features=("legal_class", "size"),
                   area_km2=("area_km2", "sum"))
              .reset_index()
              .sort_values(["source_layer", "legal_class"]))
    summ["area_km2"] = summ["area_km2"].round(2)
    return summ


def biggest_difference_layer(rights: gpd.GeoDataFrame, grid: gpd.GeoDataFrame) -> pd.DataFrame:
    """
    For each layer, how many grid cells are touched ONLY by its non-active
    (pending/cooling_off/uncertain) polygons? The layer touching the most cells is
    the biggest driver of the conservative-vs-strict difference.
    """
    non_active = rights[rights["legal_class"] != "active"]
    rows = []
    for layer, sub in non_active.groupby("source_layer"):
        inter = gpd.overlay(grid[["cell_id", "geometry"]],
                            sub[["geometry"]].copy(), how="intersection",
                            keep_geom_type=True)
        inter = inter[~inter.geometry.is_empty]
        rows.append({"source_layer": layer,
                     "non_active_polygons": len(sub),
                     "grid_cells_touched": inter["cell_id"].nunique()})
    out = pd.DataFrame(rows).sort_values("grid_cells_touched", ascending=False)
    return out


def _write_mask_outputs(grid, rights_subset, cfg, tag, outputs_dir):
    """Run script-02 maths for a rights subset; write open_cells + full csv. Returns status df."""
    status = _m02.compute_cell_status(grid, rights_subset, cfg)
    out_cols = ["cell_id", "area_km2", "centroid_x", "centroid_y",
                "taken_area_m2", "taken_overlap_pct", "taken_layer_count",
                "source_layers", "legal_status", "is_clean_open", "geometry"]
    status = status[out_cols]

    open_gdf = status[status["legal_status"] == "open"]
    gpkg = outputs_dir / f"open_cells_{tag}.gpkg"
    if open_gdf.empty:
        gpd.GeoDataFrame(open_gdf, crs=status.crs).to_file(
            gpkg, layer=f"open_cells_{tag}", driver="GPKG")
    else:
        open_gdf.to_file(gpkg, layer=f"open_cells_{tag}", driver="GPKG")
    csv = outputs_dir / f"cell_legal_status_{tag}.csv"
    status.drop(columns="geometry").to_csv(csv, index=False)
    log.info("[%s] wrote %s (%d open) and %s", tag, gpkg.name, len(open_gdf), csv.name)
    return status


def main() -> int:
    cfg = load_config()
    processed = get_path(cfg, "processed", create=True)
    outputs = get_path(cfg, "outputs", create=True)

    grid_path = processed / "aoi_grid.gpkg"
    if not grid_path.exists():
        log.error("AOI grid missing: %s — run 01 first.", grid_path)
        return 2
    grid = gpd.read_file(grid_path, layer="aoi_grid")

    rights = load_classified_rights(cfg)
    if rights.empty:
        log.error("No classified rights loaded — cannot build status masks.")
        return 2

    cls_counts = rights["legal_class"].value_counts().to_dict()
    log.info("Classified %d rights: %s", len(rights), cls_counts)

    # Write classified rights + summary.
    rights.to_file(processed / "tukes_rights_classified.gpkg",
                   layer="tukes_rights_classified", driver="GPKG")
    summ = status_summary(rights)
    summ.to_csv(outputs / "tukes_status_summary.csv", index=False)
    log.info("Wrote tukes_rights_classified.gpkg and tukes_status_summary.csv")

    # --- Two masks ---
    # conservative: exclude everything that isn't clearly free (= all known statuses).
    conservative_rights = rights  # every polygon counts as taken
    # strict_active_only: exclude only active (voimassa).
    strict_rights = rights[rights["legal_class"] == "active"].copy()
    log.info("conservative excludes %d polygons; strict-active excludes %d polygons.",
             len(conservative_rights), len(strict_rights))

    cons = _write_mask_outputs(grid, conservative_rights, cfg, "conservative", outputs)
    strict = _write_mask_outputs(grid, strict_rights, cfg, "strict_active_only", outputs)

    # --- Comparison ---
    def stats(df):
        vc = df["legal_status"].value_counts().to_dict()
        return {"open": vc.get("open", 0), "partly_taken": vc.get("partly_taken", 0),
                "taken": vc.get("taken", 0), "clean_open": int(df["is_clean_open"].sum())}

    cs, ss = stats(cons), stats(strict)
    flipped = int((cons.set_index("cell_id")["legal_status"]
                   != strict.set_index("cell_id")["legal_status"]).sum())
    diff_layers = biggest_difference_layer(rights, grid)

    lines = ["# Diagnostic — Conservative vs Strict-active legal masks", "",
             "Two status-aware masks bracket the truth. `status` is read from the Tukes",
             "attribute table (voimassa=active, hakemus=pending, karenssi=cooling-off).",
             "", "## Cell counts", "",
             "| mask | clean_open (0%) | open (<=1%) | partly_taken | taken |",
             "|------|-----------------|-------------|--------------|-------|",
             f"| **conservative** (exclude active+pending+cooling-off) | {cs['clean_open']} | {cs['open']} | {cs['partly_taken']} | {cs['taken']} |",
             f"| **strict_active_only** (exclude active only) | {ss['clean_open']} | {ss['open']} | {ss['partly_taken']} | {ss['taken']} |",
             "",
             f"- Cells that change status between the two masks: **{flipped}**",
             f"- Extra clean-open ground under strict vs conservative: **{ss['clean_open'] - cs['clean_open']}** cells",
             "", "## Which layer drives the difference",
             "Grid cells touched ONLY by each layer's non-active (pending/cooling-off) polygons:",
             "",
             "| source_layer | non_active_polygons | grid_cells_touched |",
             "|--------------|---------------------|--------------------|"]
    for _, r in diff_layers.iterrows():
        lines.append(f"| {r['source_layer']} | {r['non_active_polygons']} | {r['grid_cells_touched']} |")
    lines += ["", "## Interpretation",
              "- `conservative` == the original script-02 mask (every cadastre footprint excluded).",
              "- `strict_active_only` trusts the status field and frees pending + cooling-off ground.",
              "- The swing categories (pending applications, cooling-off claims) are NOT a final",
              "  legal verdict. Verify them in the live Tukes register before any reservation.", ""]
    (outputs / "DIAGNOSTIC_STATUS_COMPARISON.md").write_text("\n".join(lines), encoding="utf-8")
    log.info("Wrote DIAGNOSTIC_STATUS_COMPARISON.md")

    log.info("SUMMARY  conservative clean_open=%d | strict clean_open=%d | flipped=%d",
             cs["clean_open"], ss["clean_open"], flipped)
    if len(diff_layers):
        top = diff_layers.iloc[0]
        log.info("Biggest difference driver: %s (touches %d cells via non-active polygons)",
                 top["source_layer"], top["grid_cells_touched"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
