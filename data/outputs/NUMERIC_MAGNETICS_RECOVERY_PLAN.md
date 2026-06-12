# Numeric Magnetics Recovery Plan

Current status: the local `aeromagnetic_anomaly_grey_epsg3067.ecw` is not usable for modelling. GDAL cannot open it in this environment, and its XML metadata says 4 bands, 8-bit unsigned integer, Red/Green/Blue/AllOpacity. That is a rendered display product, not a defensible numeric magnetic-anomaly grid.

## Required Dataset

Need a numeric magnetic anomaly grid for the CLGB AOI, preferably total magnetic intensity anomaly / magnetic anomalies, RTP/VRTP if available, or a defensible source grid from which derivatives can be computed.

Acceptable formats:

- GeoTIFF: `.tif`, `.tiff`
- ERDAS IMG: `.img`
- Geosoft grid: `.grd` plus any sidecar metadata
- ESRI ASCII grid: `.asc`
- XYZ text grid: `.xyz`, with x/y/value columns and CRS metadata

Reject:

- PNG/JPG/PDF map exports
- ECW products whose metadata says RGB/greyscale/opacity bands
- Any 3-band or 4-band 8-bit Red/Green/Blue/Alpha display raster
- Legend images

## Official Source 1: GTK Hakku

Portal: https://hakku.gtk.fi

Manual search terms to try:

- `Aerogeophysical low altitude surveys`
- `Magneettiset matalalentomittaukset`
- `Magnetic anomalies`
- `Magneettiset anomaliat`
- `aeromagnetic anomaly grid`
- `magnetic anomaly grid 1 km`
- `magnetic anomaly 50 m grid`

Expected product wording:

- Aerogeophysical low altitude surveys
- Magnetic anomalies
- Total magnetic intensity / magnetic anomaly
- Grid density 1 km, 500 m, 200 m, 100 m or 50 m
- Units in nT or equivalent magnetic-field anomaly units

Download target folder:

`data/raw/gtk/magnetics_numeric/`

Preferred filename pattern:

`data/raw/gtk/magnetics_numeric/gtk_magnetic_anomaly_numeric_<resolution>_<crs>.<ext>`

## Official Source 2: GTK ArcGIS Geophysics Inventory

Inventory service:

https://gtkdata.gtk.fi/arcgis/rest/services/MDaE/Geophysics/MapServer

Relevant official layers:

- `Aerogeophysical low altitude surveys` group
- `Magnetic` group
- `Magnetic anomalies` raster layer, MapServer layer 65:
  https://gtkdata.gtk.fi/arcgis/rest/services/MDaE/Geophysics/MapServer/65

Use this service to confirm the official layer name, coverage and metadata. Do not treat `Export Map` image output as numeric source data unless the export is a real single-band numeric raster with preserved values, CRS and units. In practice, ArcGIS MapServer exports are usually rendered images and should be treated as visual context only.

## Possible Detailed Survey Sources

The same official geophysics inventory also lists detailed aeromagnetic survey raster layers, often named as `.img`, under `Detailed aeromagnetic surveys`.

Examples visible in the official inventory include:

- `Kolari_aeromagnetic.img`
- `Kolvakero_aeromagnetic.img`
- `Levijoki_aeromagnetic.img`
- `Petajaselka_aeromagnetic.img`
- `Sokli_aeromagnetic.img`
- `Tipasjarvi_aeromagnetic.img`

Use these only if their coverage overlaps the CLGB AOI and they are downloadable as source numeric rasters, not just rendered map-service layers.

## Verification Commands

After dropping files into `data/raw/gtk/magnetics_numeric/`, run:

```bash
/Users/mk/miniconda3/envs/geoarb/bin/python scripts/21_validate_local_geophysics.py
```

Then inspect:

```bash
cat data/outputs/LOCAL_GEOPHYSICS_VALIDATION_REPORT.md
```

Direct GDAL/rasterio checks:

```bash
/Users/mk/miniconda3/envs/geoarb/bin/gdalinfo data/raw/gtk/magnetics_numeric/<file>
```

```bash
/Users/mk/miniconda3/envs/geoarb/bin/python - <<'PY'
import rasterio
import numpy as np
path = "data/raw/gtk/magnetics_numeric/<file>"
with rasterio.open(path) as ds:
    print("driver", ds.driver)
    print("crs", ds.crs)
    print("bounds", ds.bounds)
    print("res", ds.res)
    print("bands", ds.count)
    print("dtypes", ds.dtypes)
    print("descriptions", ds.descriptions)
    arr = ds.read(1, masked=True, out_shape=(min(512, ds.height), min(512, ds.width)))
    print("min/max/mean", float(arr.min()), float(arr.max()), float(arr.mean()))
PY
```

## Numeric-vs-Display Decision Rules

Accept as numeric if:

- GDAL/rasterio can open it.
- CRS is present or recoverable, ideally EPSG:3067.
- It overlaps the CLGB AOI.
- It is single-band or otherwise documented numeric bands.
- Values are not simply 0-255 RGB display values.
- Band descriptions/metadata refer to magnetic anomaly, TMI, RTP, VRTP or nT values.

Reject or mark visual-only if:

- `bands` is 3 or 4 with `uint8`.
- Band names/descriptions are Red, Green, Blue, Alpha or AllOpacity.
- Min/max are 0-255 and metadata indicates RGB/greyscale.
- Source file is a legend, PNG/JPG/PDF, or ECW display map.

## Next Pipeline Step After Recovery

Once a numeric magnetic grid is validated:

1. Update `scripts/06c_process_magnetics.py` to prefer `data/raw/gtk/magnetics_numeric/` over the visual ECW.
2. Clip/resample to the CLGB 2 km grid.
3. Compute defensible `mag_1vd` only if source resolution, CRS and units are adequate.
4. Compute `mag_low_in_high_proxy` using transparent local-vs-regional filtering.
5. Rebuild `feature_stack_minimal_2km.parquet`.
6. Rerun Step 2 validation and ablation.

No target memos are allowed until numeric magnetics are either acquired or explicitly confirmed unavailable, and validation beats the baseline beyond the current partial result.
