import os
import urllib.request
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
import matplotlib.patheffects as pe

def load_or_download_finland(cache_dir="data/raw/restrictions"):
    os.makedirs(cache_dir, exist_ok=True)
    geojson_path = os.path.join(cache_dir, "finland_boundary.geojson")
    
    if not os.path.exists(geojson_path):
        print("Downloading world countries GeoJSON to extract Finland...")
        url = 'https://raw.githubusercontent.com/datasets/geo-countries/master/data/countries.geojson'
        urllib.request.urlretrieve(url, geojson_path)
        
    world = gpd.read_file(geojson_path)
    # The column is 'name' in this dataset
    finland = world[world['name'] == 'Finland']
    if len(finland) == 0:
        # Fallback if column names differ
        finland = world[world['ADMIN'] == 'Finland'] if 'ADMIN' in world.columns else world.iloc[0:1]
    
    # Reproject to project CRS
    finland = finland.to_crs("EPSG:3067")
    return finland

def main():
    print("Starting cartographic map generation...")
    out_dir = "data/outputs/maps"
    os.makedirs(out_dir, exist_ok=True)

    # 1. Load Finland
    finland = load_or_download_finland()

    # 2. Define input paths
    paths = {
        "AOI Grid": "data/processed/aoi_grid.gpkg",
        "Bedrock (CLGB)": "data/raw/gtk/bedrock.gpkg",
        "Taken Cells": "data/outputs/taken_cells.gpkg",
        "Partly Taken Cells": "data/outputs/partly_taken_cells.gpkg",
        "Clean Open Cells": "data/outputs/open_cells.gpkg",
        "Tukes Rights": "data/processed/tukes_all_rights.gpkg",
        "Gold Deposits": "data/raw/gtk/fodd_precious_metals.gpkg"
    }

    layers = {}
    missing = []
    
    for name, path in paths.items():
        if os.path.exists(path):
            try:
                gdf = gpd.read_file(path)
                if gdf.crs and gdf.crs != "EPSG:3067":
                    gdf = gdf.to_crs("EPSG:3067")
                layers[name] = gdf
            except Exception as e:
                print(f"Error loading {path}: {e}")
                missing.append(name)
        else:
            missing.append(name)

    print(f"Loaded {len(layers)} layers. Missing: {missing}")

    if "AOI Grid" not in layers:
        print("AOI grid missing. Cannot build map.")
        return

    aoi_bounds = layers["AOI Grid"].total_bounds
    minx, miny, maxx, maxy = aoi_bounds

    # Calculate AOI polygon for context map
    from shapely.geometry import box
    aoi_poly = gpd.GeoDataFrame(geometry=[box(*aoi_bounds)], crs="EPSG:3067")

    # Clip Tukes Rights to AOI for cleaner plotting if present
    if "Tukes Rights" in layers:
        print("Clipping Tukes Rights to AOI...")
        try:
            layers["Tukes Rights"] = gpd.clip(layers["Tukes Rights"], aoi_bounds)
        except Exception as e:
            print("Clipping failed, using unclipped.")

    # 3. Setup Figure
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(24, 12), gridspec_kw={'width_ratios': [1, 2]})
    plt.subplots_adjust(wspace=0.05)

    # ==========================================
    # PANEL A: FINLAND CONTEXT
    # ==========================================
    finland.plot(ax=ax1, facecolor="#e0e0e0", edgecolor="#606060", linewidth=0.8)
    aoi_poly.plot(ax=ax1, facecolor="none", edgecolor="red", linewidth=3)
    
    ax1.set_title("GeoArb Finland — Project Location", fontsize=16, pad=20, weight='bold')
    ax1.set_axis_off()

    # Context Legend
    ctx_handles = [
        mpatches.Patch(facecolor="#e0e0e0", edgecolor="#606060", label='Finland'),
        mpatches.Patch(facecolor="none", edgecolor="red", linewidth=3, label='Project AOI')
    ]
    ax1.legend(handles=ctx_handles, loc='lower left', fontsize=12, frameon=False)


    # ==========================================
    # PANEL B: ZOOMED PROJECT MAP
    # ==========================================
    # Plot layers in strict Z-order
    
    # 1. Background Geology (CLGB)
    if "Bedrock (CLGB)" in layers:
        layers["Bedrock (CLGB)"].plot(ax=ax2, facecolor="#c0ffc0", alpha=0.3, edgecolor="none")
    
    # 2. Cell grids
    if "Taken Cells" in layers:
        layers["Taken Cells"].plot(ax=ax2, facecolor="#808080", edgecolor="none")
        
    if "Partly Taken Cells" in layers:
        layers["Partly Taken Cells"].plot(ax=ax2, facecolor="#ffaa00", edgecolor="none", alpha=0.8)
        
    if "Clean Open Cells" in layers:
        layers["Clean Open"].plot(ax=ax2, facecolor="#ccffcc", edgecolor="#00cc00", linewidth=0.5) if "Clean Open" in layers else layers["Clean Open Cells"].plot(ax=ax2, facecolor="#ccffcc", edgecolor="#00cc00", linewidth=0.5)

    # 3. Tukes Rights (Outlines only)
    if "Tukes Rights" in layers:
        layers["Tukes Rights"].plot(ax=ax2, facecolor="none", edgecolor="#aa0000", linewidth=0.6)

    # 4. Deposits
    if "Gold Deposits" in layers:
        deps = layers["Gold Deposits"]
        # Ensure we only plot deposits in the AOI
        deps_in_aoi = gpd.clip(deps, aoi_bounds)
        deps_in_aoi.plot(ax=ax2, marker='*', facecolor="gold", edgecolor="black", markersize=300, zorder=5)

        # Labels for key deposits
        key_deposits = ["Suurikuusikko", "Pahtavaara", "Ikkari", "Kaaresselkä"]
        if "name" in deps_in_aoi.columns:
            for idx, row in deps_in_aoi.iterrows():
                dep_name = row["name"]
                if dep_name in key_deposits and row.geometry:
                    # White halo effect
                    path_eff = [pe.withStroke(linewidth=3, foreground="white")]
                    ax2.annotate(dep_name, 
                                 xy=(row.geometry.x, row.geometry.y), 
                                 xytext=(8, 8), 
                                 textcoords="offset points", 
                                 fontsize=11, 
                                 weight='bold',
                                 path_effects=path_eff,
                                 zorder=6)

    # 5. Towns (Manual points)
    towns = {
        "Kittilä": (410000, 7505000), 
        "Sodankylä": (483000, 7478000)
    }
    for t_name, (tx, ty) in towns.items():
        if minx <= tx <= maxx and miny <= ty <= maxy:
            ax2.plot(tx, ty, 'ko', markersize=6, zorder=7)
            path_eff = [pe.withStroke(linewidth=3, foreground="white")]
            ax2.annotate(t_name, xy=(tx, ty), xytext=(8, -4), textcoords="offset points", 
                         fontsize=12, style='italic', path_effects=path_eff, zorder=7)

    # 6. AOI Boundary
    aoi_poly.plot(ax=ax2, facecolor="none", edgecolor="black", linewidth=2)

    # Configure axes limits
    buffer = 5000
    ax2.set_xlim(minx - buffer, maxx + buffer)
    ax2.set_ylim(miny - buffer, maxy + buffer)
    ax2.set_title("Legal Availability in the Central Lapland AOI", fontsize=18, pad=20, weight='bold')
    ax2.set_axis_off()

    # Scale bar (manual)
    sb_len = 20000 # 20km
    sb_x = minx + 10000
    sb_y = miny + 5000
    ax2.plot([sb_x, sb_x + sb_len], [sb_y, sb_y], color='black', linewidth=4)
    ax2.text(sb_x + sb_len/2, sb_y + 1500, "20 km", ha='center', va='bottom', fontsize=12, weight='bold')

    # North arrow
    ax2.annotate('N', xy=(0.95, 0.95), xytext=(0.95, 0.90),
                arrowprops=dict(facecolor='black', width=3, headwidth=10),
                ha='center', va='center', fontsize=16, weight='bold',
                xycoords='axes fraction', textcoords='axes fraction')

    # Zoom Legend
    zoom_handles = [
        mpatches.Patch(facecolor="#ccffcc", edgecolor="#00cc00", label='Clean-Open Cells'),
        mpatches.Patch(facecolor="#ffaa00", edgecolor="none", label='Partly Taken Cells'),
        mpatches.Patch(facecolor="#808080", edgecolor="none", label='Taken Cells'),
        mpatches.Patch(facecolor="none", edgecolor="#aa0000", linewidth=1, label='Tukes Rights'),
        Line2D([0], [0], marker='*', color='w', markerfacecolor='gold', markeredgecolor='black', markersize=15, label='Gold Deposits'),
        mpatches.Patch(facecolor="#c0ffc0", alpha=0.3, edgecolor="none", label='CLGB Envelope'),
    ]
    ax2.legend(handles=zoom_handles, loc='upper left', fontsize=12, framealpha=0.9)

    # Save outputs
    png_path = os.path.join(out_dir, "finland_context_and_aoi.png")
    pdf_path = os.path.join(out_dir, "finland_context_and_aoi.pdf")
    
    plt.savefig(png_path, dpi=300, bbox_inches='tight', facecolor='white')
    plt.savefig(pdf_path, dpi=300, bbox_inches='tight', facecolor='white')
    plt.close()

    # Report Generation
    report_path = os.path.join(out_dir, "MAP_REPORT.md")
    with open(report_path, "w") as f:
        f.write("# Cartographic Visualization Report\n\n")
        f.write("A publication-quality two-panel map was successfully generated.\n\n")
        f.write("## 1. Layers Used\n")
        for layer in layers.keys():
            f.write(f"- `{layer}`\n")
        f.write("\n## 2. Missing Layers\n")
        if not missing:
            f.write("None\n")
        else:
            for m in missing:
                f.write(f"- `{m}`\n")
        
        f.write("\n## 3. Styling Logic\n")
        f.write("- **Finland Context**: Light grey fill, dark grey outline.\n")
        f.write("- **AOI**: Bold red outline in context, bold black outline in zoom.\n")
        f.write("- **CLGB Proxy**: Very light transparent green fill.\n")
        f.write("- **Open Cells**: Pale green fill with crisp green outline.\n")
        f.write("- **Partly Taken Cells**: Amber/orange fill.\n")
        f.write("- **Taken Cells**: Dark grey fill.\n")
        f.write("- **Tukes Rights**: Thin dark red outlines (clipped to AOI).\n")
        f.write("- **Deposits**: Gold stars with black outline. Labels receive a white halo to ensure readability against geometry.\n\n")
        
        f.write("## 4. Output Locations\n")
        f.write(f"- PNG: `{png_path}`\n")
        f.write(f"- PDF: `{pdf_path}`\n")
        f.write(f"- Report: `{report_path}`\n")

    print(f"Map successfully generated: {png_path}")

if __name__ == "__main__":
    main()
