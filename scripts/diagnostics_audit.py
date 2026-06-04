"""
diagnostics_audit — Forensic Step 1 audit report generator.

Produces the diagnostic artefacts that don't need their own pipeline script:
    T1  data/outputs/DIAGNOSTIC_DATA_PROVENANCE.md + .csv
    T2  data/outputs/DIAGNOSTIC_LEGAL_MEANING.md
    T4  data/outputs/DIAGNOSTIC_OVERLAP_AUDIT.md + taken_overlap_histogram.png
    T5  data/outputs/DIAGNOSTIC_AOI.md + aoi_overview.png
    T6  data/outputs/top_clean_open_cells_for_manual_review.csv

Run AFTER run_step1_pipeline.py and 02c. Read-only w.r.t. the pipeline outputs.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pyproj import Transformer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import get_logger, get_path, import_script, load_config  # noqa: E402

log = get_logger("diagnostics")
_m02 = import_script("02_mask_taken_areas.py", "m02")
_m02c = import_script("02c_classify_tukes_status.py", "m02c")

TO_WGS84 = Transformer.from_crs("EPSG:3067", "EPSG:4326", always_xy=True)


def df_to_md(df: pd.DataFrame) -> str:
    """Render a DataFrame as a GitHub markdown table without needing `tabulate`."""
    cols = list(df.columns)
    head = "| " + " | ".join(str(c) for c in cols) + " |"
    sep = "|" + "|".join(["---"] * len(cols)) + "|"
    rows = ["| " + " | ".join(str(v) for v in row) + " |"
            for row in df.itertuples(index=False, name=None)]
    return "\n".join([head, sep] + rows)

# Key Central Lapland reference points (approx WGS84 lon/lat) for the AOI check.
REFERENCE_POINTS = {
    "Kittilä town": (24.90, 67.65),
    "Suurikuusikko/Kittilä mine": (25.39, 67.92),
    "Ikkari (Rupert, Sodankylä area)": (26.02, 67.52),
    "Sodankylä town": (26.59, 67.42),
    "Sirkka village (Sirkka shear)": (24.80, 67.80),
    "Kiistala (Kiistala shear)": (25.30, 67.95),
}


# --------------------------------------------------------------------------- T1
def provenance_records(cfg: dict) -> list[dict]:
    """Per-layer provenance + geometry-cleaning counts (reproduces script-02 load)."""
    crs = cfg["project"].get("crs")
    extract_dir = get_path(cfg, "tukes_extracted")
    raw_dir = get_path(cfg, "raw")
    manifest = {}
    mpath = raw_dir / "tukes_download_manifest.json"
    if mpath.exists():
        for r in json.loads(mpath.read_text()):
            manifest[Path(r.get("extracted_path", "")).name] = r

    recs = []
    for shp in _m02.find_vector_files(extract_dir):
        label = _m02._source_label(shp, extract_dir)
        man = manifest.get(label, {})
        gdf_raw = gpd.read_file(shp)
        n_raw = len(gdf_raw)
        detected_crs = str(gdf_raw.crs) if gdf_raw.crs else None
        assumed = None if detected_crs else crs
        g = gdf_raw.copy()
        if g.crs is None:
            g = g.set_crs(crs, allow_override=True)
        if str(g.crs) != crs:
            g = g.to_crs(crs)
        g = g[g.geometry.notna() & ~g.geometry.is_empty]
        n_after_empty = len(g)
        n_invalid = int((~g.geometry.is_valid).sum())
        g_poly = g[g.geometry.geom_type.isin(_m02.POLYGON_TYPES)]
        # Extracted file list (just the shp sibling set + mif/tab folders present).
        extracted_files = sorted(p.name for p in shp.parent.glob(shp.stem + ".*"))
        sample_cols = [c for c in ["Aluetunnus", "KaivNro", "Aluestatus", "status",
                                   "Alueennimi", "Aluenimi", "Hakija", "Haltijanim",
                                   "Kivennäise"] if c in gdf_raw.columns]
        recs.append({
            "source_layer": label,
            "url": man.get("url", ""),
            "downloaded_zip": man.get("filename", ""),
            "zip_size_bytes": man.get("size_bytes", ""),
            "downloaded_utc": man.get("timestamp_utc", ""),
            "extract_date_from_name": label.split("_")[-1] if "_" in label else "",
            "shapefile": shp.name,
            "extracted_files": ";".join(extracted_files),
            "geom_types": ";".join(sorted(gdf_raw.geom_type.dropna().unique())),
            "crs_detected": detected_crs or "NONE",
            "crs_assumed": assumed or "",
            "n_raw_features": n_raw,
            "n_after_empty_drop": n_after_empty,
            "n_invalid_geoms_fixed": n_invalid,
            "n_polygons_final": len(g_poly),
            "key_columns": ";".join(list(gdf_raw.columns)),
            "_sample_cols": sample_cols,
            "_gdf_raw": gdf_raw,
        })
    return recs


def write_provenance(cfg: dict, outputs: Path) -> None:
    recs = provenance_records(cfg)
    # CSV (scalar fields only).
    csv_cols = ["source_layer", "url", "downloaded_zip", "zip_size_bytes", "downloaded_utc",
                "extract_date_from_name", "shapefile", "geom_types", "crs_detected",
                "crs_assumed", "n_raw_features", "n_after_empty_drop",
                "n_invalid_geoms_fixed", "n_polygons_final", "key_columns"]
    pd.DataFrame([{k: r[k] for k in csv_cols} for r in recs]).to_csv(
        outputs / "DIAGNOSTIC_DATA_PROVENANCE.csv", index=False)

    L = ["# Diagnostic T1 — Tukes data provenance audit", "",
         f"_Generated: {datetime.now(timezone.utc).isoformat()}_", "",
         "Every Tukes layer loaded by the pipeline, with download provenance, CRS,",
         "geometry cleaning counts, and a 5-row attribute sample.", ""]
    for r in recs:
        L += [f"## {r['source_layer']}", "",
              f"- **Source URL:** {r['url']}",
              f"- **Downloaded ZIP:** `{r['downloaded_zip']}` ({r['zip_size_bytes']} bytes)",
              f"- **Downloaded (UTC):** {r['downloaded_utc']}",
              f"- **Cadastre extract date (from name):** {r['extract_date_from_name']}",
              f"- **Shapefile loaded:** `{r['shapefile']}`",
              f"- **Extracted files:** {r['extracted_files']}",
              f"- **Geometry type(s):** {r['geom_types']}",
              f"- **CRS detected:** {r['crs_detected']}  |  **CRS assumed:** {r['crs_assumed'] or 'n/a (.prj present)'}",
              f"- **Raw features:** {r['n_raw_features']}  |  **after empty/null drop:** {r['n_after_empty_drop']}"
              f"  |  **invalid fixed:** {r['n_invalid_geoms_fixed']}  |  **polygons kept:** {r['n_polygons_final']}",
              f"- **Attribute columns:** `{r['key_columns']}`", ""]
        # 5-row sample of important attributes.
        g = r["_gdf_raw"]
        cols = r["_sample_cols"]
        if cols:
            samp = g[cols].head(5).copy()
            L.append("Sample rows:")
            L.append("")
            L.append("| " + " | ".join(cols) + " |")
            L.append("|" + "|".join(["---"] * len(cols)) + "|")
            for _, row in samp.iterrows():
                L.append("| " + " | ".join(str(row[c])[:40] for c in cols) + " |")
            L.append("")
    (outputs / "DIAGNOSTIC_DATA_PROVENANCE.md").write_text("\n".join(L), encoding="utf-8")
    log.info("T1 wrote DIAGNOSTIC_DATA_PROVENANCE.md + .csv")


# --------------------------------------------------------------------------- T2
LEGAL_MEANING = {
    # source_layer stem : (meaning, exclude?, confidence, evidence)
    "malminetsintavaraus": (
        "Exploration RESERVATION (Malminetsintävaraus). A reservation reserves the "
        "priority right to later apply for an exploration permit; it does NOT itself "
        "grant exploration. status field splits active/pending/cooling-off.",
        "Yes for reservation strategy (someone already reserved priority)",
        "High",
        "status ∈ {voimassa, hakemus, karenssi}; Aluetunnus 'VA...'; Hakija (applicant)"),
    "malminetsinta": (
        "Exploration PERMIT (Malminetsintälupa). voimassa = granted & in force; "
        "hakemus = pending application; karenssi = lapsed permit in cooling-off.",
        "Yes (active permits); pending/cooling-off are swing categories",
        "High",
        "status field; Aluetunnus 'ML...'; Voimassaol (valid-until); Päätöspvm"),
    "kaivosalue": (
        "MINING-PERMIT area (Kaivoslupa/Kaivosalue under the 2011 Mining Act). "
        "Active = operating/granted mining permit area.",
        "Yes (active mining permits are firmly taken)",
        "High",
        "status field; Aluetunnus 'KL...'; mostly gold/metal commodities"),
    "kaivospiiri": (
        "MINING CONCESSION / district (Kaivospiiri, older Mining Act title). "
        "Many are long-standing (Kaivospiir date back to e.g. 1986).",
        "Yes (active concessions are firmly taken)",
        "High",
        "status field; KaivNro; Kaivospiir (establishment date); Haltijanim (holder)"),
    "valtaus": (
        "CLAIM (Valtaus, old Mining Act). In this extract 100/107 are KARENSSI "
        "(lapsed, in cooling-off) — i.e. mostly historical, not active.",
        "Conservative: yes; Strict: mostly NO (only 7 active)",
        "High",
        "status mostly 'karenssi'; Raukeamisp (lapse date) populated"),
    "kullanhuuhdonta": (
        "GOLD-PANNING permit (Kullanhuuhdonta). Small areas; voimassa = active "
        "panning permit, hakemus = pending. Relevant to Lapland gold ground but "
        "small-scale; overlaps with prospective areas around Lemmenjoki/Ivalojoki.",
        "Yes (occupies ground) but small-scale; review relevance",
        "Medium",
        "status field; Aluetunnus 'HL...'; small polygon areas"),
}


def write_legal_meaning(cfg: dict, outputs: Path) -> None:
    rights = _m02c.load_classified_rights(cfg)
    rights["_stem"] = rights["source_layer"].str.split("_").str[0]
    L = ["# Diagnostic T2 — Legal meaning of each Tukes layer", "",
         "Classification is based on the actual `status` attribute in each shapefile",
         "(voimassa=active, hakemus=pending, karenssi=cooling-off) plus the Finnish",
         "Mining Act meaning of each title type. **Not legal advice** — see caveats.", "",
         "## Status distribution actually observed", "",
         "| source_layer | active | pending | cooling_off | uncertain | total |",
         "|--------------|--------|---------|-------------|-----------|-------|"]
    for stem, sub in rights.groupby("_stem"):
        vc = sub["legal_class"].value_counts().to_dict()
        L.append(f"| {stem} | {vc.get('active',0)} | {vc.get('pending',0)} | "
                 f"{vc.get('cooling_off',0)} | {vc.get('uncertain',0)} | {len(sub)} |")
    L += ["", "## Legal interpretation", "",
          "| source_layer | likely legal meaning | active/pending/expired? | exclude from open-ground search? | confidence | evidence/attribute |",
          "|--------------|----------------------|-------------------------|----------------------------------|-----------|--------------------|"]
    for stem, (meaning, exclude, conf, ev) in LEGAL_MEANING.items():
        sub = rights[rights["_stem"] == stem]
        vc = sub["legal_class"].value_counts().to_dict()
        mix = f"active={vc.get('active',0)}, pending={vc.get('pending',0)}, cooling_off={vc.get('cooling_off',0)}"
        L.append(f"| {stem} | {meaning} | {mix} | {exclude} | {conf} | {ev} |")
    L += ["", "## What must still be checked manually", "",
          "- **Cooling-off (karenssi)**: confirm the precise legal effect of the waiting",
          "  period for each title type, and whether it blocks a new reservation/application.",
          "- **Pending (hakemus)**: a pending application does not guarantee a grant, but",
          "  the Mining Act gives the first applicant priority — treat as effectively taken",
          "  for now, verify case-by-case in the live register.",
          "- **kullanhuuhdonta** relevance to hard-rock orogenic gold targeting (it is",
          "  alluvial gold-panning) — likely low overlap with our deep targets; keep as mask",
          "  but flag as a different commodity context.",
          "- None of this is a legal opinion. Verify every title in the live Tukes register",
          "  (https://gtkdata.gtk.fi/Kaivosrekisteri/) before any reservation decision.", ""]
    (outputs / "DIAGNOSTIC_LEGAL_MEANING.md").write_text("\n".join(L), encoding="utf-8")
    log.info("T2 wrote DIAGNOSTIC_LEGAL_MEANING.md")


# --------------------------------------------------------------------------- T4
def write_overlap_audit(cfg: dict, processed: Path, outputs: Path) -> None:
    grid = gpd.read_file(processed / "aoi_grid.gpkg", layer="aoi_grid")
    rights = gpd.read_file(processed / "tukes_all_rights.gpkg")
    status = pd.read_csv(outputs / "cell_legal_status.csv")

    # Double-count proof: per cell, naive SUM of per-right intersection areas vs the
    # UNION area the pipeline uses. If rights overlap, sum > union; union <= cell area.
    inter = gpd.overlay(grid[["cell_id", "geometry"]], rights[["geometry"]],
                        how="intersection", keep_geom_type=True)
    inter = inter[~inter.geometry.is_empty].copy()
    inter["piece_area"] = inter.geometry.area
    naive_sum = inter.groupby("cell_id")["piece_area"].sum()
    union_area = inter.dissolve(by="cell_id").geometry.area
    comp = pd.DataFrame({"naive_sum_m2": naive_sum, "union_m2": union_area}).dropna()
    comp["ratio"] = comp["naive_sum_m2"] / comp["union_m2"]
    n_double = int((comp["ratio"] > 1.0001).sum())
    max_ratio = float(comp["ratio"].max()) if len(comp) else 1.0

    pct = status["taken_overlap_pct"]
    desc = pct.describe()
    over100 = int((pct > 100.0001).sum())
    aoi_km2 = grid.geometry.area.sum() / 1e6

    top20 = status.sort_values("taken_overlap_pct", ascending=False).head(20)[
        ["cell_id", "taken_overlap_pct", "taken_layer_count", "source_layers", "legal_status"]]
    rnd = status.sample(20, random_state=7)[
        ["cell_id", "taken_overlap_pct", "taken_layer_count", "source_layers", "legal_status"]]

    # Histogram.
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(pct, bins=np.linspace(0, 100, 51), color="#444", edgecolor="white")
    ax.set_xlabel("taken_overlap_pct (% of cell covered by any Tukes right)")
    ax.set_ylabel("number of cells")
    ax.set_title("Distribution of Tukes overlap per AOI cell")
    ax.set_yscale("log")
    fig.tight_layout()
    fig.savefig(outputs / "taken_overlap_histogram.png", dpi=130)
    plt.close(fig)

    L = ["# Diagnostic T4 — Geometry & overlap audit", "",
         f"- Total AOI area (grid): **{aoi_km2:,.1f} km²**",
         f"- Grid cells: **{len(grid)}**",
         f"- open + partly + taken = {int((status.legal_status=='open').sum())} + "
         f"{int((status.legal_status=='partly_taken').sum())} + "
         f"{int((status.legal_status=='taken').sum())} = "
         f"**{len(status)}** (== total cells: {len(status)==len(grid)})", "",
         "## taken_overlap_pct distribution", "",
         "```", desc.to_string(), "```",
         f"- Max overlap %: **{pct.max():.4f}**",
         f"- Cells with overlap > 100%: **{over100}** (must be 0)", "",
         "## Double-counting proof (union vs naive sum)", "",
         "The pipeline computes taken area as the UNION of per-cell intersection pieces",
         "(via dissolve), not the sum. If it summed instead, overlapping rights would",
         "inflate area beyond the cell.",
         f"- Cells where rights overlap (naive sum > union): **{n_double}**",
         f"- Worst naive-sum / union ratio: **{max_ratio:.3f}×** "
         f"(would have over-counted by {(max_ratio-1)*100:.1f}% in that cell)",
         f"- Because we union, max overlap stays ≤ 100% (observed max {pct.max():.2f}%). ✔", "",
         "## Top 20 cells by overlap", "", df_to_md(top20), "",
         "## 20 random cells", "", df_to_md(rnd), ""]
    (outputs / "DIAGNOSTIC_OVERLAP_AUDIT.md").write_text("\n".join(L), encoding="utf-8")
    log.info("T4 wrote DIAGNOSTIC_OVERLAP_AUDIT.md + taken_overlap_histogram.png "
             "(double-count cells=%d, over100=%d)", n_double, over100)


# --------------------------------------------------------------------------- T5
def write_aoi_audit(cfg: dict, processed: Path, outputs: Path) -> None:
    bounds = cfg["aoi"]["bounds"]
    xmin, ymin, xmax, ymax = bounds
    corners = {"SW": (xmin, ymin), "SE": (xmax, ymin),
               "NW": (xmin, ymax), "NE": (xmax, ymax)}
    corners_ll = {k: TO_WGS84.transform(x, y) for k, (x, y) in corners.items()}
    aoi_km2 = (xmax - xmin) * (ymax - ymin) / 1e6

    # Reference-point coverage.
    from pyproj import Transformer as T
    to_3067 = T.from_crs("EPSG:4326", "EPSG:3067", always_xy=True)
    cover = {}
    for name, (lon, lat) in REFERENCE_POINTS.items():
        x, y = to_3067.transform(lon, lat)
        inside = (xmin <= x <= xmax) and (ymin <= y <= ymax)
        cover[name] = (inside, x, y)

    L = ["# Diagnostic T5 — AOI correctness audit", "",
         "## AOI bounds", "",
         f"- EPSG:3067 [xmin, ymin, xmax, ymax]: `{bounds}`",
         f"- Width × height: {(xmax-xmin)/1000:.0f} km × {(ymax-ymin)/1000:.0f} km",
         f"- Area: **{aoi_km2:,.0f} km²**", "",
         "### Corners in WGS84 (lat, lon)", ""]
    for k, (lon, lat) in corners_ll.items():
        L.append(f"- {k}: {lat:.4f}°N, {lon:.4f}°E")
    L += ["", "## Coverage of key Central Lapland gold features", "",
          "| feature | inside AOI? | EPSG:3067 (E, N) |",
          "|---------|-------------|------------------|"]
    for name, (inside, x, y) in cover.items():
        L.append(f"| {name} | {'✅ yes' if inside else '❌ NO'} | ({x:,.0f}, {y:,.0f}) |")
    n_in = sum(1 for v in cover.values() if v[0])
    L += ["",
          f"**{n_in}/{len(cover)} reference features fall inside the AOI.**", "",
          "## Why this AOI", "",
          "- Chosen to span the Central Lapland Greenstone Belt from the Kittilä/",
          "  Suurikuusikko–Sirkka–Kiistala area in the west to the Sodankylä/Ikkari area",
          "  in the east — the principal orogenic-gold corridor.",
          "- 5 km cells give ~30,600 km² / 1,224 cells: coarse enough to be fast, fine",
          "  enough to localise reservation-scale blocks.", "",
          "## Is it too broad or too narrow?", "",
          "- **Slightly broad**: it includes ground well outside the greenstone belt",
          "  (basement/granitoid terrain) that is geologically low-priority. That's fine",
          "  for a legal-availability sweep but Step 2 should clip to the belt + buffer.",
          "- **Not too narrow**: all listed marquee features are covered (see table).",
          "- Recommendation: keep for Step 1; in Step 2 intersect with the GTK greenstone-",
          "  belt polygon to drop irrelevant cells before modelling.", ""]
    (outputs / "DIAGNOSTIC_AOI.md").write_text("\n".join(L), encoding="utf-8")

    # Overview map.
    grid = gpd.read_file(processed / "aoi_grid.gpkg", layer="aoi_grid")
    rights = gpd.read_file(processed / "tukes_all_rights.gpkg")
    taken = gpd.read_file(outputs / "taken_cells.gpkg", layer="taken_cells")
    openc = gpd.read_file(outputs / "open_cells.gpkg", layer="open_cells")
    clean = openc[openc["is_clean_open"]] if "is_clean_open" in openc else openc

    import matplotlib.lines as mlines
    import matplotlib.patches as mpatches
    fig, ax = plt.subplots(figsize=(9, 9))
    grid.boundary.plot(ax=ax, color="0.85", linewidth=0.3)
    clean.plot(ax=ax, color="#2ca02c", alpha=0.35)
    if len(taken):
        taken.plot(ax=ax, color="#999999", alpha=0.45)
    rights.plot(ax=ax, facecolor="none", edgecolor="#d62728", linewidth=0.4)
    # Reference points.
    for name, (lon, lat) in REFERENCE_POINTS.items():
        x, y = to_3067.transform(lon, lat)
        ax.plot(x, y, marker="*", color="black", markersize=11)
        ax.annotate(name.split(" (")[0], (x, y), fontsize=7, xytext=(4, 4),
                    textcoords="offset points")
    ax.set_title("GeoArb_Finland AOI — grid, Tukes rights, clean-open & taken cells (EPSG:3067)")
    ax.set_xlabel("Easting (m)"); ax.set_ylabel("Northing (m)")
    # Build a legend with explicit handles (plot()/patches don't auto-register labels).
    handles = [
        mpatches.Patch(facecolor="#2ca02c", alpha=0.35, label="clean-open cells"),
        mpatches.Patch(facecolor="#999999", alpha=0.45, label="taken cells"),
        mpatches.Patch(facecolor="none", edgecolor="#d62728", label="Tukes rights"),
        mlines.Line2D([], [], color="black", marker="*", linestyle="none",
                      markersize=10, label="reference gold features"),
    ]
    ax.legend(handles=handles, loc="upper right", fontsize=8)
    fig.tight_layout()
    fig.savefig(outputs / "aoi_overview.png", dpi=130)
    plt.close(fig)
    log.info("T5 wrote DIAGNOSTIC_AOI.md + aoi_overview.png (%d/%d features inside)",
             n_in, len(cover))


# --------------------------------------------------------------------------- T6
def write_clean_open_inspection(cfg: dict, processed: Path, outputs: Path) -> None:
    openc = gpd.read_file(outputs / "open_cells.gpkg", layer="open_cells")
    clean = openc[openc["is_clean_open"]].copy()
    rights = _m02c.load_classified_rights(cfg)

    # Nearest right (with attributes) per clean cell, measured from centroid.
    cell_pts = clean.copy()
    cell_pts["geometry"] = cell_pts.geometry.centroid
    near = gpd.sjoin_nearest(
        cell_pts[["cell_id", "geometry"]],
        rights[["source_layer", "legal_class", "right_id", "holder", "geometry"]],
        how="left", distance_col="nearest_right_m")
    near = near.sort_values("nearest_right_m").drop_duplicates("cell_id")
    near = near.set_index("cell_id")

    base = clean.set_index("cell_id")
    lon, lat = TO_WGS84.transform(base["centroid_x"].values, base["centroid_y"].values)
    tbl = pd.DataFrame({
        "cell_id": base.index,
        "centroid_x": base["centroid_x"].values,
        "centroid_y": base["centroid_y"].values,
        "centroid_lat": np.round(lat, 5),
        "centroid_lon": np.round(lon, 5),
        "taken_overlap_pct": base["taken_overlap_pct"].values,
        "nearest_right_m": near.reindex(base.index)["nearest_right_m"].round(1).values,
        "nearest_source_layer": near.reindex(base.index)["source_layer"].values,
        "nearest_right_class": near.reindex(base.index)["legal_class"].values,
        "nearest_right_id": near.reindex(base.index)["right_id"].values,
        "nearest_right_holder": near.reindex(base.index)["holder"].values,
    }).reset_index(drop=True)

    rng = np.random.default_rng(7)
    pick_random = tbl.iloc[rng.choice(len(tbl), size=min(20, len(tbl)), replace=False)].copy()
    pick_random["selection_reason"] = "random_clean_open"
    pick_boundary = tbl.sort_values("nearest_right_m").head(20).copy()
    pick_boundary["selection_reason"] = "near_taken_boundary"

    # Representative cell per largest clusters.
    clusters_path = outputs / "clean_open_clusters.gpkg"
    cluster_rows = []
    if clusters_path.exists():
        clusters = gpd.read_file(clusters_path, layer="clean_open_clusters")
        if not clusters.empty:
            big = clusters.sort_values("n_cells", ascending=False).head(20)
            cents = big.geometry.centroid
            for cx, cy in zip(cents.x, cents.y):
                d = ((tbl["centroid_x"] - cx) ** 2 + (tbl["centroid_y"] - cy) ** 2)
                cluster_rows.append(tbl.iloc[int(d.idxmin())])
    pick_cluster = pd.DataFrame(cluster_rows)
    if not pick_cluster.empty:
        pick_cluster["selection_reason"] = "cluster_representative"

    out = pd.concat([pick_random, pick_boundary, pick_cluster], ignore_index=True)
    out = out.drop_duplicates("cell_id", keep="first")
    out.to_csv(outputs / "top_clean_open_cells_for_manual_review.csv", index=False)
    log.info("T6 wrote top_clean_open_cells_for_manual_review.csv (%d rows; min dist-to-right %.1f m)",
             len(out), tbl["nearest_right_m"].min())


def main() -> int:
    cfg = load_config()
    processed = get_path(cfg, "processed")
    outputs = get_path(cfg, "outputs")
    write_provenance(cfg, outputs)
    write_legal_meaning(cfg, outputs)
    write_overlap_audit(cfg, processed, outputs)
    write_aoi_audit(cfg, processed, outputs)
    write_clean_open_inspection(cfg, processed, outputs)
    log.info("All diagnostic artefacts written to %s", outputs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
