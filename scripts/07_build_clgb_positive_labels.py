"""
07 — Build CLGB orogenic-gold positive labels (anti-contamination).

POSITIVES = FODD deposits whose GENETIC_TYPE is orogenic gold AND not on the exclusion
list. Everything else is recorded separately, NEVER silently used as a positive.

RELIABILITY RANK (from FODD STATUS):
    1 = mine (active/closed)         highest confidence
    2 = deposit / prospect (not exploited)
    (occurrences / till anomalies would be 3/4 — none present here as typed positives)

EXCLUDED (contaminating non-CLGB systems — see docs/CLGB_MODEL_EXCLUSIONS.md):
    IOCG, Au-U (Rompas), Au-Co-U-REE (Kuusamo), VMS, epithermal, porphyry/intrusion-
    related, skarn, placer/paleoplacer, and untyped/unknown.

OUTPUTS
    data/processed/clgb_positive_labels.gpkg        (positive deposit points + reliability)
    data/processed/excluded_non_clgb_labels.gpkg    (everything excluded + reason)
    data/processed/cell_labels_<grid>.parquet       (per-cell is_positive flag)
    data/outputs/STEP2_LABEL_AUDIT.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import get_logger, get_path, load_config  # noqa: E402

log = get_logger("07_labels")


def classify(gdf: gpd.GeoDataFrame, cfg: dict) -> gpd.GeoDataFrame:
    """Tag each FODD point as positive / excluded with a reason + reliability."""
    lab = cfg["labels"]
    gfield = lab["genetic_field"]
    inc = [k.lower() for k in lab["include_genetic_keywords"]]
    exc = [k.lower() for k in lab["exclude_genetic_keywords"]]

    out = gdf.copy()
    gt = out[gfield].astype(str).str.lower().fillna("")
    status = out.get("STATUS", pd.Series([""] * len(out))).astype(str).str.lower()

    def decide(g):
        if not g or g == "nan":
            return ("excluded", "untyped/unknown genetic type")
        if any(k in g for k in exc):
            hit = next(k for k in exc if k in g)
            return ("excluded", f"non-CLGB genetic type ({hit})")
        if any(k in g for k in inc):
            return ("positive", "orogenic gold")
        return ("excluded", "genetic type not in CLGB include-list")

    decisions = [decide(g) for g in gt]
    out["label_class"] = [d[0] for d in decisions]
    out["label_reason"] = [d[1] for d in decisions]
    out["label_reliability"] = [
        1 if "mine" in s else 2 for s in status  # mine vs deposit/prospect
    ]
    out["reliability_name"] = out["label_reliability"].map({1: "mine", 2: "deposit_or_prospect"})
    return out


def main() -> int:
    cfg = load_config()
    raw = get_path(cfg, "raw")
    processed = get_path(cfg, "processed", create=True)
    outputs = get_path(cfg, "outputs", create=True)

    fodd_path = raw / "gtk/fodd_precious_metals.gpkg"
    if not fodd_path.exists():
        log.error("FODD deposits not found: %s — run 05 first.", fodd_path)
        return 2
    fodd = gpd.read_file(fodd_path).to_crs("EPSG:3067")

    tagged = classify(fodd, cfg)
    positives = tagged[tagged["label_class"] == "positive"].copy()
    excluded = tagged[tagged["label_class"] == "excluded"].copy()

    keep_cols = ["NAME", "MAIN_COMMODITIES", "GENETIC_TYPE", "STATUS",
                 "label_class", "label_reason", "label_reliability", "reliability_name",
                 "geometry"]
    keep_cols = [c for c in keep_cols if c in tagged.columns]
    positives[keep_cols].to_file(processed / "clgb_positive_labels.gpkg",
                                 layer="clgb_positive_labels", driver="GPKG")
    excluded[keep_cols].to_file(processed / "excluded_non_clgb_labels.gpkg",
                                layer="excluded_non_clgb_labels", driver="GPKG")
    log.info("Positives: %d | Excluded: %d", len(positives), len(excluded))

    # --- Map positives onto grids (cell contains a positive) ---
    cell_label_counts = {}
    for gname in ["clgb_grid_2km", "clgb_grid_1km"]:
        gp = outputs / f"{gname}.gpkg"
        if not gp.exists():
            continue
        grid = gpd.read_file(gp)
        if positives.empty:
            grid["is_positive"] = False
            grid["positive_name"] = None
            grid["positive_reliability"] = pd.NA
        else:
            j = gpd.sjoin(grid[["cell_id", "geometry"]], positives, predicate="contains", how="left")
            # Best (lowest reliability number) per cell + a name.
            agg = j.groupby("cell_id").agg(
                is_positive=("NAME", lambda s: s.notna().any()),
                positive_name=("NAME", lambda s: next((x for x in s if isinstance(x, str)), None)),
                positive_reliability=("label_reliability", "min"))
            grid = grid.merge(agg, on="cell_id", how="left")
            grid["is_positive"] = grid["is_positive"].fillna(False)
        n_pos_cells = int(grid["is_positive"].sum())
        cell_label_counts[gname] = n_pos_cells
        size = gname.split("_")[-1]
        grid[["cell_id", "is_positive", "positive_name", "positive_reliability"]].to_parquet(
            processed / f"cell_labels_{size}.parquet", index=False)
        log.info("%s: %d positive cells", gname, n_pos_cells)

    # --- Audit ---
    L = ["# Step 2 Label Audit", "",
         "Positive labels are **CLGB orogenic gold only**, filtered on FODD GENETIC_TYPE.",
         "Contaminating systems are excluded (see docs/CLGB_MODEL_EXCLUSIONS.md).", "",
         f"- FODD precious-metal points in AOI: **{len(tagged)}**",
         f"- **Positives (orogenic gold): {len(positives)}**",
         f"- Excluded (non-CLGB / untyped): {len(excluded)}",
         f"- Positive cells: " + ", ".join(f"{k.split('_')[-1]}={v}" for k, v in cell_label_counts.items()),
         "", "## Positive labels (orogenic gold)", "",
         "| name | commodities | genetic type | status | reliability |",
         "|------|-------------|--------------|--------|-------------|"]
    for _, r in positives.iterrows():
        L.append(f"| {r.get('NAME')} | {r.get('MAIN_COMMODITIES')} | {r.get('GENETIC_TYPE')} "
                 f"| {r.get('STATUS')} | {r.get('reliability_name')} |")
    L += ["", "## Excluded (NOT used as positives)", "",
          "| name | genetic type | reason |", "|------|--------------|--------|"]
    for _, r in excluded.iterrows():
        L.append(f"| {r.get('NAME')} | {r.get('GENETIC_TYPE')} | {r.get('label_reason')} |")
    L += ["", "## Caveats",
          f"- Only **{len(positives)} positives** — very small. Enough for a baseline "
          "top-k capture test, far too few for confident supervised ML. Treat model",
          "  results as indicative, not validated.",
          "- Unknown ground is **unlabelled, not negative** (handled in script 08).",
          "- Till-anomaly-only occurrences are NOT positives (none present here).", ""]
    (outputs / "STEP2_LABEL_AUDIT.md").write_text("\n".join(L), encoding="utf-8")
    log.info("Wrote STEP2_LABEL_AUDIT.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
