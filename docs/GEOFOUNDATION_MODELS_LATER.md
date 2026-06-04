# Geo Foundation Models — deferred (do NOT use yet)

**Decision: we are NOT using geospatial foundation models (GeoFMs) at this stage.**
This includes TerraMind, Clay, Prithvi, OlmoEarth, Cosmos, and similar.

## Why not now

The current bottleneck is **not** model sophistication. It is:

1. A clean, geology-relevant AOI (CLGB clip — still using a manual envelope, needs GTK).
2. Restriction layers (Natura 2000, protected areas, Sámi Homeland, water) — not yet in.
3. Grid resolution choices (2 km regional / 1 km detail — now in place).
4. **GTK feature ingestion** (bedrock, magnetics, gravity, EM, radiometrics, till
   geochemistry, structures) — not started.

Throwing a foundation model at the problem before these exist would produce
impressive-looking but ungrounded output. We fix the data foundation first.

## What GeoFMs are (and are not) for here

GeoFMs **may** be tested **later**, and **only** as *secondary feature generators*
after the source-grounded baseline works:

- DEM / SAR **lineament & structural extraction** (edges, fabric) to supplement
  magnetic-derivative lineaments.
- **Glacial-landform / surficial classification** (e.g. esker/till mapping) to help
  the glacial-transport correction of till geochemistry.
- Embedding-based **context features** from imagery, used alongside — never instead
  of — GTK geophysics and mineral-system features.

They are **explicitly NOT** for:

- "Finding gold." No model output is evidence of mineralisation.
- Replacing GTK geophysics, till geochemistry, or structural/mineral-system features.
- Being the primary predictor. The baseline must be explainable (XGBoost + SHAP) and
  beat simple baselines (e.g. distance-to-major-shear) on spatial cross-validation
  before any GeoFM feature is considered.

## Gate before any GeoFM work

A GeoFM may be trialled only after **all** of these hold:

1. GTK layers are ingested and standardised (script 05) on the CLGB grid.
2. A source-grounded baseline model (script 09) is trained and validated (script 10).
3. The baseline captures known deposits in the top-k area and beats naive baselines.
4. There is a specific, articulated feature gap a GeoFM could fill (e.g. lineaments).

Until then: source-grounded geology first, foundation models later, and never as the
thing that "finds" gold.
