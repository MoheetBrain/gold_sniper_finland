# Restriction Data Shopping List

**Why this is critical:** Step 1 proves a cell is free of *Tukes mining titles*
(reservations, exploration/mining permits, concessions, claims, gold-panning). That
is **not** the same as legally/practically pursuable. A cell can be free of mining
titles yet sit inside a Natura 2000 site, a national park, the Sámi Homeland, a lake,
or an urban area. **No legal conclusion ("this ground is open") can be drawn until the
layers below are added and intersected with the grid.**

The placeholder `scripts/02b_build_restriction_masks_placeholder.py` already checks for
these under `data/raw/restrictions/<folder>/` and reports what's missing. Once the data
is present, `02b` will be upgraded to actually mask.

Legend: **Required before any reservation decision** = must have it before concluding a
cell is pursuable. **Required before Step 2** = needed (or strongly wanted) before
prospectivity modelling, mainly to avoid wasting modelling effort on unavailable ground.

| # | Layer | Why we need it | Likely source | Download URL (verify) | Format | Required before Step 2? | Required before reservation? | Consuming script |
|---|-------|----------------|---------------|------------------------|--------|-------------------------|------------------------------|------------------|
| 1 | **Natura 2000 (SAC/SPA)** | Statutorily protected habitats; exploration heavily constrained | SYKE (Finnish Environment Institute); EEA EU-wide | syke.fi / Avoin tieto; eea.europa.eu/data-and-maps/data/natura | GPKG/SHP | Recommended | **Yes** | 02b → 11 |
| 2 | **Protected areas / nature reserves** | Conservation areas, mire/old-growth protection programmes | SYKE / Metsähallitus (Suojelualueet) | ckan.ymparisto.fi / Metsähallitus avoin aineisto | GPKG/SHP | Recommended | **Yes** | 02b → 11 |
| 3 | **National parks** | No exploration/mining; hard exclusion | Metsähallitus | metsa.fi / paikkatieto | GPKG/SHP | Recommended | **Yes** | 02b → 11 |
| 4 | **Wilderness areas (erämaa-alueet)** | 12 statutory wilderness areas in Lapland; special regime | Metsähallitus / SYKE | ckan.ymparisto.fi | GPKG/SHP | Recommended | **Yes** | 02b → 11 |
| 5 | **Sámi Homeland area** | Special consultation/consent considerations; reputationally and legally critical in N Lapland | Sámi Parliament (Sámediggi); statutory boundary (Act on the Sámi Parliament) | samediggi.fi; statutory municipality set (Enontekiö, Inari, Utsjoki, N Sodankylä) | GPKG/SHP | **Yes** | **Yes** | 02b → 11 |
| 6 | **Reindeer herding constraint areas** | Reindeer husbandry areas / special herding zones; land-use sensitivity | Paliskuntain yhdistys; MMM | paliskunnat.fi (availability varies) | SHP/GPKG | Optional | Recommended | 02b → 11 |
| 7 | **Water bodies / lakes / rivers** | Cannot site ground targets on open water; trims false open ground | NLS/MML topographic DB; SYKE Ranta10 | tiedostopalvelu.maanmittauslaitos.fi; ckan.ymparisto.fi | GPKG/SHP | **Yes** | Recommended | 02b → 11 |
| 8 | **Urban areas / built-up / infrastructure** | Towns, roads, power lines — not pursuable / logistics | NLS/MML topographic DB (CORINE land cover as proxy) | maanmittauslaitos.fi; SYKE CORINE | GPKG/SHP/raster | Optional | Recommended | 02b → 11 |
| 9 | **Military / restricted zones** | Defence areas exclude access | Finnish Defence Forces / NLS restricted-area data | puolustusvoimat.fi (limited public data) | SHP/GPKG | Optional | **Yes** | 02b → 11 |
| 10 | **Land-use / zoning constraints (maakuntakaava)** | Regional land-use plans may restrict mining | Regional councils (Lapin liitto); SYKE Liiteri | lapinliitto.fi; liiteri.ymparisto.fi | GPKG/SHP | Optional | Recommended | 02b → 11 |

## How to add a layer

1. Create `data/raw/restrictions/<folder>/` using the folder names listed in
   `data/raw/restrictions/README_RESTRICTIONS.md` (e.g. `natura2000/`, `sami_homeland/`).
2. Drop the downloaded vector data inside (any GDAL-readable format).
3. Re-run `python scripts/02b_build_restriction_masks_placeholder.py` to confirm it is
   detected. (The masking upgrade to `02b` consumes them and reprojects to EPSG:3067.)

## Honest status today

- **Zero restriction layers are present.** Every "open" number in Step 1 is
  *Tukes-cadastre-only*.
- The single most important additions for North Lapland specifically are **Sámi
  Homeland (#5)**, **Natura 2000 (#1)**, **national parks/wilderness (#3/#4)** and
  **water bodies (#7)** — these are the layers most likely to remove apparently-open
  cells in the Kittilä–Sodankylä corridor.
- Until they are in, treat "clean-open" as "no mining title here", not "go ahead".

> None of the above is legal advice. URLs change — verify each source and its licence
> before use, and confirm the live legal position with a qualified Finnish adviser.
