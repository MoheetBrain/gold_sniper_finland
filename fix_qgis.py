import re

with open("scripts/13_build_qgis_project.py", "r") as f:
    code = f.read()

# 1. Add aoi_box style
code = code.replace('"default_poly": {"type": "polygon"', '"aoi_box": {"type": "polygon", "fill": "0,0,0,0", "outline": "0,0,0,255", "width": "2.0", "style": "no"},\n    "default_poly": {"type": "polygon"')

# 2. Change AOI context to aoi_box
code = code.replace('"name": "AOI Context", "style": "default_poly"', '"name": "AOI Context", "style": "aoi_box"')

# 3. Add CRS enforcement and dissolve for AOI context
load_logic = """
        try:
            gdf = gpd.read_file(lc["path"])
            if gdf.crs and gdf.crs != "EPSG:3067":
                gdf = gdf.to_crs("EPSG:3067")
            if lc["name"] == "AOI Context":
                gdf = gdf.dissolve() # Just the outer boundary
            loaded_data[lc["name"]] = {"gdf": gdf, "config": lc}
"""
code = code.replace("""
        try:
            gdf = gpd.read_file(lc["path"])
            loaded_data[lc["name"]] = {"gdf": gdf, "config": lc}
""", load_logic)

# 4. Set map bounds
bounds_logic = """
    # Set map limits to AOI bounds
    if "AOI Context" in loaded_data:
        minx, miny, maxx, maxy = loaded_data["AOI Context"]["gdf"].total_bounds
        ax.set_xlim(minx - 5000, maxx + 5000)
        ax.set_ylim(miny - 5000, maxy + 5000)

    plt.title("GeoArb Finland - Context & Legal Status")
"""
code = code.replace('plt.title("GeoArb Finland - Context & Legal Status")', bounds_logic)

with open("scripts/13_build_qgis_project.py", "w") as f:
    f.write(code)

print("Fixed scripts/13_build_qgis_project.py")
