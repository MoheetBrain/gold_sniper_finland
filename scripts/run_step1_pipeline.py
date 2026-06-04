"""
run_step1_pipeline — Run the GeoArb_Finland Step 1 legal-availability engine.

PIPELINE (in order)
    00  download Tukes mining-register map files        (non-fatal if offline)
    01  build the Central Lapland AOI grid              (critical)
    02  mask taken areas -> open/partly/taken cells     (critical)
    02b restriction-mask placeholder                    (non-fatal)
    03  demo-rank the open cells (FAKE score)           (critical)

It stops if a *critical* step fails. The download step is treated as non-fatal so
the rest of the pipeline stays runnable offline (script 02 then marks everything
open and the summary flags that no rights were loaded).

OUTPUTS
    data/outputs/STEP1_SUMMARY.md
    data/outputs/STEP1_SUMMARY.json
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import get_logger, get_path, load_config  # noqa: E402

log = get_logger("run_step1")
SCRIPTS_DIR = Path(__file__).resolve().parent

# (filename, human label, critical?)
STEPS = [
    ("00_download_tukes_map_files.py", "Download Tukes map files", False),
    ("01_make_aoi_grid.py", "Build AOI grid", True),
    ("02_mask_taken_areas.py", "Mask taken areas", True),
    ("02b_build_restriction_masks_placeholder.py", "Restriction placeholder", False),
    ("03_demo_rank_open_cells.py", "Demo-rank open cells", True),
]


def run_step(script: str) -> int:
    """Run one pipeline script in a subprocess, streaming its output."""
    path = SCRIPTS_DIR / script
    log.info("=" * 70)
    log.info(">>> RUN %s", script)
    log.info("=" * 70)
    proc = subprocess.run([sys.executable, str(path)])
    return proc.returncode


def _safe_read_gpkg_count(path: Path, layer: str) -> int | None:
    """Return feature count of a GeoPackage layer, or None if unreadable/missing."""
    if not path.exists():
        return None
    try:
        import geopandas as gpd
        return len(gpd.read_file(path, layer=layer))
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not read %s:%s — %s", path.name, layer, exc)
        return None


def gather_summary(cfg: dict, step_results: list[dict]) -> dict:
    """Collect the headline Step 1 numbers from the produced files."""
    import geopandas as gpd
    import pandas as pd

    processed = get_path(cfg, "processed")
    outputs = get_path(cfg, "outputs")
    raw = get_path(cfg, "raw")

    summary: dict = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "project": cfg["project"]["name"],
        "region": cfg["project"]["region"],
        "crs": cfg["project"].get("crs"),
        "aoi_bounds": cfg["aoi"]["bounds"],
        "cell_size_m": cfg["aoi"]["cell_size_m"],
        "steps": step_results,
        "warnings": [],
        "files": [],
    }

    # --- Tukes download manifest ---
    manifest_path = raw / "tukes_download_manifest.json"
    tukes_files, tukes_layers = 0, []
    if manifest_path.exists():
        try:
            recs = json.loads(manifest_path.read_text())
            ok = [r for r in recs if "error" not in r]
            tukes_files = len(ok)
            tukes_layers = [r["filename"] for r in ok]
            if any("error" in r for r in recs):
                summary["warnings"].append("Some Tukes downloads failed (see manifest).")
        except Exception as exc:  # noqa: BLE001
            summary["warnings"].append(f"Could not parse download manifest: {exc}")
    else:
        summary["warnings"].append("No Tukes download manifest — downloads may have failed.")
    summary["tukes_files_downloaded"] = tukes_files
    summary["tukes_layers"] = tukes_layers

    # --- Rights polygons ---
    rights_path = processed / "tukes_all_rights.gpkg"
    n_rights = _safe_read_gpkg_count(rights_path, "tukes_all_rights")
    summary["rights_polygons_loaded"] = n_rights if n_rights is not None else 0
    if not n_rights:
        summary["warnings"].append("0 rights polygons loaded — legal mask is empty.")

    # --- Grid + cell statuses ---
    summary["total_cells"] = _safe_read_gpkg_count(processed / "aoi_grid.gpkg", "aoi_grid") or 0
    summary["open_cells"] = _safe_read_gpkg_count(outputs / "open_cells.gpkg", "open_cells") or 0
    summary["partly_taken_cells"] = _safe_read_gpkg_count(
        outputs / "partly_taken_cells.gpkg", "partly_taken_cells") or 0
    summary["taken_cells"] = _safe_read_gpkg_count(
        outputs / "taken_cells.gpkg", "taken_cells") or 0

    # clean-open count from the CSV (authoritative full table).
    csv_path = outputs / "cell_legal_status.csv"
    clean_open = 0
    if csv_path.exists():
        try:
            df = pd.read_csv(csv_path)
            clean_open = int(df["is_clean_open"].sum())
        except Exception as exc:  # noqa: BLE001
            summary["warnings"].append(f"Could not read cell_legal_status.csv: {exc}")
    summary["clean_open_cells"] = clean_open

    # Consistency check: open+partly+taken should equal total.
    parts_sum = summary["open_cells"] + summary["partly_taken_cells"] + summary["taken_cells"]
    if parts_sum != summary["total_cells"]:
        summary["warnings"].append(
            f"Cell counts don't sum to total: {parts_sum} vs {summary['total_cells']}.")

    # --- Top 20 demo-ranked open cells ---
    top20 = []
    ranked_csv = outputs / "ranked_open_cells_demo.csv"
    if ranked_csv.exists():
        try:
            rdf = pd.read_csv(ranked_csv)
            n = int(cfg["demo_rank"].get("top_n_in_summary", 20))
            cols = [c for c in ["rank", "cell_id", "demo_score",
                                "centroid_x", "centroid_y"] if c in rdf.columns]
            top20 = rdf.sort_values("rank").head(n)[cols].to_dict(orient="records")
        except Exception as exc:  # noqa: BLE001
            summary["warnings"].append(f"Could not read ranked demo CSV: {exc}")
    summary["top20_demo_open_cells"] = top20

    # --- Generated files ---
    for p in sorted(outputs.glob("*")) + [processed / "aoi_grid.gpkg",
                                          processed / "tukes_all_rights.gpkg"]:
        if p.exists():
            summary["files"].append(str(p.relative_to(get_path(cfg, "raw").parent.parent)))

    # --- What's needed for Step 2 ---
    summary["missing_for_step2"] = [
        "GTK bedrock geology (polygons)",
        "GTK mineral occurrences / known gold deposits (points) — needed for ML labels",
        "GTK airborne magnetics (grids) + derivatives",
        "GTK gravity, airborne EM, radiometrics (grids, optional but valuable)",
        "GTK till geochemistry (points/grids: Au, As, Sb, Te, Bi, W, ...)",
        "Glacial flow / Quaternary / surficial geology (for till vectoring)",
        "Fault / shear / lineament layers",
        "DEM / topography",
        "Restriction layers: Natura 2000, protected areas, Sámi homeland, national "
        "parks, water bodies (see data/raw/restrictions/README_RESTRICTIONS.md)",
    ]
    return summary


def write_summary_files(cfg: dict, summary: dict) -> tuple[Path, Path]:
    outputs = get_path(cfg, "outputs", create=True)
    json_path = outputs / "STEP1_SUMMARY.json"
    md_path = outputs / "STEP1_SUMMARY.md"

    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    lines = []
    a = lines.append
    a(f"# Step 1 Summary — {summary['project']}")
    a("")
    a(f"_Generated: {summary['generated_utc']}_")
    a("")
    a(f"**Region:** {summary['region']}  ")
    a(f"**CRS:** {summary['crs']}  ")
    a(f"**AOI bounds (EPSG:3067):** {summary['aoi_bounds']}  ")
    a(f"**Cell size:** {summary['cell_size_m']} m")
    a("")
    a("## Pipeline steps")
    a("")
    a("| step | status | exit |")
    a("|------|--------|------|")
    for s in summary["steps"]:
        a(f"| {s['label']} | {s['status']} | {s['returncode']} |")
    a("")
    a("## Key numbers")
    a("")
    a(f"- Tukes files downloaded: **{summary['tukes_files_downloaded']}**")
    a(f"- Rights polygons loaded: **{summary['rights_polygons_loaded']}**")
    a(f"- Total AOI cells: **{summary['total_cells']}**")
    a(f"- Open cells: **{summary['open_cells']}**")
    a(f"- Clean-open cells (0% taken): **{summary['clean_open_cells']}**")
    a(f"- Partly-taken cells: **{summary['partly_taken_cells']}**")
    a(f"- Taken cells: **{summary['taken_cells']}**")
    a("")
    if summary["tukes_layers"]:
        a("## Tukes layers downloaded")
        a("")
        for f in summary["tukes_layers"]:
            a(f"- `{f}`")
        a("")
    a("## Top 20 demo-ranked open cells  ⚠️ FAKE score (not geology)")
    a("")
    if summary["top20_demo_open_cells"]:
        a("| rank | cell_id | demo_score | centroid_x | centroid_y |")
        a("|------|---------|-----------|-----------|-----------|")
        for r in summary["top20_demo_open_cells"]:
            a(f"| {r.get('rank')} | {r.get('cell_id')} | {r.get('demo_score')} "
              f"| {r.get('centroid_x'):.0f} | {r.get('centroid_y'):.0f} |")
    else:
        a("_No open cells to rank._")
    a("")
    a("## Generated files")
    a("")
    for f in summary["files"]:
        a(f"- `{f}`")
    a("")
    a("## Warnings / errors")
    a("")
    if summary["warnings"]:
        for w in summary["warnings"]:
            a(f"- ⚠️ {w}")
    else:
        a("- none")
    a("")
    a("## What data is missing for Step 2")
    a("")
    for m in summary["missing_for_step2"]:
        a(f"- {m}")
    a("")
    a("See `docs/STEP2_DATA_REQUIREMENTS.md` for the full dataset checklist.")
    a("")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path, json_path


def main() -> int:
    cfg = load_config()
    step_results = []
    overall_rc = 0

    for script, label, critical in STEPS:
        rc = run_step(script)
        status = "ok" if rc == 0 else ("FAILED" if critical else "warn")
        step_results.append({"script": script, "label": label,
                             "critical": critical, "returncode": rc, "status": status})
        if rc != 0:
            if critical:
                log.error("Critical step FAILED: %s (exit %d). Stopping.", script, rc)
                overall_rc = rc
                break
            log.warning("Non-critical step had issues: %s (exit %d). Continuing.",
                        script, rc)

    # Always try to write a summary from whatever was produced.
    summary = gather_summary(cfg, step_results)
    md_path, json_path = write_summary_files(cfg, summary)

    log.info("=" * 70)
    log.info("STEP 1 SUMMARY written:")
    log.info("  %s", md_path)
    log.info("  %s", json_path)
    log.info("Key numbers: total=%d open=%d clean_open=%d partly=%d taken=%d rights=%d",
             summary["total_cells"], summary["open_cells"], summary["clean_open_cells"],
             summary["partly_taken_cells"], summary["taken_cells"],
             summary["rights_polygons_loaded"])
    log.info("=" * 70)

    return overall_rc


if __name__ == "__main__":
    raise SystemExit(main())
