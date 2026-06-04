# Step 2 — Data Requirements

Step 1 (the legal-availability engine) is complete: we have an AOI grid, a merged
Tukes rights mask, and open / partly-taken / taken cells. **Step 2 adds the actual
geology, geophysics and geochemistry** so we can score *open* ground for orogenic
gold prospectivity.

This document lists the exact datasets to gather **before** building Step 2. Do not
invent these layers — use the official sources. Place each under `data/raw/<folder>/`
as noted. All layers will be reprojected to **EPSG:3067 (ETRS89 / TM35FIN)**.

## Deposit model recap (what the data must illuminate)

Orogenic gold in the Central Lapland Greenstone Belt is **structurally controlled**:
shear zones, second-order splays, fault bends/jogs, reactive host rocks (iron-rich
volcanics, carbonaceous sediments), magnetic-destruction (alteration) zones, and
till geochemical anomalies (Au + As, Sb, Te, Bi, W pathfinders). The datasets below
exist to make those signals *mappable* per grid cell.

---

## Required datasets

| # | Dataset | Why we need it | Format | Place under | Required? | Consumed by |
|---|---------|----------------|--------|-------------|-----------|-------------|
| 1 | **GTK bedrock geology** | Identify reactive/favourable host lithologies; build lithology features & contacts | Vector polygons (GPKG/SHP) | `data/raw/gtk_geology/` | **Required** | `05_load_gtk_layers.py`, `06_build_structural_features.py` |
| 2 | **GTK mineral occurrences / known gold deposits** | Positive labels for ML; backtesting (hide & rediscover) | Vector points (GPKG/SHP/CSV+coords) | `data/raw/gtk_mineral_occurrences/` | **Required** | `08_build_training_labels.py`, `10_spatial_backtest.py` |
| 3 | **Airborne magnetics (TMI / RTP grid)** | Map structure & magnetic-destruction alteration zones | Raster grid (GeoTIFF) | `data/raw/gtk_magnetics/` | **Required** | `05_load_gtk_layers.py`, `06_build_structural_features.py` |
| 4 | **Magnetic derivatives** (1VD, tilt, analytic signal) | Sharpen edges/contacts/lineaments; many can be computed from #3 | Raster grid (GeoTIFF) | `data/raw/gtk_magnetics/` (or derived to `data/interim/`) | Optional (derivable) | `06_build_structural_features.py` |
| 5 | **Fault / shear / lineament layers** | Distance-to-shear, splay/intersection density — the core orogenic control | Vector lines (GPKG/SHP) | `data/raw/gtk_structures/` | **Required** | `06_build_structural_features.py` |
| 6 | **Till geochemistry** (Au, As, Sb, Te, Bi, W, Cu, Co, Ni, S) | Direct/pathfinder geochemical anomalies | Points or grid (CSV+coords / GPKG / GeoTIFF) | `data/raw/gtk_till_geochemistry/` | **Required** | `07_glacial_vector_correct_till.py` |
| 7 | **Glacial flow / Quaternary / surficial geology** | Vector till anomalies up-ice to bedrock source; avoid chasing transported anomalies | Vector polygons + flow lines/azimuths | `data/raw/gtk_quaternary/` | **Required (for #6 to be trustworthy)** | `07_glacial_vector_correct_till.py` |
| 8 | **DEM / topography** | Terrain-derived lineaments; access/logistics; context | Raster grid (GeoTIFF) | `data/raw/dem/` | **Required** | `06_build_structural_features.py` |

## Optional but valuable geophysics

| # | Dataset | Why | Format | Place under | Consumed by |
|---|---------|-----|--------|-------------|-------------|
| 9 | **Gravity** | Density contrasts, deep structure, mafic/ultramafic bodies | Raster grid (GeoTIFF) | `data/raw/gtk_gravity/` | `05_load_gtk_layers.py` |
| 10 | **Airborne EM** | Conductors (sulphides, graphitic/carbonaceous units) | Raster grid (GeoTIFF) | `data/raw/gtk_em/` | `05_load_gtk_layers.py` |
| 11 | **Radiometrics (K, U, Th)** | Alteration/lithology discrimination (e.g. K-enrichment) | Raster grid (GeoTIFF) | `data/raw/gtk_radiometrics/` | `05_load_gtk_layers.py` |

## Restriction / availability layers (also needed; Step 1 placeholder already set up)

| # | Dataset | Why | Place under | Consumed by |
|---|---------|-----|-------------|-------------|
| 12 | **Natura 2000** | Statutorily restricted ground | `data/raw/restrictions/natura2000/` | `02b` (future), `11_rank_real_targets.py` |
| 13 | **Protected areas / nature reserves** | Restricted ground | `data/raw/restrictions/protected_areas/` | `02b` (future), `11_rank_real_targets.py` |
| 14 | **Sámi homeland area** | Social/legal sensitivity | `data/raw/restrictions/sami_homeland/` | `02b` (future), `11_rank_real_targets.py` |
| 15 | **National parks / wilderness** | Restricted ground | `data/raw/restrictions/national_parks/` | `02b` (future) |
| 16 | **Water bodies / lakes** | Non-pursuable ground; mask | `data/raw/restrictions/water_bodies/` | `02b` (future) |
| 17 | **Roads / access / infrastructure** | Logistics scoring; avoid urban/infra | `data/raw/infrastructure/` | `11_rank_real_targets.py` |
| 18 | **Tukes cadastre updates** | Keep legal mask current (Step 1 already automates this) | `data/raw/tukes_extracted/` | `02_mask_taken_areas.py` |

---

## Suggested sources

- **GTK** (Geological Survey of Finland) — Hakku service / GTK data portal / WFS:
  bedrock geology, mineral deposits (FODD / mineral occurrence DB), airborne
  geophysics (magnetics, EM, radiometrics), gravity, till geochemistry.
- **SYKE / Finnish Environment Institute** & **Metsähallitus** — protected areas,
  Natura 2000, national parks.
- **NLS / MML (National Land Survey)** — DEM, topographic database, water bodies,
  roads/infrastructure.
- **Tukes** — mining-register cadastre (already automated in Step 1).

> Record every source URL, download date, and licence in a metadata note when you
> add a dataset, so the pipeline stays reproducible and auditable.

## Modelling principles to carry into Step 2 (do not violate)

- **Unknown land is not barren.** Background cells are *unlabelled*, not negative.
- **Known deposits are positive labels**; treat minor showings separately if possible.
- Use **positive-unlabelled / semi-supervised** logic, not naive 0/1 classification.
- Use **spatial cross-validation** (leave-one-district-out), never random splits.
- **Validate by hiding known deposits** and checking the model rediscovers them
  (top-k area capture), and **compare against simple baselines** (e.g.
  distance-to-major-shear) — ML must beat them to earn its place.
- **Require multi-layer convergence**: structure + geophysics + geochemistry + legal
  openness. **Kill single-signal targets.**
- Use **SHAP / feature importance** for explainability.
- **Export everything to EPSG:3067 GeoPackages/GeoTIFFs** so a geologist can inspect
  it in QGIS.
