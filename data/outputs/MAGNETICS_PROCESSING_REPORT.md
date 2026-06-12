# Magnetics Processing Report

Magnetics file used: `/Users/mk/AL_THAHAB/gold_sniper/data/raw/gtk/magnetics/aeromagnetic_anomaly_grey_epsg3067.ecw`

## Readability

- Rasterio/GDAL readable: NO
- GDAL driver note: ECW/JP2ECW drivers are absent from this GDAL build.
- Raster/GDAL message: `RasterioIOError: '/Users/mk/AL_THAHAB/gold_sniper/data/raw/gtk/magnetics/aeromagnetic_anomaly_grey_epsg3067.ecw' not recognized as being in a supported file format.; gdalinfo: ERROR 4: `/Users/mk/AL_THAHAB/gold_sniper/data/raw/gtk/magnetics/aeromagnetic_anomaly_grey_epsg3067.ecw' not recognized as being in a supported file format.
gdalinfo failed - unable to open '/Users/mk/AL_THAHAB/gold_sniper/data/raw/gtk/magnetics/aeromagnetic_anomaly_grey_epsg3067.ecw'.`

## Metadata Interpretation

- XML exists: True
- XML bands: 4
- XML pixel depth/type: 8 / unsigned integer
- XML band names: Red, Green, Blue, AllOpacity
- XML bounds: 61475.000000, 6559275.000000, 739425.000000, 7787975.000000

## Decision

- The supplied ECW is a rendered greyscale/RGBA display product, not a defensible numeric magnetic-anomaly grid.
- `mag_1vd` was not created.
- `mag_low_in_high_proxy` was not created.
- `mag_visual_proxy_low_confidence` was not created because ECW pixels cannot be read in this GDAL build; even if readable, it would be a low-confidence visual texture/intensity proxy only.
- Downstream validation must flag `magnetics_low_confidence`.
