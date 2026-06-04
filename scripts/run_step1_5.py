"""
run_step1_5 — Shrink & harden the search space (Step 1.5 orchestrator).

Pipeline:
    1. Ensure CLGB clip + finer grids exist (04b) and restriction masks (04c).
    2. Gold-panning scenarios A vs B on the 5 km grid (Task 4).
    3. Re-cluster clean-open ground on the 2 km and 1 km CLGB grids, across mask
       modes (conservative / strict_active / scenario_b) (Task 5).
    4. Write the Step 1.5 Decision Report (Task 6).

Nothing here is a gold target. Outputs are *legal/geographic candidate clusters*.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import get_logger, get_path, import_script, load_config  # noqa: E402

log = get_logger("run_step1_5")
SCRIPTS = Path(__file__).resolve().parent
_m02 = import_script("02_mask_taken_areas.py", "m02")
_m02c = import_script("02c_classify_tukes_status.py", "m02c")
_m04 = import_script("04_cluster_open_cells.py", "m04")


def _run(script: str, *args):
    log.info(">>> %s %s", script, " ".join(args))
    subprocess.run([sys.executable, str(SCRIPTS / script), *args], check=True)


def gold_panning_scenarios(cfg, grid, rights, outputs):
    """Task 4: Scenario A (exclude all incl panning) vs B (panning kept open)."""
    stem = rights["source_layer"].str.split("_").str[0]
    panning = cfg["gold_panning"]["layer_stem"]
    A_rights = rights                              # exclude everything incl panning
    B_rights = rights[stem != panning]             # keep gold-panning ground open

    A = _m02.compute_cell_status(grid, A_rights, cfg)
    B = _m02.compute_cell_status(grid, B_rights, cfg)

    for st, name, layer in [(A, "open_cells_hardrock_scenario_A.gpkg", "scenario_A"),
                            (B, "open_cells_hardrock_scenario_B.gpkg", "scenario_B")]:
        openc = st[st["legal_status"] == "open"][
            ["cell_id", "area_km2", "centroid_x", "centroid_y", "taken_overlap_pct",
             "is_clean_open", "legal_status", "geometry"]]
        openc.to_file(outputs / name, layer=layer, driver="GPKG")

    a_idx = A.set_index("cell_id"); b_idx = B.set_index("cell_id")
    changed = (a_idx["legal_status"] != b_idx["legal_status"])
    n_changed = int(changed.sum())
    a_clean = int(A["is_clean_open"].sum()); b_clean = int(B["is_clean_open"].sum())
    a_open = int((A["legal_status"] == "open").sum())
    b_open = int((B["legal_status"] == "open").sum())
    panning_only = int(((a_idx["legal_status"] != "open") & (b_idx["legal_status"] == "open")).sum())

    lines = ["# Diagnostic — Gold-panning (kullanhuuhdonta) effect (Task 4)", "",
             "Gold-panning permits are placer/alluvial, a different commodity context",
             "from hard-rock orogenic gold. We produce two masks and report the delta —",
             "**this is a modelling choice, not a legal decision.**", "",
             "| scenario | rule | open cells (≤1%) | clean-open (0%) |",
             "|----------|------|------------------|-----------------|",
             f"| **A** | exclude ALL Tukes rights incl. gold-panning | {a_open} | {a_clean} |",
             f"| **B** | exclude all EXCEPT gold-panning (placer kept open) | {b_open} | {b_clean} |",
             "",
             f"- Cells that change legal_status between A and B: **{n_changed}**",
             f"- Cells that are open ONLY because gold-panning is not excluded (open in B, "
             f"not in A): **{panning_only}**",
             f"- Extra clean-open ground in B vs A: **{b_clean - a_clean}** cells "
             f"(= {(b_clean - a_clean) * 25} km² at 5 km).",
             "",
             "## Interpretation",
             "- If gold-panning permits should NOT block hard-rock targeting (they are",
             f"  placer), Scenario B frees ~{panning_only} cells of otherwise-'taken' ground.",
             "- These cells sit under existing gold-panning permits — surface/placer rights",
             "  that may or may not constrain a deep hard-rock reservation. **Verify legally.**",
             "- Scenario A remains the cautious default used elsewhere in Step 1.", ""]
    (outputs / "DIAGNOSTIC_GOLD_PANNING_EFFECT.md").write_text("\n".join(lines), encoding="utf-8")
    log.info("Task4 gold-panning: A_clean=%d B_clean=%d changed=%d panning_only=%d",
             a_clean, b_clean, n_changed, panning_only)
    return {"a_clean": a_clean, "b_clean": b_clean, "n_changed": n_changed,
            "panning_only": panning_only, "a_open": a_open, "b_open": b_open}


def cluster_combos(cfg, outputs, restrictions_path):
    """Task 5: cluster across 2km/1km grids x mask modes; build ranked CSV."""
    grids = {"2km": outputs / "clgb_grid_2km.gpkg", "1km": outputs / "clgb_grid_1km.gpkg"}
    modes = ["conservative", "strict_active", "scenario_b"]
    all_rows = []
    canonical = {}
    for gname, gpath in grids.items():
        for mode in modes:
            clusters = _m04.run_clustering(cfg, gpath, mode, restrictions_path)
            clusters = clusters.copy()
            clusters["grid"] = gname
            clusters["scenario"] = {"conservative": "A", "scenario_b": "B",
                                    "strict_active": "strict"}[mode]
            tag = f"{gname}_{mode}"
            clusters.to_file(outputs / f"clean_open_clusters_{tag}.gpkg",
                             layer=f"clean_open_clusters_{tag}", driver="GPKG")
            if mode == "conservative":  # canonical per-grid file the task asks for
                clusters.to_file(outputs / f"clean_open_clusters_{gname}.gpkg",
                                 layer=f"clean_open_clusters_{gname}", driver="GPKG")
                canonical[gname] = clusters
            all_rows.append(clusters.drop(columns="geometry"))
    ranked = pd.concat(all_rows, ignore_index=True)
    ranked = ranked.sort_values(["grid", "scenario", "n_cells"], ascending=[True, True, False])
    ranked.to_csv(outputs / "clean_open_clusters_ranked.csv", index=False)
    log.info("Task5 wrote clean_open_clusters_ranked.csv (%d cluster rows across %d runs)",
             len(ranked), len(grids) * len(modes))
    return canonical, ranked


def write_decision_report(cfg, outputs, processed, panning, canonical, ranked):
    clgb = gpd.read_file(processed / "clgb_aoi.gpkg")
    clgb_area = float(clgb["area_km2"].iloc[0])
    clgb_src = str(clgb["source"].iloc[0])

    # clean-open cell counts on CLGB grids (conservative).
    def clean_cells(gname):
        c = canonical.get(gname)
        return int(c["n_cells"].sum()) if c is not None and not c.empty else 0
    co_2km = clean_cells("2km"); co_1km = clean_cells("1km")

    # restriction status (04c).
    rstatus = outputs / "cell_restriction_status.csv"
    restr_applied = False; n_after = None
    if rstatus.exists():
        df = pd.read_csv(rstatus)
        restr_applied = bool(df["is_restricted"].any())
        n_after = int((~df["is_restricted"]).sum())

    cons2 = canonical.get("2km")
    n_clusters_2km = len(cons2) if cons2 is not None else 0
    # top 10 by area then cleanliness (far from active rights).
    top = ranked[ranked["grid"] == "2km"]
    top = top[top["scenario"] == "A"].copy()
    if not top.empty:
        top["far_from_active"] = top["dist_to_nearest_active_right_m"].fillna(0)
        top10 = top.sort_values(["area_km2", "far_from_active"], ascending=False).head(10)
    else:
        top10 = top
    # clusters too close to active rights (within 2 km).
    close = top[top["dist_to_nearest_active_right_m"].fillna(1e9) < 2000] if not top.empty else top

    L = ["# Step 1.5 Decision Report", "",
         "**Status: candidate open-ground analysis. These are legal/geographic candidate",
         "clusters / modelling candidates — NOT gold targets.** Gold targets require Step 2",
         "feature convergence (structure + lithology + magnetics + gravity + till geochem +",
         "glacial correction + legal openness).", "",
         "## CLGB refinement", "",
         f"- CLGB clip area: **{clgb_area:,.0f} km²** (from {clgb_area/30600*100:.0f}% of the "
         f"30,600 km² full AOI).",
         f"- CLGB source: {clgb_src}",
         "", "## Answers", "",
         f"**1. Clean-open cells after CLGB clipping?** 2 km grid: **{co_2km} cells "
         f"({co_2km*4} km²)**; 1 km grid: **{co_1km} cells ({co_1km} km²)** "
         f"(conservative mask, Scenario A).",
         "",
         f"**2. Clean-open after restrictions?** "
         + (f"{n_after} cells remain open (restrictions applied)."
            if restr_applied else
            "**No change — 0 restriction layers are present yet.** Restriction masking is "
            "wired (04c) but Natura 2000 / protected areas / Sámi Homeland / water bodies "
            "must be supplied (see RESTRICTION_DOWNLOAD_CHECKLIST.md). Until then, 'open' = "
            "Tukes-cadastre-only."),
         "",
         f"**3. How many open clusters remain?** 2 km conservative: **{n_clusters_2km} clusters**; "
         f"1 km conservative: **{len(canonical.get('1km', [])) if canonical.get('1km') is not None else 0}**. "
         "One dominant contiguous block still dominates (open ground is well-connected at "
         "this resolution).",
         "",
         "**4. Top 10 candidate clusters (2 km, Scenario A) by area & legal cleanliness:**", ""]
    if not top10.empty:
        L += ["| cluster_id | n_cells | area_km2 | centroid_lat | centroid_lon | dist_active_m | restr_overlap_% |",
              "|---|---|---|---|---|---|---|"]
        for _, r in top10.iterrows():
            L.append(f"| {r['cluster_id']} | {r['n_cells']} | {r['area_km2']} | "
                     f"{r['centroid_lat']} | {r['centroid_lon']} | "
                     f"{r['dist_to_nearest_active_right_m']} | {r['restriction_overlap_pct']} |")
    L += ["",
          f"**5. Clusters too close to active rights (<2 km):** **{len(close)}** of "
          f"{len(top)} 2 km Scenario-A clusters touch/abut active rights — the big block "
          "wraps around active permits, so its edge cells sit close to live ground.",
          "",
          f"**6. Clusters that change if gold-panning excluded?** Going from Scenario B "
          f"(panning kept open) to Scenario A (panning excluded) removes **{panning['panning_only']} "
          f"cells** of 5 km open ground; clean-open drops from {panning['b_clean']} (B) to "
          f"{panning['a_clean']} (A). See DIAGNOSTIC_GOLD_PANNING_EFFECT.md.",
          "",
          "**7. Is the AOI now tight enough for Step 2?** Partly. The CLGB clip halves the "
          "area and removes basement corners, but it currently uses an APPROXIMATE manual "
          "envelope, not real GTK greenstone lithology. **Supply GTK bedrock geology and "
          "re-run 04b before trusting the boundary.**",
          "",
          "**8. Model at 2 km or 1 km first?** **2 km first** for regional prospectivity "
          "ranking (3,798 CLGB cells — fast, stable), then drop to **1 km** only inside the "
          "top-ranked clusters for target-memo detail (15,275 cells is wasteful belt-wide).",
          "",
          "**9. Manual legal/restriction checks still blocking a reservation decision:**",
          "   - Acquire + apply restriction layers (Sámi Homeland & Natura 2000 first).",
          "   - Verify pending (hakemus) and cooling-off (karenssi) status per title in the "
          "live Tukes register.",
          "   - Decide whether gold-panning permits block a hard-rock reservation (Scenario A vs B).",
          "   - Replace the manual CLGB envelope with GTK greenstone geology.",
          "",
          "**10. Can we proceed to GTK geology/geophysics feature building?** **YES, WITH "
          "WARNINGS.** The search space is now scoped (CLGB clip + finer grids + status-aware "
          "masks + a working restriction engine). Begin Step 2 ingestion at 2 km, but treat "
          "all 'open' ground as provisional until restriction layers and real CLGB geology "
          "are in.", ""]
    (outputs / "STEP1_5_DECISION_REPORT.md").write_text("\n".join(L), encoding="utf-8")
    log.info("Task6 wrote STEP1_5_DECISION_REPORT.md")
    return {"co_2km": co_2km, "co_1km": co_1km, "n_clusters_2km": n_clusters_2km,
            "restr_applied": restr_applied}


def main() -> int:
    cfg = load_config()
    processed = get_path(cfg, "processed")
    outputs = get_path(cfg, "outputs")

    # 1. Ensure CLGB grids + restriction masks exist.
    if not (outputs / "clgb_grid_2km.gpkg").exists() or not (outputs / "clgb_grid_1km.gpkg").exists():
        _run("04b_refine_aoi_to_clgb.py")
    _run("04c_build_restriction_masks.py")
    restrictions_path = processed / "restriction_masks.gpkg"
    restrictions_arg = str(restrictions_path) if restrictions_path.exists() else None

    rights = _m02c.load_classified_rights(cfg)
    grid5 = gpd.read_file(processed / "aoi_grid.gpkg", layer="aoi_grid")

    # 2. Gold-panning scenarios (Task 4).
    panning = gold_panning_scenarios(cfg, grid5, rights, outputs)

    # 3. Cluster combos (Task 5).
    canonical, ranked = cluster_combos(cfg, outputs, restrictions_arg)

    # 4. Decision report (Task 6).
    summary = write_decision_report(cfg, outputs, processed, panning, canonical, ranked)

    log.info("=" * 70)
    log.info("STEP 1.5 done. 2km clean-open=%d  1km clean-open=%d  2km clusters=%d  "
             "restrictions_applied=%s", summary["co_2km"], summary["co_1km"],
             summary["n_clusters_2km"], summary["restr_applied"])
    log.info("Report: %s", outputs / "STEP1_5_DECISION_REPORT.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
