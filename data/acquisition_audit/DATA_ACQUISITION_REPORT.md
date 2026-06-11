# GEOARB Finland Data Acquisition Audit

Generated: 2026-06-10T12:07:46+00:00
AOI source: `data/processed/clgb_aoi.gpkg`

This audit finds official public sources, downloads selected queryable GTK WFS/REST source layers, and validates local files. It does not run ML and does not create probability surfaces.

## Register Summary

- Total dataset rows: 63
- Status counts: {"already_exists": 22, "downloaded": 15, "manual_required": 26}
- GTK geophysics discovery: `data/acquisition_audit/GTK_GEOPHYSICS_LAYER_DISCOVERY.json`
- Selected GTK geophysics service: `MDaE/20250205_Geophysics`
- GTK geophysics layers parsed safely: 76

## Validation Checks

- File existence checked for every configured local path.
- Vector CRS, feature count, bounds, and AOI intersection checked with GeoPandas.
- Raster CRS, dimensions, bounds, and AOI intersection checked with Rasterio when raster files exist.
- Missing WMS-only geophysical render layers remain manual because rendered map images are not source grids for modelling.

## Data Codex downloaded
- `data/raw/gtk/glacial_lineations.gpkg`
- `data/raw/gtk/glacial_striae.gpkg`
- `data/raw/gtk/glaciofluvial_moraine_formations.gpkg`
- `data/raw/gtk/stream_sediment_geochemistry.gpkg`
- `data/raw/gtk/surficial_geology_50k.gpkg`
- `data/raw/gtk/till_geochemistry_almr_511p.gpkg`
- `data/raw/gtk/till_geochemistry_almr_519u.gpkg`
- `data/raw/gtk/till_geochemistry_supraregional.gpkg`

## Data already present
- `data/processed/clgb_aoi.gpkg`
- `data/processed/clgb_positive_labels.gpkg`
- `data/processed/tukes_all_rights.gpkg`
- `data/processed/tukes_rights_classified.gpkg`
- `data/raw/gtk/bedrock.gpkg`
- `data/raw/gtk/fodd_precious_metals.gpkg`
- `data/raw/gtk/gold_mines.gpkg`
- `data/raw/gtk/structures.gpkg`
- `data/raw/restrictions/natura2000/natura2000.gpkg`
- `data/raw/restrictions/protected_areas/protected_areas.gpkg`
- `data/raw/restrictions/water_bodies/groundwater.gpkg`

## Data user must manually obtain
- **Dykes if available** (Core geology): Automatic source-data download is not configured or not available. Next: Search GTK Hakku/DigiKP for dyke layers clipped to CLGB. Source: https://hakku.gtk.fi
- **Lithological contacts if available** (Core geology): Automatic source-data download is not configured or not available. Next: Derive contacts after authoritative bedrock polygons are finalized. Source: https://gtkdata.gtk.fi/arcgis/rest/services/GTK_Bedrock_and_Superficial_Geology/MapServer/3
- **GTK aeromagnetic TMI** (Geophysics): Only WMS visualization discovered automatically; source grid not downloaded. Next: Obtain source grid from GTK Hakku or WCS; WMS map image is not adequate for modelling. Source: https://gtkdata.gtk.fi/arcgis/rest/services/MDaE/Geophysics/MapServer/63
- **Magnetic 1VD or raw TMI suitable for derivative calculation** (Geophysics): Only WMS visualization discovered automatically; source grid not downloaded. Next: Obtain source TMI or 1VD grid, not a rendered WMS layer. Source: https://gtkdata.gtk.fi/arcgis/rest/services/MDaE/Geophysics/MapServer/63
- **Magnetic analytic signal if available** (Geophysics): Automatic source-data download is not configured or not available. Next: Confirm whether GTK publishes analytic signal; otherwise derive from TMI. Source: https://hakku.gtk.fi
- **Magnetic tilt derivative if available** (Geophysics): Automatic source-data download is not configured or not available. Next: Derive locally after source TMI grid is acquired. Source: https://gtkdata.gtk.fi/arcgis/rest/services/MDaE/Geophysics/MapServer/63
- **Bouguer gravity** (Geophysics): Only WMS visualization discovered automatically; source grid not downloaded. Next: Obtain source Bouguer grid; WMS map image is not adequate for modelling. Source: https://gtkdata.gtk.fi/arcgis/rest/services/MDaE/Geophysics/MapServer/58
- **Gravity gradient / upward continuation if available** (Geophysics): Automatic source-data download is not configured or not available. Next: Derive locally after Bouguer source grid is acquired. Source: https://gtkdata.gtk.fi/arcgis/rest/services/MDaE/Geophysics/MapServer/58
- **Radiometric K, Th, U if available** (Geophysics): Automatic source-data download is not configured or not available. Next: Obtain source K/Th/U grids; WMS rendered layers are not adequate. Source: https://gtkdata.gtk.fi/arcgis/rest/services/MDaE/Geophysics/MapServer/72
- **EM/electromagnetic data if publicly available** (Geophysics): Automatic source-data download is not configured or not available. Next: Obtain source EM grids if available; WMS rendered layers are not adequate. Source: https://gtkdata.gtk.fi/arcgis/rest/services/MDaE/Geophysics/MapServer/66
- **GTK till Bi** (Geochemistry): Not found in automatically discovered till WFS layers. Next: No Bi field was found in discovered regional till layers; confirm in Hakku or with GTK and do not substitute stream-sediment Bi. Source: https://hakku.gtk.fi
- **Bedrock/lithogeochemistry if available** (Geochemistry): Automatic source-data download is not configured or not available. Next: Search Hakku for lithogeochemistry samples clipped to CLGB. Source: https://hakku.gtk.fi
- **Till cover / drift thickness if available** (Glacial/regolith): Automatic source-data download is not configured or not available. Next: Obtain source grid, not a rendered WMS layer. Source: https://gtkdata.gtk.fi/arcgis/rest/services/Maapeitepaksuus_1m/MapServer
- **Peat/bog/wetland polygons** (Glacial/regolith): Automatic source-data download is not configured or not available. Next: Download wetland/peat/bog polygons from SYKE or NLS and clip to CLGB. Source: https://www.syke.fi/en/open-information/open-data
- **DEM/elevation** (Glacial/regolith): Automatic source-data download is not configured or not available. Next: Download DEM tiles covering the CLGB and mosaic/clip. Source: https://www.maanmittauslaitos.fi/en/e-services/open-data-file-download-service
- **Slope** (Glacial/regolith): Automatic source-data download is not configured or not available. Next: Derive from DEM after source elevation is acquired. Source: https://www.maanmittauslaitos.fi/en/e-services/open-data-file-download-service
- **Water bodies** (Glacial/regolith): Automatic source-data download is not configured or not available. Next: Download lakes/rivers from NLS Topographic Database or SYKE; groundwater is not a water-body substitute. Source: https://www.maanmittauslaitos.fi/en/e-services/open-data-file-download-service
- **Drillholes if available** (Deposits/training labels): Automatic source-data download is not configured or not available. Next: Download drillhole collars/intervals if public for CLGB prospects. Source: https://hakku.gtk.fi
- **Historical exploration reports if downloadable** (Deposits/training labels): Automatic source-data download is not configured or not available. Next: Manually retrieve and index Hakku exploration reports for label QA. Source: https://hakku.gtk.fi
- **Wilderness areas** (Restrictions/social/environment): Automatic source-data download is not configured or not available. Next: Download wilderness-area polygons and clip to CLGB. Source: https://www.syke.fi/en/open-information/open-data
- **Water bodies** (Restrictions/social/environment): Automatic source-data download is not configured or not available. Next: Download surface water polygons; groundwater layer does not satisfy this dataset. Source: https://www.maanmittauslaitos.fi/en/e-services/open-data-file-download-service
- **Roads** (Commercial/infrastructure): Automatic source-data download is not configured or not available. Next: Download Digiroad roads and derive distance raster. Source: https://vayla.fi/en/transport-network/data/digiroad/open-data
- **Railways** (Commercial/infrastructure): Automatic source-data download is not configured or not available. Next: Download railway vectors and derive distance raster. Source: https://www.maanmittauslaitos.fi/en/e-services/open-data-file-download-service
- **Power lines if available** (Commercial/infrastructure): Automatic source-data download is not configured or not available. Next: Download transmission/distribution line data if public. Source: https://data.fingrid.fi/en/
- **Towns** (Commercial/infrastructure): Automatic source-data download is not configured or not available. Next: Download settlement/town layer and derive distances. Source: https://stat.fi/org/avoindata/paikkatietoaineistot_en.html
- **Distance-to-infrastructure layers** (Commercial/infrastructure): Automatic source-data download is not configured or not available. Next: Derive after roads, rail, power, and towns are acquired. Source: https://vayla.fi/en/transport-network/data/digiroad/open-data

## Top 5 missing blockers before probability modelling
1. GTK aeromagnetic TMI - Obtain source grid from GTK Hakku or WCS; WMS map image is not adequate for modelling.
2. Magnetic 1VD or raw TMI suitable for derivative calculation - Obtain source TMI or 1VD grid, not a rendered WMS layer.
3. Bouguer gravity - Obtain source Bouguer grid; WMS map image is not adequate for modelling.
4. Gravity gradient / upward continuation if available - Derive locally after Bouguer source grid is acquired.
5. GTK till Bi - No Bi field was found in discovered regional till layers; confirm in Hakku or with GTK and do not substitute stream-sediment Bi.

## Can we build a probability surface now?

**No.** The audit now has several official GTK till/regolith source layers and the existing legal/geology/label layers, but source geophysical grids, DEM/slope, surface-water/wetland masks, and drillhole/report QA are still missing or manual. A probability-first prospectivity surface would still be underconstrained and would risk presenting availability/geology proxies as mineral probability.
