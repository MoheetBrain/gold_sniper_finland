# GeoArb_Finland — Central Lapland gold target-intelligence pipeline

AI-assisted **gold prospect-generation** system for Finland's Central Lapland
Greenstone Belt. It combines open Finnish geodata with the Tukes mining cadastre to
find **legally-available** ground that is *also* geologically prospective for
orogenic gold, then packages it for possible reservation / partner / junior-explorer
outreach.

> **This repository currently implements Step 1: the legal-availability engine.**
> Geology/geophysics/ML scoring (Step 2) is scaffolded but not yet implemented.

---

## What this project IS and IS NOT

**It IS:** a software + research pipeline using *public* data — geology, geophysics,
till geochemistry, and the Tukes cadastre — plus ML ranking, to generate and
*falsify* gold target packages, and to decide whether to reserve / partner / consult
/ kill each target.

**It is NOT:**
- physical prospecting, gold panning, digging, sampling, or trespass;
- "a satellite that sees gold";
- proof that gold exists anywhere;
- legal advice, a mining right, or an investment guarantee.

Nothing here authorises any field activity. Always verify the **live** Tukes register
and obtain professional legal/geological advice before any reservation or outreach.

---

## Why legal masking comes BEFORE geology

There is no point scoring a cell for gold if the ground is already reserved,
permitted, claimed, or protected. Step 1 builds the **availability filter first**, so
the expensive Step 2 geology work is only ever spent on ground that could realistically
be pursued. The first milestone is *not* finding gold — it is a reliable
legal-availability engine.

---

## Quick start

```bash
# 1. Create and activate the environment (conda recommended)
conda env create -f environment.yml
conda activate geoarb

# 2. Run the whole Step 1 pipeline (downloads Tukes data + builds outputs)
python scripts/run_step1_pipeline.py

# 3. Verify the outputs
python scripts/99_sanity_check_outputs.py
```

`bash setup_env.sh` does steps 1 and also creates the data folder skeleton. If you
cannot use conda, `pip install -r requirements.txt` works **only if GDAL is already
installed** on your system (geopandas/rasterio need it).

Everything spatial uses **EPSG:3067 (ETRS89 / TM35FIN)**, the Finnish standard CRS.

---

## What you get (Step 1 outputs)

A typical run (Tukes data as of 2026-06-02) produces:

| metric | value |
|--------|-------|
| Tukes ZIP layers downloaded | 7 |
| Rights polygons loaded | 1,971 |
| Total AOI cells (5 km grid) | 1,224 |
| **Clean-open cells (0% taken)** | **773** |
| Open cells (≤1% taken) | 825 |
| Partly-taken cells (1–10%) | 68 |
| Taken cells (>10%) | 331 |

(Exact numbers move as the Tukes cadastre updates.) Full, up-to-date numbers are
written to `data/outputs/STEP1_SUMMARY.md` and `.json`.

---

## What each script does

| Script | Role |
|--------|------|
| `scripts/00_download_tukes_map_files.py` | Scrapes the Tukes map-files ATOM feed, downloads + extracts the 6 cadastre layers (reservations, exploration permits, mining permits, concessions, claims, gold panning), writes a manifest. Fails loudly + saves debug HTML if the page structure changes. |
| `scripts/01_make_aoi_grid.py` | Builds the Central Lapland AOI grid (default 5×5 km, EPSG:3067) → `data/processed/aoi_grid.gpkg`. |
| `scripts/02_mask_taken_areas.py` | Merges all Tukes rights, intersects with the grid, computes per-cell taken area/%/layer-count, classifies open / partly-taken / taken, flags `is_clean_open`. The core of Step 1. |
| `scripts/02b_build_restriction_masks_placeholder.py` | Framework for non-cadastre restrictions (Natura 2000, protected areas, Sámi homeland, national parks, water). Reports what's missing; never invents data. |
| `scripts/03_demo_rank_open_cells.py` | **Fake** reproducible score over open cells — proves the plumbing only. NOT geology. |
| `scripts/run_step1_pipeline.py` | Runs 00→01→02→02b→03, stops on critical failure, writes `STEP1_SUMMARY.md/.json`. |
| `scripts/99_sanity_check_outputs.py` | Verifies outputs exist, are readable, valid, EPSG:3067, and that cell counts add up. |
| `scripts/05–12_*.py` | **Step 2 stubs** (GTK layers, structure, glacial-vectored till, labels, XGBoost, spatial backtest, real ranking, memos). Docstring-only skeletons for now. |

---

## Outputs and what they mean

All under `data/outputs/` (and `data/processed/`):

| File | Meaning |
|------|---------|
| `data/processed/aoi_grid.gpkg` | The AOI grid (layer `aoi_grid`): `cell_id`, `area_km2`, `centroid_x/y`. |
| `data/processed/tukes_all_rights.gpkg` | All Tukes rights merged + cleaned, with `source_layer`. |
| `open_cells.gpkg` | Cells ≤1% covered by any right — the priority ground. |
| `partly_taken_cells.gpkg` | Cells 1–10% taken — may contain open sub-areas (kept, not deleted). |
| `taken_cells.gpkg` | Cells >10% taken — deprioritised for Step 1. |
| `cell_legal_status.csv` | Every cell with `taken_overlap_pct`, `taken_layer_count`, `source_layers`, `legal_status`, `is_clean_open`. |
| `ranked_open_cells_demo.gpkg/.csv` | Open cells with the **fake** demo rank (sanity only). |
| `STEP1_SUMMARY.md/.json` | Headline numbers, top-20 demo cells, file list, warnings, Step-2 gaps. |

Thresholds (configurable in `configs/config.yaml`): open `0–1%`, partly-taken
`>1–10%`, taken `>10%`. `is_clean_open` is stricter: **exactly 0%** taken.

---

## Opening the outputs in QGIS

1. Open QGIS, set the project CRS to **EPSG:3067**.
2. Drag in `data/processed/aoi_grid.gpkg`, `data/processed/tukes_all_rights.gpkg`,
   and the three `*_cells.gpkg` from `data/outputs/`.
3. Suggested view: rights polygons (semi-transparent fill) over the grid; style the
   cell layers by `legal_status`, or load `ranked_open_cells_demo.gpkg` graduated by
   `demo_score`. Label cells by `cell_id`.
4. You should see: the Central Lapland AOI grid, the Tukes taken areas, the clean
   open cells, and the demo-ranked open cells. That is the Step 1 gate.

---

## Configuration

Edit `configs/config.yaml` — not the scripts. Key knobs:

- `aoi.bounds` — AOI bounding box in EPSG:3067 (default covers Kittilä/Ikkari →
  Sodankylä, across the Sirkka & Kiistala shear corridors). Tighten to focus.
- `aoi.cell_size_m` — grid cell size (default 5000).
- `legal_status.*` — open / partly-taken / taken thresholds.
- `tukes.layer_keywords` — which cadastre layers to download.

---

## Project layout

```
configs/config.yaml          # all tunable settings
scripts/                     # numbered pipeline + Step 2 stubs + _common.py helpers
docs/STEP2_DATA_REQUIREMENTS.md
data/raw/        tukes_zip, tukes_extracted, debug, restrictions   (git-ignored)
data/processed/  aoi_grid.gpkg, tukes_all_rights.gpkg               (git-ignored)
data/outputs/    open/partly/taken cells, demo rank, STEP1_SUMMARY  (git-ignored)
Project_Architecture.txt     # the full multi-step vision (Step 1 → commercial)
```

---

## What's needed for Step 2

Step 2 adds real geology + ML scoring. It needs GTK bedrock geology, known
gold/mineral occurrences (for ML labels), airborne magnetics (+derivatives), gravity
/ EM / radiometrics, till geochemistry, glacial/Quaternary flow data, fault/shear
layers, a DEM, and the restriction layers. See **`docs/STEP2_DATA_REQUIREMENTS.md`**
for the exact list, formats, where to place each file, and which script consumes it.

Core modelling principles (carried into Step 2): unknown land is *not* barren; known
deposits are positive labels; background is unlabelled (use positive-unlabelled /
semi-supervised methods); validate with spatial cross-validation, not random splits;
require multi-layer convergence and kill single-signal targets; explain scores with
SHAP; export everything to QGIS.

---

## Legal & safety note

The Tukes layers show ground already covered by reservations, exploration permits,
mining permits, concessions, claims and gold-panning permits — public cadastre data,
**not legal advice**. A reservation is not a mining right. Always confirm the live
register and consult professionals before any reservation, disclosure, or outreach.
