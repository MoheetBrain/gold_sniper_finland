#!/Users/mk/miniconda3/envs/geoarb/bin/python
import geopandas as gpd
import pandas as pd
import numpy as np

def run_diagnostics():
    print("--- DIAGNOSTIC: COORDINATES & MATH ---")
    
    # 1. Load the clusters and AOI
    clusters = gpd.read_file("data/outputs/clean_open_clusters_2km.gpkg")
    aoi = gpd.read_file("data/processed/aoi_grid.gpkg")
    csv_data = pd.read_csv("data/outputs/maps_command_center/target_block_coordinates.csv")
    
    print(f"Clusters CRS: {clusters.crs}")
    print(f"AOI CRS: {aoi.crs}")
    
    if clusters.crs.to_epsg() != 3067:
        print("ERROR: Clusters not in EPSG:3067")
        return
        
    # 2. Check AOI Bounds
    minx, miny, maxx, maxy = aoi.total_bounds
    print(f"\nAOI Bounds (EPSG:3067):")
    print(f"Easting:  {minx:.1f} to {maxx:.1f} (Width: {(maxx-minx)/1000:.1f} km)")
    print(f"Northing: {miny:.1f} to {maxy:.1f} (Height: {(maxy-miny)/1000:.1f} km)")
    
    # 3. Verify math in CSV against GeoDataFrame
    print("\nVerifying Cluster Math:")
    errors = 0
    for idx, row in csv_data.iterrows():
        c_id = row['cluster_id']
        geom = clusters[clusters['cluster_id'] == c_id].iloc[0].geometry
        
        # Calculate expected
        exp_area_m2 = geom.area
        exp_area_km2 = exp_area_m2 / 1e6
        exp_area_ha = exp_area_m2 / 10000
        exp_centroid = geom.centroid
        exp_bounds = geom.bounds # minx, miny, maxx, maxy
        
        # Check Area
        if not np.isclose(row['area_km2'], exp_area_km2, rtol=1e-4):
            print(f"ERROR ({c_id}): Area km2 mismatch. CSV={row['area_km2']}, Expected={exp_area_km2}")
            errors += 1
        if not np.isclose(row['area_hectares'], exp_area_ha, rtol=1e-4):
            print(f"ERROR ({c_id}): Area ha mismatch. CSV={row['area_hectares']}, Expected={exp_area_ha}")
            errors += 1
            
        # Check Centroid
        if not np.isclose(row['centroid_easting_m'], exp_centroid.x, rtol=1e-5):
            print(f"ERROR ({c_id}): Centroid Easting mismatch.")
            errors += 1
        if not np.isclose(row['centroid_northing_m'], exp_centroid.y, rtol=1e-5):
            print(f"ERROR ({c_id}): Centroid Northing mismatch.")
            errors += 1
            
        # Check bounds
        if not np.isclose(row['bbox_min_easting_m'], exp_bounds[0], rtol=1e-5):
            print(f"ERROR ({c_id}): BBox Min Easting mismatch.")
            errors += 1
        if not np.isclose(row['bbox_max_northing_m'], exp_bounds[3], rtol=1e-5):
            print(f"ERROR ({c_id}): BBox Max Northing mismatch.")
            errors += 1

        # Check if centroid is within AOI
        if not (minx <= exp_centroid.x <= maxx and miny <= exp_centroid.y <= maxy):
            print(f"WARNING ({c_id}): Centroid is outside AOI bounds!")
            errors += 1

    if errors == 0:
        print("All coordinate, area, and bounding box math verified successfully.")
    else:
        print(f"Found {errors} errors in math/coordinates.")
        
    print("\n--- SANITY CHECK: 2km Cell Size ---")
    # A 2km x 2km cell should be exactly 4 km2 and 400 hectares
    cell_area = aoi.geometry.iloc[0].area
    print(f"Single AOI cell area: {cell_area/1e6:.2f} km2 (Should be 4.00 for 2km grid)")
    if not np.isclose(cell_area, 4000000.0, rtol=1e-2):
        print("WARNING: The AOI grid cells are NOT 2km x 2km!")

if __name__ == '__main__':
    run_diagnostics()
