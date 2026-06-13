#!/Users/mk/miniconda3/envs/geoarb/bin/python
import os
import glob
import json
import sqlite3
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

def get_qml_template(geom_type, fill_color, outline_color, outline_width, style="solid", point_shape="circle", point_size="2"):
    if geom_type == "polygon":
        return f"""<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.22.0" styleCategories="Symbology">
  <renderer-v2 type="singleSymbol" symbollevels="0" enableorderby="0" forceraster="0">
    <symbols>
      <symbol type="fill" name="0" alpha="1">
        <layer class="SimpleFill" pass="0" locked="0" enabled="1">
          <prop k="color" v="{fill_color}"/>
          <prop k="outline_color" v="{outline_color}"/>
          <prop k="outline_width" v="{outline_width}"/>
          <prop k="style" v="{style}"/>
        </layer>
      </symbol>
    </symbols>
  </renderer-v2>
</qgis>"""
    elif geom_type == "line":
        return f"""<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.22.0" styleCategories="Symbology">
  <renderer-v2 type="singleSymbol" symbollevels="0" enableorderby="0" forceraster="0">
    <symbols>
      <symbol type="line" name="0" alpha="1">
        <layer class="SimpleLine" pass="0" locked="0" enabled="1">
          <prop k="line_color" v="{outline_color}"/>
          <prop k="line_width" v="{outline_width}"/>
        </layer>
      </symbol>
    </symbols>
  </renderer-v2>
</qgis>"""
    elif geom_type == "point":
        return f"""<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.22.0" styleCategories="Symbology">
  <renderer-v2 type="singleSymbol" symbollevels="0" enableorderby="0" forceraster="0">
    <symbols>
      <symbol type="marker" name="0" alpha="1">
        <layer class="SimpleMarker" pass="0" locked="0" enabled="1">
          <prop k="color" v="{fill_color}"/>
          <prop k="outline_color" v="{outline_color}"/>
          <prop k="name" v="{point_shape}"/>
          <prop k="size" v="{point_size}"/>
        </layer>
      </symbol>
    </symbols>
  </renderer-v2>
</qgis>"""

STYLES = {
    "taken": {"type": "polygon", "fill": "100,100,100,255", "outline": "255,0,0,255", "width": "0.3", "style": "solid"},
    "partly_taken": {"type": "polygon", "fill": "255,165,0,128", "outline": "255,165,0,255", "width": "0.3", "style": "solid"},
    "clean_open": {"type": "polygon", "fill": "0,0,0,0", "outline": "0,255,0,255", "width": "0.5", "style": "no"},
    "open_clusters": {"type": "polygon", "fill": "0,0,0,0", "outline": "0,255,255,255", "width": "1.0", "style": "no"},
    "restrictions": {"type": "polygon", "fill": "255,0,255,128", "outline": "255,0,0,255", "width": "0.3", "style": "diagonal_x"},
    "faults": {"type": "line", "fill": "0,0,0,0", "outline": "255,0,0,255", "width": "0.5"},
    "gold_deposits": {"type": "point", "fill": "255,215,0,255", "outline": "0,0,0,255", "width": "0.1", "shape": "star", "size": "4"},
    "geology": {"type": "polygon", "fill": "0,255,0,64", "outline": "0,128,0,255", "width": "0.2", "style": "solid"},
    "aoi_box": {"type": "polygon", "fill": "0,0,0,0", "outline": "0,0,0,255", "width": "2.0", "style": "no"},
    "default_poly": {"type": "polygon", "fill": "200,200,200,128", "outline": "100,100,100,255", "width": "0.2", "style": "solid"},
    "default_point": {"type": "point", "fill": "200,200,200,255", "outline": "0,0,0,255", "width": "0.1", "shape": "circle", "size": "2"}
}

def write_qml(filepath, style_key):
    st = STYLES.get(style_key, STYLES["default_poly"])
    content = get_qml_template(
        st["type"],
        st["fill"],
        st["outline"],
        st["width"],
        style=st.get("style", "solid"),
        point_shape=st.get("shape", "circle"),
        point_size=st.get("size", "2")
    )
    with open(filepath, 'w') as f:
        f.write(content)

def main():
    out_dir = "data/outputs/qgis"
    os.makedirs(out_dir, exist_ok=True)
    
    layers_config = [
        {"path": "data/processed/aoi_grid.gpkg", "name": "AOI Context", "style": "aoi_box"},
        {"path": "data/processed/tukes_all_rights.gpkg", "name": "Tukes All Rights", "style": "default_poly"},
        {"path": "data/outputs/taken_cells.gpkg", "name": "Taken Cells", "style": "taken"},
        {"path": "data/outputs/partly_taken_cells.gpkg", "name": "Partly Taken Cells", "style": "partly_taken"},
        {"path": "data/outputs/open_cells.gpkg", "name": "Clean Open Cells", "style": "clean_open"},
        {"path": "data/outputs/clean_open_clusters_2km.gpkg", "name": "Open Clusters", "style": "open_clusters"},
        {"path": "data/outputs/restricted_cells.gpkg", "name": "Restricted Cells", "style": "restrictions"},
        {"path": "data/raw/gtk/bedrock.gpkg", "name": "Bedrock Geology", "style": "geology"},
        {"path": "data/raw/gtk/structures.gpkg", "name": "Structures / Faults", "style": "faults"},
        {"path": "data/raw/gtk/fodd_precious_metals.gpkg", "name": "Precious Metals", "style": "gold_deposits"},
        {"path": "data/raw/gtk/gold_mines.gpkg", "name": "Gold Mines", "style": "gold_deposits"},
    ]
    
    # Also find restrictions
    for rpath in glob.glob("data/raw/restrictions/**/*.gpkg", recursive=True):
        layers_config.append({"path": rpath, "name": os.path.basename(rpath), "style": "restrictions"})

    available_layers = []
    missing_layers = []
    
    for lc in layers_config:
        if os.path.exists(lc["path"]):
            available_layers.append(lc)
        else:
            missing_layers.append(lc)
            
    # Load and process available layers
    loaded_data = {}
    print("Loading layers for PNG map and report...")
    for lc in available_layers:
        print(f"Loading {lc['path']}...")
        try:
            gdf = gpd.read_file(lc["path"])
            if gdf.crs and gdf.crs != "EPSG:3067":
                gdf = gdf.to_crs("EPSG:3067")
            if lc["name"] == "AOI Context":
                gdf = gdf.dissolve() # Just the outer boundary
            loaded_data[lc["name"]] = {"gdf": gdf, "config": lc}
            
            # Write QML
            qml_path = os.path.join(out_dir, f"{os.path.basename(lc['path']).replace('.gpkg','')}.qml")
            write_qml(qml_path, lc["style"])
        except Exception as e:
            print(f"Failed to load {lc['path']}: {e}")
            missing_layers.append(lc)
            
    # Placeholder layers QMLs
    write_qml(os.path.join(out_dir, "magnetics_placeholder.qml"), "default_poly")
    write_qml(os.path.join(out_dir, "gravity_placeholder.qml"), "default_poly")
    write_qml(os.path.join(out_dir, "till_geochemistry_placeholder.qml"), "default_point")

    # Plot
    fig, ax = plt.subplots(figsize=(12, 12))
    
    # Define plot drawing order (bottom to top)
    plot_order = [
        "Bedrock Geology",
        "AOI Context",
        "Tukes All Rights",
        "Restricted Cells",
        "Taken Cells",
        "Partly Taken Cells",
        "Clean Open Cells",
        "Open Clusters",
        "Structures / Faults",
        "Precious Metals",
        "Gold Mines"
    ]
    
    for layer_name in plot_order:
        if layer_name in loaded_data:
            gdf = loaded_data[layer_name]["gdf"]
            st = STYLES.get(loaded_data[layer_name]["config"]["style"], STYLES["default_poly"])
            
            # Simple conversion of string RGBA to matplotlib color tuple
            if st["type"] == "polygon":
                fc = [float(x)/255 for x in st["fill"].split(",")]
                ec = [float(x)/255 for x in st["outline"].split(",")]
                if st.get("style") == "no":
                    fc = "none"
                if len(fc) == 4 and fc[3] == 0:
                    fc = "none"
                try:
                    gdf.plot(ax=ax, facecolor=fc, edgecolor=ec, linewidth=float(st["width"]))
                except Exception as e:
                    print(f"Plotting failed for {layer_name}: {e}")
            elif st["type"] == "line":
                ec = [float(x)/255 for x in st["outline"].split(",")]
                try:
                    gdf.plot(ax=ax, color=ec, linewidth=float(st["width"]))
                except Exception as e:
                    print(f"Plotting failed for {layer_name}: {e}")
            elif st["type"] == "point":
                fc = [float(x)/255 for x in st["fill"].split(",")]
                ec = [float(x)/255 for x in st["outline"].split(",")]
                try:
                    gdf.plot(ax=ax, marker='*', facecolor=fc, edgecolor=ec, markersize=float(st["size"])*10)
                except Exception as e:
                    print(f"Plotting failed for {layer_name}: {e}")
                    
    # Also try to plot any remaining layers that weren't in plot_order
    for name, data in loaded_data.items():
        if name not in plot_order:
            gdf = data["gdf"]
            try:
                gdf.plot(ax=ax, facecolor="none", edgecolor="purple", linewidth=0.5)
            except:
                pass
                
    
    # Set map limits to AOI bounds
    if "AOI Context" in loaded_data:
        minx, miny, maxx, maxy = loaded_data["AOI Context"]["gdf"].total_bounds
        ax.set_xlim(minx - 5000, maxx + 5000)
        ax.set_ylim(miny - 5000, maxy + 5000)

    plt.title("GeoArb Finland - Context & Legal Status")

    plt.savefig(os.path.join(out_dir, "aoi_legal_open_map.png"), dpi=300, bbox_inches='tight')
    plt.close()

    # Report
    report_path = os.path.join(out_dir, "QGIS_VISUALIZATION_REPORT.md")
    with open(report_path, "w") as f:
        f.write("# QGIS Visualization Report\n\n")
        f.write("This project visualizes the GeoArb Finland processing pipeline results.\n\n")
        
        f.write("## Loaded Layers\n")
        for layer_name, data in loaded_data.items():
            gdf = data["gdf"]
            config = data["config"]
            f.write(f"- **{layer_name}**\n")
            f.write(f"  - **Path:** `{config['path']}`\n")
            f.write(f"  - **CRS:** {gdf.crs.to_string() if gdf.crs else 'None'}\n")
            f.write(f"  - **Feature Count:** {len(gdf)}\n")
            f.write(f"  - **Styling Applied:** `{config['style']}` (QML template generated)\n\n")
            
        f.write("## Missing Layers\n")
        if not missing_layers:
            f.write("None\n\n")
        else:
            for lc in missing_layers:
                f.write(f"- **{lc['name']}**: `{lc['path']}`\n")
        f.write("\n")
        
        f.write("## Exact Output Paths\n")
        f.write(f"- QML Style Files: `{out_dir}/`\n")
        f.write(f"- Static Map PNG: `{out_dir}/aoi_legal_open_map.png`\n")
        f.write(f"- Report: `{out_dir}/QGIS_VISUALIZATION_REPORT.md`\n")
        f.write(f"- Placeholder slots created for: Magnetics, Gravity, Till Geochemistry\n\n")
        
        f.write("## How to open in QGIS\n")
        f.write("1. Open QGIS.\n")
        f.write("2. Open a new project and set the project CRS to **EPSG:3067** (ETRS89 / TM35FIN).\n")
        f.write("3. Drag and drop the `.gpkg` layers listed above from your file explorer into the QGIS Layers panel.\n")
        f.write("4. For each layer, right-click -> Properties -> Symbology -> Click 'Style' at the bottom -> 'Load Style...'.\n")
        f.write(f"5. Select the corresponding `.qml` file from the `{out_dir}` folder to apply standard styles.\n")
        f.write("6. Enable labels for `cluster_id` on Open Clusters, `cell_id` on Clean Open Cells (set rendering to scale-dependent, e.g. 1:100,000), and `deposit_name` on Gold Deposits.\n")
        f.write("7. Reorder layers appropriately (polygons at bottom, lines and points on top).\n")
        
    print(f"Report generated at {report_path}")
    print(f"Map generated at {out_dir}/aoi_legal_open_map.png")

if __name__ == '__main__':
    main()
