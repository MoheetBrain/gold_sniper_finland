# Local Geophysics Validation Report

GDAL driver note: ECW/JP2ECW drivers are absent from this GDAL build.

## Files Checked

| file | readable | CRS | bounds | overlap CLGB | resolution | bands | numeric/display | modelling | visual-only |
|------|----------|-----|--------|--------------|------------|-------|-----------------|-----------|-------------|
| `Fenno_Bouguer_Fin_ETRS89_TM35FIN.grd` | NO |  |  | UNKNOWN (0.0%) |  |  | unknown | NO | NO |
| `BA_FIN.XYZ` | NO; parsed manually | WGS84 / Gauss-Krueger CM 21E false easting 1500000 | (63058.566, 6543099.178, 731587.177, 7774984.874) | YES (100.0%) | 2500 x 2500 m | 1 | numeric XYZ Bouguer anomaly | YES | NO |
| `Fenno_Bouguer_FIN_ETRS89_TM35FIN.ecw` | NO | EPSG:3067 | (38750.0, 6476250.0, 816250.0, 7826250.0) | YES (100.0%) | 500.0 | 4 | rendered RGB/greyscale display from XML metadata | NO | YES |
| `aeromagnetic_anomaly_grey_epsg3067.ecw` | NO | EPSG:3067 | (61475.0, 6559275.0, 739425.0, 7787975.0) | YES (100.0%) | 50.0 | 4 | rendered RGB/greyscale display from XML metadata | NO | YES |
| `magnetics_numeric` | NO |  |  | UNKNOWN (0.0%) |  |  | no numeric magnetic grid supplied yet | NO | NO |

## Numeric Statistics

| file | min | max | mean | nodata | error / driver message |
|------|-----|-----|------|--------|------------------------|
| `Fenno_Bouguer_Fin_ETRS89_TM35FIN.grd` | nan | nan | nan |  | RasterioIOError: '/Users/mk/AL_THAHAB/gold_sniper/data/raw/gtk/gravity/Fenno_Bouguer_Fin_ETRS89_TM35FIN.grd' not recognized as being in a supported file format. / gdalinfo: ERROR 4: `/Users/mk/AL_THAHAB/gold_sniper/data/raw/gtk/gravity/Fenno_Bouguer_Fin_ETRS89_TM35FIN.grd' not recognized as being in a supported file format. gdalinfo failed - unable to open '/Users/mk/AL_THAHAB/gold_sniper/data/raw/gtk/gravity/Fenno_Bouguer_Fin_ETRS89_TM35FIN.grd'. |
| `BA_FIN.XYZ` | -62.23 | 48.45 | -10.67764943024605 |  | GDAL cannot open XYZ directly: ERROR 1: Maximum number of characters allowed reached. gdalinfo failed - unable to open '/Users/mk/AL_THAHAB/gold_sniper/data/raw/gtk/gravity/BA_FIN.XYZ'. |
| `Fenno_Bouguer_FIN_ETRS89_TM35FIN.ecw` | nan | nan | nan |  | RasterioIOError: '/Users/mk/AL_THAHAB/gold_sniper/data/raw/gtk/gravity/Fenno_Bouguer_FIN_ETRS89_TM35FIN.ecw' not recognized as being in a supported file format. / gdalinfo: ERROR 4: `/Users/mk/AL_THAHAB/gold_sniper/data/raw/gtk/gravity/Fenno_Bouguer_FIN_ETRS89_TM35FIN.ecw' not recognized as being in a supported file format. gdalinfo failed - unable to open '/Users/mk/AL_THAHAB/gold_sniper/data/raw/gtk/gravity/Fenno_Bouguer_FIN_ETRS89_TM35FIN.ecw'. / ECW/JP2ECW drivers are absent from this GDAL build. |
| `aeromagnetic_anomaly_grey_epsg3067.ecw` | nan | nan | nan |  | RasterioIOError: '/Users/mk/AL_THAHAB/gold_sniper/data/raw/gtk/magnetics/aeromagnetic_anomaly_grey_epsg3067.ecw' not recognized as being in a supported file format. / gdalinfo: ERROR 4: `/Users/mk/AL_THAHAB/gold_sniper/data/raw/gtk/magnetics/aeromagnetic_anomaly_grey_epsg3067.ecw' not recognized as being in a supported file format. gdalinfo failed - unable to open '/Users/mk/AL_THAHAB/gold_sniper/data/raw/gtk/magnetics/aeromagnetic_anomaly_grey_epsg3067.ecw'. / ECW/JP2ECW drivers are absent from this GDAL build. |
| `magnetics_numeric` | nan | nan | nan |  | Drop GDAL-readable numeric magnetic anomaly grids into this directory. |

## Decisions

- Gravity: the preferred Geosoft `.grd` is present but not readable by this GDAL build. The `BA_FIN.XYZ` text grid is numeric, overlaps the CLGB AOI, and is suitable for the interim gravity-gradient feature.
- Gravity ECW: metadata says it is an 8-bit, 4-band ECW display product; GDAL also cannot open ECW in this environment.
- Magnetics: the ECW metadata says 4 bands, 8-bit Red/Green/Blue/opacity. That is a rendered greyscale/RGBA display, not a numeric magnetic anomaly grid. It is visual-only and not suitable for `mag_1vd` or `mag_low_in_high_proxy`.
- Future numeric magnetics: place GDAL-readable numeric grids under `data/raw/gtk/magnetics_numeric/`; this validator will include them automatically.
