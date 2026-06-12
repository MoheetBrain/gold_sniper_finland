# Gravity Processing Report

Bouguer file used: `/Users/mk/AL_THAHAB/gold_sniper/data/raw/gtk/gravity/BA_FIN.XYZ`

## Input Selection

- Preferred Geosoft GRD is present but not readable by this GDAL/rasterio build.
- ECW is not readable here and its sidecar metadata describes an 8-bit display product.
- `BA_FIN.XYZ` is a numeric 2.5 km Bouguer anomaly grid and was used.

## Processing

- Source CRS: WGS84 Gauss-Krueger, central meridian 21E, false easting 1500000.
- Source grid spacing: 2500 m x 2500 m.
- Horizontal gradient magnitude computed on the regular source grid from Bouguer mGal.
- Units for `gravity_gradient`: mGal/km.
- Values sampled to CLGB 2 km cell centroids after CRS transformation.

## Output Summary

- Cells written: 3798
- Cells with non-null gravity_gradient: 3798 (100.0%)
- gravity_gradient min/max/mean: 0.03895 / 5.368 / 1.453 mGal/km

## Limitations

- The Bouguer grid is regional, upward-continued to 500 m, and documented as suitable mainly for shield-scale/regional interpretation.
- Cell values are centroid samples of a 2.5 km source grid on a 2 km modelling grid; they should be treated as broad density-contrast context, not target-scale gravity.
