#!/Users/mk/miniconda3/envs/geoarb/bin/python
import os
import glob
import pandas as pd
import geopandas as gpd
from shapely.geometry import Polygon
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D

# ---------------------------------------------------------
# CONSTANTS & SETUP
# ---------------------------------------------------------
EPSG = 3067
OUT_DIR = "data/outputs/maps_command_center"
os.makedirs(OUT_DIR, exist_ok=True)

# ---------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------
def load_layer(path, crs=EPSG):
    if os.path.exists(path):
        try:
            gdf = gpd.read_file(path)
            if gdf.crs and gdf.crs.to_epsg() != crs:
                gdf = gdf.to_crs(epsg=crs)
            elif not gdf.crs:
                gdf.set_crs(epsg=crs, inplace=True)
            return gdf
        except Exception as e:
            print(f"Failed to load {path}: {e}")
            return None
    return None

def add_grid_lines_and_labels(ax):
    # Just setting tick formats since we use pure metric
    ax.ticklabel_format(style='plain', useOffset=False)
    ax.set_xlabel("Easting (m)", fontsize=10)
    ax.set_ylabel("Northing (m)", fontsize=10)
    # Scale bar concept text instead of complex patches
    ax.text(0.02, 0.02, "Coordinates: EPSG:3067 / ETRS89-TM35FIN, metres",
            transform=ax.transAxes, fontsize=8, color='black',
            bbox=dict(facecolor='white', alpha=0.8, edgecolor='none'))

def get_aoi_bounds(aoi_gdf):
    if aoi_gdf is None or aoi_gdf.empty:
        return None
    bounds = aoi_gdf.total_bounds # minx, miny, maxx, maxy
    return bounds

# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------
def main():
    report_lines = []
    report_lines.append("# Command Center Map Report\n")
    
    # 1. Check data availability
    print("Loading layers...")
    finland_gdf = load_layer("data/raw/finland_boundary.geojson")
    aoi_gdf = load_layer("data/processed/aoi_grid.gpkg")
    tukes_gdf = load_layer("data/processed/tukes_all_rights.gpkg")
    taken_gdf = load_layer("data/outputs/taken_cells.gpkg")
    partly_taken_gdf = load_layer("data/outputs/partly_taken_cells.gpkg")
    open_gdf = load_layer("data/outputs/open_cells.gpkg")
    restricted_gdf = load_layer("data/outputs/restricted_cells.gpkg")
    clusters_gdf = load_layer("data/outputs/clean_open_clusters_2km.gpkg")
    
    bedrock_gdf = load_layer("data/raw/gtk/bedrock.gpkg")
    structures_gdf = load_layer("data/raw/gtk/structures.gpkg")
    deposits_gdf = load_layer("data/raw/gtk/fodd_precious_metals.gpkg")
    
    aoi_bounds = get_aoi_bounds(aoi_gdf)
    
    report_lines.append("## Layers Loaded:")
    for name, layer in [("Finland Boundary", finland_gdf), ("AOI Grid", aoi_gdf), 
                        ("Tukes Rights", tukes_gdf), ("Taken Cells", taken_gdf),
                        ("Partly Taken Cells", partly_taken_gdf), ("Open Cells", open_gdf),
                        ("Restricted Cells", restricted_gdf), ("Clusters 2km", clusters_gdf),
                        ("Bedrock", bedrock_gdf), ("Structures", structures_gdf),
                        ("Deposits", deposits_gdf)]:
        if layer is not None:
            report_lines.append(f"- {name}: {len(layer)} features, CRS={layer.crs.to_epsg()}")
        else:
            report_lines.append(f"- {name}: MISSING")

    # ====================================================
    # MAP 1: FINLAND CONTEXT
    # ====================================================
    print("Generating Map 1: Finland Context...")
    fig, ax = plt.subplots(figsize=(8, 12))
    if finland_gdf is not None:
        finland_gdf.plot(ax=ax, facecolor='lightgrey', edgecolor='darkgrey')
    
    if aoi_bounds is not None:
        minx, miny, maxx, maxy = aoi_bounds
        aoi_poly = Polygon([(minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy)])
        gpd.GeoDataFrame([1], geometry=[aoi_poly], crs=EPSG).plot(ax=ax, facecolor='none', edgecolor='red', linewidth=2)
        
    ax.set_title("GeoArb Finland — Project Location", fontsize=14, fontweight='bold')
    ax.text(0.5, 0.98, "Central Lapland Greenstone Belt / AOI context", 
            transform=ax.transAxes, ha='center', fontsize=10)
    add_grid_lines_and_labels(ax)
    plt.savefig(os.path.join(OUT_DIR, "01_finland_context.png"), dpi=300, bbox_inches='tight')
    plt.close()

    # ====================================================
    # MAP 2: LEGAL AVAILABILITY
    # ====================================================
    print("Generating Map 2: Legal Availability...")
    fig, ax = plt.subplots(figsize=(10, 10))
    ax.set_facecolor('white')
    
    if aoi_bounds is not None:
        ax.set_xlim(aoi_bounds[0] - 5000, aoi_bounds[2] + 5000)
        ax.set_ylim(aoi_bounds[1] - 5000, aoi_bounds[3] + 5000)
        
    if restricted_gdf is not None and not restricted_gdf.empty:
        restricted_gdf.plot(ax=ax, facecolor='none', edgecolor='black', hatch='//', linewidth=0.5, label='Restricted')
    if taken_gdf is not None and not taken_gdf.empty:
        taken_gdf.plot(ax=ax, facecolor='darkgrey', edgecolor='none', label='Taken')
    if partly_taken_gdf is not None and not partly_taken_gdf.empty:
        partly_taken_gdf.plot(ax=ax, facecolor='orange', edgecolor='none', alpha=0.8, label='Partly Taken')
    if open_gdf is not None and not open_gdf.empty:
        open_gdf.plot(ax=ax, facecolor='#ccffcc', edgecolor='#33cc33', linewidth=0.5, label='Clean-Open')
    if tukes_gdf is not None and not tukes_gdf.empty:
        tukes_gdf.plot(ax=ax, facecolor='none', edgecolor='red', linewidth=0.5, alpha=0.5, label='Tukes Rights')
    if clusters_gdf is not None and not clusters_gdf.empty:
        clusters_gdf.plot(ax=ax, facecolor='none', edgecolor='cyan', linewidth=2)
        # label clusters
        for idx, row in clusters_gdf.iterrows():
            c_id = row.get('cluster_id', f'CL_{idx}')
            ax.text(row.geometry.centroid.x, row.geometry.centroid.y, str(c_id),
                    color='cyan', fontsize=9, fontweight='bold', ha='center', va='center',
                    bbox=dict(facecolor='black', alpha=0.5, edgecolor='none', pad=1))
    if deposits_gdf is not None and not deposits_gdf.empty:
        # clip to aoi
        if aoi_gdf is not None:
            deposits_aoi = gpd.clip(deposits_gdf, aoi_gdf)
            if not deposits_aoi.empty:
                deposits_aoi.plot(ax=ax, marker='*', facecolor='gold', edgecolor='black', markersize=100, label='Deposits')
    
    ax.set_title("Central Lapland AOI — Legal Availability Map", fontsize=14, fontweight='bold')
    ax.text(0.5, 0.98, "Green = clean-open; grey/black = unavailable; orange = partly taken", 
            transform=ax.transAxes, ha='center', fontsize=10)
    add_grid_lines_and_labels(ax)
    
    # Legend
    legend_elements = [
        mpatches.Patch(facecolor='#ccffcc', edgecolor='#33cc33', label='Clean-Open'),
        mpatches.Patch(facecolor='orange', label='Partly Taken'),
        mpatches.Patch(facecolor='darkgrey', label='Taken'),
        mpatches.Patch(facecolor='none', hatch='//', edgecolor='black', label='Restricted'),
        mpatches.Patch(facecolor='none', edgecolor='cyan', linewidth=2, label='Open Clusters'),
        Line2D([0], [0], marker='*', color='w', markerfacecolor='gold', markeredgecolor='black', markersize=10, label='Gold Deposits'),
        mpatches.Patch(facecolor='none', edgecolor='red', label='Tukes Rights')
    ]
    ax.legend(handles=legend_elements, loc='upper right', framealpha=0.9, fontsize=8)
    
    plt.savefig(os.path.join(OUT_DIR, "02_legal_availability_aoi.png"), dpi=300, bbox_inches='tight')
    plt.close()

    # ====================================================
    # MAP 3: BASELINE GEOLOGY & TARGET BLOCKS
    # ====================================================
    print("Generating Map 3: Baseline Geology...")
    fig, ax = plt.subplots(figsize=(10, 10))
    ax.set_facecolor('#111122') # Dark charcoal / navy
    
    if aoi_bounds is not None:
        ax.set_xlim(aoi_bounds[0] - 5000, aoi_bounds[2] + 5000)
        ax.set_ylim(aoi_bounds[1] - 5000, aoi_bounds[3] + 5000)

    # Plot bedrock and structures
    if bedrock_gdf is not None and not bedrock_gdf.empty:
        try:
            # simple single color for bedrock
            bedrock_gdf.plot(ax=ax, facecolor='#225544', edgecolor='none', alpha=0.3)
        except:
            pass
    if structures_gdf is not None and not structures_gdf.empty:
        structures_gdf.plot(ax=ax, color='cyan', linewidth=0.5, alpha=0.6)
        
    # Plot cells
    if taken_gdf is not None and not taken_gdf.empty:
        taken_gdf.plot(ax=ax, facecolor='none', edgecolor='#333333', hatch='//', linewidth=0.5)
    if restricted_gdf is not None and not restricted_gdf.empty:
        restricted_gdf.plot(ax=ax, facecolor='none', edgecolor='#333333', hatch='//', linewidth=0.5)
    if open_gdf is not None and not open_gdf.empty:
        open_gdf.plot(ax=ax, facecolor='none', edgecolor='#44aa44', linewidth=0.5)

    # Coordinates & Callouts tracking
    coord_data = []
    
    if clusters_gdf is not None and not clusters_gdf.empty:
        # Sort by area if baseline score is not in columns, to assign Alpha, Bravo, Charlie
        clusters_gdf['area_m2'] = clusters_gdf.geometry.area
        clusters_gdf = clusters_gdf.sort_values(by='area_m2', ascending=False)
        
        # Plot clusters with thick outlines
        clusters_gdf.plot(ax=ax, facecolor='none', edgecolor='gold', linewidth=1.5)
        
        labels = ['ALPHA', 'BRAVO', 'CHARLIE', 'DELTA', 'ECHO', 'FOXTROT', 'GOLF', 'HOTEL']
        
        for idx, (_, row) in enumerate(clusters_gdf.iterrows()):
            c_id = row.get('cluster_id', f'CL_{idx}')
            block_name = f"TARGET BLOCK {labels[idx]}" if idx < len(labels) else f"TARGET BLOCK {idx}"
            
            centroid = row.geometry.centroid
            minx, miny, maxx, maxy = row.geometry.bounds
            area_km2 = row.geometry.area / 1e6
            area_ha = row.geometry.area / 10000
            
            coord_data.append({
                'target_block_id': block_name,
                'cluster_id': c_id,
                'score_type': 'Baseline geology only',
                'centroid_easting_m': centroid.x,
                'centroid_northing_m': centroid.y,
                'bbox_min_easting_m': minx,
                'bbox_min_northing_m': miny,
                'bbox_max_easting_m': maxx,
                'bbox_max_northing_m': maxy,
                'area_km2': area_km2,
                'area_hectares': area_ha,
                'legal_status': 'Clean-open',
                'restriction_status': 'No hard restrictions',
                'score_value_if_available': 'N/A',
                'data_status': 'Not validated ML prospectivity'
            })
            
            if idx < 3: # Callouts for top 3
                callout_text = (
                    f"{block_name}\n"
                    f"Centroid: E {int(centroid.x):,} m / N {int(centroid.y):,} m\n"
                    f"Area: {area_km2:.1f} km2 / {int(area_ha):,} ha\n"
                    f"Score type: Baseline geology only\n"
                    f"Status: Not validated ML prospectivity\n"
                    f"Missing: mag_1VD, gravity, till Au-As-Sb-Bi"
                )
                # Draw a text box
                ax.text(centroid.x, centroid.y, callout_text, color='white', fontsize=7,
                        bbox=dict(facecolor='black', alpha=0.7, edgecolor='gold', pad=2),
                        ha='left', va='bottom', zorder=10)

    if deposits_gdf is not None and not deposits_gdf.empty:
        if aoi_gdf is not None:
            deposits_aoi = gpd.clip(deposits_gdf, aoi_gdf)
            if not deposits_aoi.empty:
                deposits_aoi.plot(ax=ax, marker='*', facecolor='gold', edgecolor='black', markersize=80)
                
    ax.text(0.5, 0.5, "No validated ML prospectivity score available yet.\nBaseline Geology & Structure only.", 
            transform=ax.transAxes, ha='center', va='center', color='red', fontsize=12, fontweight='bold',
            bbox=dict(facecolor='black', alpha=0.5, edgecolor='none'))

    ax.set_title("Central Lapland — Baseline Geology Target Blocks", color='white', fontsize=14, fontweight='bold')
    add_grid_lines_and_labels(ax)
    
    # Custom colors for axis
    ax.tick_params(colors='white')
    ax.xaxis.label.set_color('white')
    ax.yaxis.label.set_color('white')
    
    plt.savefig(os.path.join(OUT_DIR, "03_baseline_geology_target_blocks.png"), dpi=300, bbox_inches='tight', facecolor='#111122')
    plt.close()
    
    # Output coords CSV
    df_coords = pd.DataFrame(coord_data)
    df_coords.to_csv(os.path.join(OUT_DIR, "target_block_coordinates.csv"), index=False)

    # ====================================================
    # MAP 4: ML PROSPECTIVITY HEATMAP (PLACEHOLDER)
    # ====================================================
    print("Generating Map 4: ML Prospectivity (Placeholder)...")
    fig, ax = plt.subplots(figsize=(10, 10))
    ax.set_facecolor('#222222')
    
    if aoi_bounds is not None:
        ax.set_xlim(aoi_bounds[0] - 5000, aoi_bounds[2] + 5000)
        ax.set_ylim(aoi_bounds[1] - 5000, aoi_bounds[3] + 5000)
    
    add_grid_lines_and_labels(ax)
    ax.tick_params(colors='white')
    ax.xaxis.label.set_color('white')
    ax.yaxis.label.set_color('white')
    
    msg = (
        "ML Prospectivity Heatmap Not Generated\n\n"
        "Model Failed Validation / Missing Features\n\n"
        "Missing Layers:\n"
        "- Aeromagnetic TMI\n"
        "- Magnetic 1VD\n"
        "- Gravity / Bouguer\n"
        "- Till Au\n"
        "- Till As\n"
        "- Till Sb\n"
        "- Till Bi"
    )
    
    ax.text(0.5, 0.5, msg, transform=ax.transAxes, ha='center', va='center', 
            color='white', fontsize=12, bbox=dict(facecolor='black', edgecolor='red', pad=10))
            
    ax.set_title("ML Prospectivity Heatmap Not Generated", color='red', fontsize=14, fontweight='bold')
    plt.savefig(os.path.join(OUT_DIR, "04_if_available_ml_prospectivity_heatmap.png"), dpi=300, bbox_inches='tight', facecolor='#222222')
    plt.close()

    # ====================================================
    # REPORT
    # ====================================================
    report_lines.append("## Coordinate Reference")
    if aoi_bounds is not None:
        report_lines.append("AOI bounds:")
        report_lines.append(f"- min_easting: {aoi_bounds[0]:.1f}")
        report_lines.append(f"- max_easting: {aoi_bounds[2]:.1f}")
        report_lines.append(f"- min_northing: {aoi_bounds[1]:.1f}")
        report_lines.append(f"- max_northing: {aoi_bounds[3]:.1f}")
        
    report_lines.append("\n## Cell & Cluster Counts")
    if open_gdf is not None:
        report_lines.append(f"- Clean open cells: {len(open_gdf)}")
    if clusters_gdf is not None:
        report_lines.append(f"- Open clusters: {len(clusters_gdf)}")
        
    report_lines.append("\n## ML Validation Status")
    report_lines.append("- True ML Heatmap Generated: False")
    report_lines.append("- Model Validation Passed: False (Did not beat distance-to-fault baseline)")
    report_lines.append("- Target Blocks Represent: Legal-only + Baseline Geology")
    report_lines.append("- Missing Layers: Magnetics (TMI, 1VD), Gravity, Till Geochemistry (Au, As, Sb, Bi)")

    report_lines.append("\n## Maps Created")
    report_lines.append("1. `01_finland_context.png`")
    report_lines.append("2. `02_legal_availability_aoi.png`")
    report_lines.append("3. `03_baseline_geology_target_blocks.png`")
    report_lines.append("4. `04_if_available_ml_prospectivity_heatmap.png` (Placeholder generated)")
    report_lines.append("5. `target_block_coordinates.csv`")
    
    report_lines.append("\n## Allowed Claims")
    report_lines.append("CURRENT CLAIM ALLOWED:")
    report_lines.append("We have produced a clean legal-availability and baseline geology map for open ground in the Central Lapland AOI.")
    
    report_lines.append("\nCURRENT CLAIM NOT ALLOWED:")
    report_lines.append("We have found AI-predicted gold targets. (Cannot claim until validated ML scores beat the baseline and all required feature layers are present.)")

    with open(os.path.join(OUT_DIR, "COMMAND_CENTER_MAP_REPORT.md"), "w") as f:
        f.write("\n".join(report_lines))

if __name__ == '__main__':
    main()
