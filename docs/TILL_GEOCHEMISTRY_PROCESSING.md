# Till Geochemistry Processing — rules & glacial-shift ablation

Finland's bedrock is blanketed by glacial till. Till geochemical anomalies sit
**down-ice** of their bedrock source, so raw till coordinates are **not** the target
location. This document fixes how till is processed (when data is supplied) and why we
ablate the glacial shift rather than hard-code one.

> Status: **no till geochemistry is loaded yet** (GTK Hakku data not supplied). The
> `till_au_clr / as / sb / bi` features are NULL and `11c_till_shift_ablation.py`
> reports 0 samples processed. The rules below are implemented and ready.

## 1. Detection limits

- Values below detection limit (BDL) → **half the detection limit** (per element, if a
  detection-limit column exists). Never zero, never dropped silently.

## 2. Compositional transform (CLR)

- Apply the **centred log-ratio (CLR)** across the element suite where mathematically
  valid (all-positive composition after BDL handling).
- If CLR is invalid (non-positive values remain), **fall back to log10** and report why.
- Implemented in `11c_till_shift_ablation.py: clr_transform()` (CLR rows sum to ~0,
  unit-checked).

## 3. Glacial-transport ablation (never a single hard-coded shift)

Build multiple up-ice-shifted versions of each till sample and let validation pick:

| version | up-ice shift |
|---------|--------------|
| raw | 0 m |
| short | 500 m |
| medium | 1 km |
| long | 2 km |
| optional | 5 km (only if streamlined/drumlin data exists) |

**Up-ice direction** = opposite the regional ice-flow azimuth. Configured in
`configs/config.yaml: till_shift.ice_flow_to_azimuth_deg` (default **135°**,
i.e. ice/till moved toward the SE, so source is toward the NW). This default is
**PROVISIONAL** — replace with a real striation / ice-flow / streamlined-landform layer.

### Terrain-aware shift (when glacial-landform data exists)

- ribbed moraine / ice-divide zones: **50–500 m**
- drumlin / streamlined moraine: **1–5 km**
- unknown terrain: keep **raw + all shifts**, mark **low confidence**
  (`glacial_correction_confidence`).

## 4. How the ablation is judged

Each shifted till layer becomes a feature version. `11b` compares which shift best
captures known orogenic-gold deposits (top-k capture). The winning shift is data-driven,
not assumed. If no shift beats raw, we keep raw and flag low glacial confidence.

## 5. Pathfinder elements

For orogenic gold we process Au plus pathfinders **As, Sb, Bi** (and, when available,
Te, W, Cu, Co, Ni, S). Pathfinders extend the geochemical footprint of buried systems.
