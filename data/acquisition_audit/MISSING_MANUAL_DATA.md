# Manual Data Acquisition Checklist

Only rows with status `manual_required`, `failed`, or `not_found` are listed here.


## Core geology

- [ ] **Dykes if available**
  - Status: `manual_required`
  - Source: https://hakku.gtk.fi
  - Reason: Automatic source-data download is not configured or not available.
  - Next action: Search GTK Hakku/DigiKP for dyke layers clipped to CLGB.
- [ ] **Lithological contacts if available**
  - Status: `manual_required`
  - Source: https://gtkdata.gtk.fi/arcgis/rest/services/GTK_Bedrock_and_Superficial_Geology/MapServer/3
  - Reason: Automatic source-data download is not configured or not available.
  - Next action: Derive contacts after authoritative bedrock polygons are finalized.

## Geophysics

- [ ] **GTK aeromagnetic TMI**
  - Status: `manual_required`
  - Source: https://gtkdata.gtk.fi/arcgis/rest/services/MDaE/Geophysics/MapServer/63
  - Reason: Only WMS visualization discovered automatically; source grid not downloaded.
  - Next action: Obtain source grid from GTK Hakku or WCS; WMS map image is not adequate for modelling.
- [ ] **Magnetic 1VD or raw TMI suitable for derivative calculation**
  - Status: `manual_required`
  - Source: https://gtkdata.gtk.fi/arcgis/rest/services/MDaE/Geophysics/MapServer/63
  - Reason: Only WMS visualization discovered automatically; source grid not downloaded.
  - Next action: Obtain source TMI or 1VD grid, not a rendered WMS layer.
- [ ] **Magnetic analytic signal if available**
  - Status: `manual_required`
  - Source: https://hakku.gtk.fi
  - Reason: Automatic source-data download is not configured or not available.
  - Next action: Confirm whether GTK publishes analytic signal; otherwise derive from TMI.
- [ ] **Magnetic tilt derivative if available**
  - Status: `manual_required`
  - Source: https://gtkdata.gtk.fi/arcgis/rest/services/MDaE/Geophysics/MapServer/63
  - Reason: Automatic source-data download is not configured or not available.
  - Next action: Derive locally after source TMI grid is acquired.
- [ ] **Bouguer gravity**
  - Status: `manual_required`
  - Source: https://gtkdata.gtk.fi/arcgis/rest/services/MDaE/Geophysics/MapServer/58
  - Reason: Only WMS visualization discovered automatically; source grid not downloaded.
  - Next action: Obtain source Bouguer grid; WMS map image is not adequate for modelling.
- [ ] **Gravity gradient / upward continuation if available**
  - Status: `manual_required`
  - Source: https://gtkdata.gtk.fi/arcgis/rest/services/MDaE/Geophysics/MapServer/58
  - Reason: Automatic source-data download is not configured or not available.
  - Next action: Derive locally after Bouguer source grid is acquired.
- [ ] **Radiometric K, Th, U if available**
  - Status: `manual_required`
  - Source: https://gtkdata.gtk.fi/arcgis/rest/services/MDaE/Geophysics/MapServer/72
  - Reason: Automatic source-data download is not configured or not available.
  - Next action: Obtain source K/Th/U grids; WMS rendered layers are not adequate.
- [ ] **EM/electromagnetic data if publicly available**
  - Status: `manual_required`
  - Source: https://gtkdata.gtk.fi/arcgis/rest/services/MDaE/Geophysics/MapServer/66
  - Reason: Automatic source-data download is not configured or not available.
  - Next action: Obtain source EM grids if available; WMS rendered layers are not adequate.

## Geochemistry

- [ ] **GTK till Bi**
  - Status: `manual_required`
  - Source: https://hakku.gtk.fi
  - Reason: Not found in automatically discovered till WFS layers.
  - Next action: No Bi field was found in discovered regional till layers; confirm in Hakku or with GTK and do not substitute stream-sediment Bi.
- [ ] **Bedrock/lithogeochemistry if available**
  - Status: `manual_required`
  - Source: https://hakku.gtk.fi
  - Reason: Automatic source-data download is not configured or not available.
  - Next action: Search Hakku for lithogeochemistry samples clipped to CLGB.

## Glacial/regolith

- [ ] **Till cover / drift thickness if available**
  - Status: `manual_required`
  - Source: https://gtkdata.gtk.fi/arcgis/rest/services/Maapeitepaksuus_1m/MapServer
  - Reason: Automatic source-data download is not configured or not available.
  - Next action: Obtain source grid, not a rendered WMS layer.
- [ ] **Peat/bog/wetland polygons**
  - Status: `manual_required`
  - Source: https://www.syke.fi/en/open-information/open-data
  - Reason: Automatic source-data download is not configured or not available.
  - Next action: Download wetland/peat/bog polygons from SYKE or NLS and clip to CLGB.
- [ ] **DEM/elevation**
  - Status: `manual_required`
  - Source: https://www.maanmittauslaitos.fi/en/e-services/open-data-file-download-service
  - Reason: Automatic source-data download is not configured or not available.
  - Next action: Download DEM tiles covering the CLGB and mosaic/clip.
- [ ] **Slope**
  - Status: `manual_required`
  - Source: https://www.maanmittauslaitos.fi/en/e-services/open-data-file-download-service
  - Reason: Automatic source-data download is not configured or not available.
  - Next action: Derive from DEM after source elevation is acquired.
- [ ] **Water bodies**
  - Status: `manual_required`
  - Source: https://www.maanmittauslaitos.fi/en/e-services/open-data-file-download-service
  - Reason: Automatic source-data download is not configured or not available.
  - Next action: Download lakes/rivers from NLS Topographic Database or SYKE; groundwater is not a water-body substitute.

## Deposits/training labels

- [ ] **Drillholes if available**
  - Status: `manual_required`
  - Source: https://hakku.gtk.fi
  - Reason: Automatic source-data download is not configured or not available.
  - Next action: Download drillhole collars/intervals if public for CLGB prospects.
- [ ] **Historical exploration reports if downloadable**
  - Status: `manual_required`
  - Source: https://hakku.gtk.fi
  - Reason: Automatic source-data download is not configured or not available.
  - Next action: Manually retrieve and index Hakku exploration reports for label QA.

## Restrictions/social/environment

- [ ] **Wilderness areas**
  - Status: `manual_required`
  - Source: https://www.syke.fi/en/open-information/open-data
  - Reason: Automatic source-data download is not configured or not available.
  - Next action: Download wilderness-area polygons and clip to CLGB.
- [ ] **Water bodies**
  - Status: `manual_required`
  - Source: https://www.maanmittauslaitos.fi/en/e-services/open-data-file-download-service
  - Reason: Automatic source-data download is not configured or not available.
  - Next action: Download surface water polygons; groundwater layer does not satisfy this dataset.

## Commercial/infrastructure

- [ ] **Roads**
  - Status: `manual_required`
  - Source: https://vayla.fi/en/transport-network/data/digiroad/open-data
  - Reason: Automatic source-data download is not configured or not available.
  - Next action: Download Digiroad roads and derive distance raster.
- [ ] **Railways**
  - Status: `manual_required`
  - Source: https://www.maanmittauslaitos.fi/en/e-services/open-data-file-download-service
  - Reason: Automatic source-data download is not configured or not available.
  - Next action: Download railway vectors and derive distance raster.
- [ ] **Power lines if available**
  - Status: `manual_required`
  - Source: https://data.fingrid.fi/en/
  - Reason: Automatic source-data download is not configured or not available.
  - Next action: Download transmission/distribution line data if public.
- [ ] **Towns**
  - Status: `manual_required`
  - Source: https://stat.fi/org/avoindata/paikkatietoaineistot_en.html
  - Reason: Automatic source-data download is not configured or not available.
  - Next action: Download settlement/town layer and derive distances.
- [ ] **Distance-to-infrastructure layers**
  - Status: `manual_required`
  - Source: https://vayla.fi/en/transport-network/data/digiroad/open-data
  - Reason: Automatic source-data download is not configured or not available.
  - Next action: Derive after roads, rail, power, and towns are acquired.