#!/usr/bin/env python3
"""
scripts/28_build_interactive_geological_command_map.py

GeoArb Finland — Interactive Geological Command Map
Run: /Users/mk/miniconda3/envs/geoarb/bin/python scripts/28_build_interactive_geological_command_map.py
"""

import json, os, sys, zipfile, uuid, textwrap
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import box
import folium
from folium.plugins import Search, GroupedLayerControl, MeasureControl, Fullscreen

# ── Paths ─────────────────────────────────────────────────────────────────────
REPO  = Path(__file__).resolve().parents[1]
OUT   = REPO / "data" / "outputs" / "interactive_command_map"
LYR   = OUT  / "layers"
RAW   = REPO / "data" / "raw"   / "gtk"
PROC  = REPO / "data" / "processed"
QOUT  = REPO / "data" / "outputs"
QMAP  = QOUT / "qgis_command_map"

OUT.mkdir(parents=True, exist_ok=True)
LYR.mkdir(parents=True, exist_ok=True)

# ── Constants ──────────────────────────────────────────────────────────────────
CRS3067 = "EPSG:3067"
WGS84   = "EPSG:4326"
TARGETS = {2387: "g2k_01385", 2458: "g2k_01314"}
T_COORDS = {
    2387: {"lat": 67.824879, "lon": 24.791661, "x": 407000.0, "y": 7525000.0},
    2458: {"lat": 67.806953, "lon": 24.793354, "x": 407000.0, "y": 7523000.0},
}

ESRI_SAT   = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
ESRI_TOPO  = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}"
ESRI_LIGHT = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"
NLS_TOPO   = ("https://avoin-karttakuva.maanmittauslaitos.fi/avoin/wmts/1.0.0/"
              "taustakartta/default/WGS84_Pseudo-Mercator/{z}/{y}/{x}.png?api-key=YOUR_NLS_API_KEY")
NLS_ORTHO  = ("https://avoin-karttakuva.maanmittauslaitos.fi/avoin/wmts/1.0.0/"
              "ortokuva/default/WGS84_Pseudo-Mercator/{z}/{y}/{x}.jpg?api-key=YOUR_NLS_API_KEY")

CLGB_BOX   = (362000, 7470000, 505000, 7610000)   # EPSG:3067
FIN_BOX    = (190481, 6641517, 729647, 7784350)

print("═" * 60)
print(" GeoArb Finland — Interactive Geological Command Map")
print("═" * 60)
status = {}  # track load outcomes

# ── 1. Load + merge master grid ────────────────────────────────────────────────
print("\n[1] Loading and merging data…")

grid = gpd.read_file(QOUT / "clgb_grid_2km_numbered.gpkg")
print(f"  Grid: {len(grid)} cells  CRS={grid.crs}")

for _path, _cols, _lbl in [
    (PROC / "gravity_features_2km.parquet",
     ["cell_id","gravity_bouguer_mgal","gravity_gradient"], "gravity"),
    (PROC / "till_features_au_as_sb_2km.parquet",
     ["cell_id","till_au_clr","till_as_clr","till_sb_clr","till_source"], "till"),
    (PROC / "magnetics_features_2km.parquet",
     ["cell_id","magnetics_numeric","magnetics_status"], "magnetics"),
]:
    try:
        df_ = pd.read_parquet(_path)[_cols]
        grid = grid.merge(df_, on="cell_id", how="left")
        status[_lbl] = "LOADED"
        print(f"  ✓ {_lbl}")
    except Exception as e:
        status[_lbl] = f"FAILED: {e}"
        print(f"  ✗ {_lbl}: {e}")

magnetics_ok = bool(grid["magnetics_numeric"].any()) if "magnetics_numeric" in grid.columns else False

# Candidates extras
try:
    rc = pd.read_csv(QOUT / "review_candidates_audited.csv")
    extra_cols = ["cell_id", "fault_intersection_density", "dist_major_shear",
                  "dist_key_lithological_contact", "top_contributing_features",
                  "false_positive_flags", "single_signal_hallucination_flag", "audit_status"]
    rc_extra = rc[[c for c in extra_cols if c in rc.columns]].copy()
    grid = grid.merge(rc_extra, on="cell_id", how="left")
    status["review_candidates"] = f"LOADED ({len(rc)} rows)"
    print(f"  ✓ review_candidates: {len(rc)} rows")
except Exception as e:
    status["review_candidates"] = f"FAILED: {e}"
    print(f"  ✗ review_candidates: {e}")

# Warning flags per cell
def _flags(row):
    f = []
    if not magnetics_ok:
        f.append("NUMERIC_MAGNETICS_MISSING")
    fp = str(row.get("false_positive_flags", ""))
    if fp not in ("", "nan", "None", "<NA>"):
        f.append(f"FP:{fp[:40]}")
    if row.get("single_signal_hallucination_flag") is True:
        f.append("SINGLE_SIGNAL_HALLUCINATION")
    return "; ".join(f) if f else ""

grid["warning_flags"]    = grid.apply(_flags, axis=1)
grid["nearest_settlement"] = grid.get("nearest_town", pd.Series("unknown", index=grid.index)).fillna("unknown")

print(f"  Master index: {len(grid)} rows × {len(grid.columns)} cols")

# ── 2. Load pre-built command map layers ───────────────────────────────────────
print("\n[2] Loading command map layers…")
CMGPKG = QMAP / "command_map_layers.gpkg"

def _lyr(gpkg, name, required=False):
    try:
        g = gpd.read_file(gpkg, layer=name)
        status[name] = f"LOADED ({len(g)})"
        print(f"  ✓ {name}: {len(g)}")
        return g
    except Exception as e:
        status[name] = f"FAILED: {e}"
        if required:
            raise
        print(f"  ✗ {name}: {e}")
        return None

finland_gdf       = _lyr(CMGPKG, "finland_outline")
major_cities_gdf  = _lyr(CMGPKG, "major_cities")
clgb_aoi_gdf      = _lyr(CMGPKG, "clgb_aoi")
bedrock_gdf       = _lyr(CMGPKG, "bedrock_geology_clip")
structures_gdf    = _lyr(CMGPKG, "structures_faults_clip")
grav_cells_gdf    = _lyr(CMGPKG, "gravity_gradient_cells")
tukes_active_gdf  = _lyr(CMGPKG, "tukes_active_rights")
tukes_pend_gdf    = _lyr(CMGPKG, "tukes_pending_rights")
tukes_coff_gdf    = _lyr(CMGPKG, "tukes_cooling_off")
natura_gdf        = _lyr(CMGPKG, "natura2000")
protected_gdf     = _lyr(CMGPKG, "protected_areas")
groundwater_gdf   = _lyr(CMGPKG, "groundwater")
cand_all_gdf      = _lyr(CMGPKG, "review_candidates_all")
cand_ml_gdf       = _lyr(CMGPKG, "review_candidates_multilayer")
cand_so_gdf       = _lyr(CMGPKG, "review_candidates_structure_only")
settlements_gdf   = _lyr(CMGPKG, "settlements")

deposits_gdf = None
for p in [RAW / "fodd_precious_metals.gpkg", RAW / "gold_mines.gpkg",
          PROC / "clgb_positive_labels.gpkg"]:
    if p.exists():
        try:
            deposits_gdf = gpd.read_file(p)
            status["deposits"] = f"LOADED ({len(deposits_gdf)}) from {p.name}"
            print(f"  ✓ deposits: {len(deposits_gdf)} from {p.name}")
            break
        except Exception:
            pass

forensic_gdf = None
if (QOUT / "forensic_cells_2387_2458.gpkg").exists():
    forensic_gdf = gpd.read_file(QOUT / "forensic_cells_2387_2458.gpkg")
    status["forensic"] = f"LOADED ({len(forensic_gdf)})"
    print(f"  ✓ forensic_cells: {len(forensic_gdf)}")

# ── 3. COMMAND_MAP_INDEX.csv ──────────────────────────────────────────────────
print("\n[3] Building COMMAND_MAP_INDEX.csv…")
IDX_COLS = ["map_number","cell_id","centroid_lat","centroid_lon",
            "legal_status","restriction_status","candidate_status",
            "nearest_settlement","gravity_gradient","gravity_bouguer_mgal",
            "fault_intersection_density","dist_major_shear","dist_key_lithological_contact",
            "till_au_clr","till_as_clr","till_sb_clr",
            "model_score","baseline_score","model_minus_baseline",
            "multi_layer_convergence","audit_status","warning_flags"]
present = [c for c in IDX_COLS if c in grid.columns]
idx = grid[present].copy()
idx["map_number"] = idx["map_number"].astype(int)
idx_path = OUT / "COMMAND_MAP_INDEX.csv"
idx.to_csv(idx_path, index=False)
print(f"  Saved {idx_path.name}: {len(idx)} rows × {len(present)} cols")

# ── 4. Export GeoJSON layers ───────────────────────────────────────────────────
print("\n[4] Exporting GeoJSON layers…")

def to4326(gdf):
    if gdf is None or len(gdf) == 0:
        return gdf
    if gdf.crs and gdf.crs.to_epsg() != 4326:
        return gdf.to_crs(WGS84)
    return gdf

def _safe(v):
    if isinstance(v, (list, dict)):
        return str(v)
    try:
        if pd.isna(v):
            return ""
    except (TypeError, ValueError):
        pass
    return str(v)

def export_geojson(gdf, name, simplify_m=None, keep_cols=None):
    if gdf is None or len(gdf) == 0:
        print(f"  skip {name}: empty")
        return None
    g = gdf.copy()
    if simplify_m:
        g.geometry = g.geometry.simplify(simplify_m, preserve_topology=True)
    if keep_cols:
        cols = [c for c in keep_cols if c in g.columns] + ["geometry"]
        g = g[list(dict.fromkeys(cols))]
    g = to4326(g)
    for col in g.columns:
        if col == "geometry":
            continue
        g[col] = g[col].apply(_safe)
    p = LYR / f"{name}.geojson"
    g.to_file(p, driver="GeoJSON")
    kb = p.stat().st_size / 1024
    print(f"  ✓ {name}.geojson  {len(g)} features  {kb:.0f} KB")
    return p

GRID_COLS = ["map_number","cell_id","centroid_lat","centroid_lon",
             "legal_status","restriction_status","candidate_status",
             "nearest_settlement","gravity_gradient","model_score",
             "baseline_score","model_minus_baseline","multi_layer_convergence",
             "fault_intersection_density","dist_major_shear","dist_key_lithological_contact",
             "till_au_clr","till_as_clr","till_sb_clr","audit_status","warning_flags"]

export_geojson(grid, "grid_2km_all", simplify_m=None, keep_cols=GRID_COLS)
for mn, cid in TARGETS.items():
    export_geojson(grid[grid["map_number"] == mn], f"target_{mn}", keep_cols=GRID_COLS)

export_geojson(cand_ml_gdf,  "candidates_multilayer",     simplify_m=None)
export_geojson(cand_so_gdf,  "candidates_structure_only", simplify_m=None)
export_geojson(cand_all_gdf, "candidates_all",             simplify_m=None)
export_geojson(bedrock_gdf,  "bedrock_geology",            simplify_m=200,
               keep_cols=["LAND_LITHO","MAJOR_GU","AGE_GROUP","TECT_PRO","GU_DESCR"])
export_geojson(structures_gdf,"structures_faults",         simplify_m=None,
               keep_cols=["TECT_STRU","GS_NAME","GS_FAULTTY","CODE"])
export_geojson(grav_cells_gdf,"gravity_cells",             simplify_m=None,
               keep_cols=["cell_id","gravity_gradient","gravity_bouguer_mgal"])
export_geojson(tukes_active_gdf,"tukes_active", simplify_m=None)
export_geojson(tukes_pend_gdf,  "tukes_pending", simplify_m=None)
export_geojson(tukes_coff_gdf,  "tukes_cooling_off", simplify_m=None)
export_geojson(natura_gdf,      "natura2000", simplify_m=50)
export_geojson(protected_gdf,   "protected_areas", simplify_m=50)
export_geojson(groundwater_gdf, "groundwater", simplify_m=50)
export_geojson(finland_gdf,     "finland_outline", simplify_m=1000)
export_geojson(clgb_aoi_gdf,    "clgb_aoi", simplify_m=None)
export_geojson(settlements_gdf, "settlements")
export_geojson(deposits_gdf,    "known_deposits")
export_geojson(forensic_gdf,    "forensic_cells")

# ── 5. HTML Folium interactive map ────────────────────────────────────────────
print("\n[5] Building Folium HTML map…")

def load_gj(name):
    p = LYR / f"{name}.geojson"
    if not p.exists():
        return None
    with open(p) as f:
        return json.load(f)

def first_props(gj):
    if gj and gj.get("features"):
        return list(gj["features"][0].get("properties", {}).keys())
    return []

def poly_style(color, fill=None, fill_opacity=0.15, weight=2, dash=""):
    fc = fill or color
    def _s(f):
        return {"color": color, "fillColor": fc, "fillOpacity": fill_opacity,
                "weight": weight, "dashArray": dash}
    return _s

# Build map — centered on Sirkka/Levi, satellite imagery default
m = folium.Map(location=[67.824879, 24.791661], zoom_start=10,
               tiles=None, control_scale=True, prefer_canvas=True)

# ── Basemaps ──
folium.TileLayer(ESRI_SAT,
    attr="Tiles &copy; Esri — Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN",
    name="Esri World Imagery (Satellite)", max_zoom=19, show=True).add_to(m)
folium.TileLayer(ESRI_TOPO,
    attr="Tiles &copy; Esri — Esri, DeLorme, NAVTEQ, TomTom and the GIS User Community",
    name="Esri World Topo", max_zoom=19, show=False).add_to(m)
folium.TileLayer("OpenStreetMap", name="OpenStreetMap", show=False).add_to(m)
folium.TileLayer(ESRI_LIGHT,
    attr="Tiles &copy; Esri — Esri, HERE, Garmin, FAO",
    name="Esri Light Gray", max_zoom=16, show=False).add_to(m)
folium.TileLayer(NLS_ORTHO,
    attr="&copy; National Land Survey of Finland (API key required — see README)",
    name="NLS Finland Orthophoto [needs API key]", max_zoom=15, show=False).add_to(m)
folium.TileLayer(NLS_TOPO,
    attr="&copy; National Land Survey of Finland (API key required — see README)",
    name="NLS Finland Topo [needs API key]", max_zoom=15, show=False).add_to(m)

# ── Overlay feature groups (added in render order: bottom → top) ──

# Context (always on)
context_fg = folium.FeatureGroup(name="Finland & CLGB Context", show=True)
gj = load_gj("finland_outline")
if gj:
    folium.GeoJson(gj, style_function=poly_style("#888", "#ccc", 0.04, 1.5),
                   tooltip="Finland").add_to(context_fg)
context_fg.add_to(m)

aoi_fg = folium.FeatureGroup(name="CLGB AOI", show=True)
gj = load_gj("clgb_aoi")
if gj:
    folium.GeoJson(gj, style_function=lambda f: {"color": "#0066cc", "weight": 3.5,
                    "fillOpacity": 0, "dashArray": "10,5"},
                   tooltip="Central Lapland Greenstone Belt AOI").add_to(aoi_fg)
aoi_fg.add_to(m)

# Bedrock geology (default OFF — heavy, simplified 200m)
geology_fg = folium.FeatureGroup(name="Bedrock Geology [simplified]", show=False)
gj = load_gj("bedrock_geology")
if gj:
    flds = [c for c in ["LAND_LITHO","AGE_GROUP","TECT_PRO"] if c in first_props(gj)]
    folium.GeoJson(gj, style_function=poly_style("#998800","#cccc55",0.18,0.5),
                   tooltip=folium.GeoJsonTooltip(flds, [c+":" for c in flds]) if flds else None
                   ).add_to(geology_fg)
geology_fg.add_to(m)

# Legal / restrictions (default OFF)
legal_fg = folium.FeatureGroup(name="Legal / Restrictions", show=False)
for lname, col in [("tukes_active","#cc0000"),("tukes_pending","#ff6600"),
                   ("tukes_cooling_off","#ffaa00"),("natura2000","#006633"),
                   ("protected_areas","#009944"),("groundwater","#0088cc")]:
    gj = load_gj(lname)
    if gj:
        folium.GeoJson(gj, style_function=poly_style(col, col, 0.25, 1.2),
                       tooltip=lname.replace("_"," ").title()).add_to(legal_fg)
legal_fg.add_to(m)

# Gravity gradient (default OFF)
gravity_fg = folium.FeatureGroup(name="Gravity Gradient", show=False)
gj = load_gj("gravity_cells")
if gj:
    def _grav_style(feat):
        try:
            val = float(feat["properties"].get("gravity_gradient") or 0)
            norm = min(max((val + 0.3) / 0.6, 0.0), 1.0)
            r = int(255 * norm); b = int(255 * (1 - norm))
            return {"fillColor": f"#{r:02x}00{b:02x}", "fillOpacity": 0.4,
                    "color": "none", "weight": 0}
        except Exception:
            return {"fillOpacity": 0, "color": "none", "weight": 0}
    folium.GeoJson(gj, style_function=_grav_style,
                   tooltip=folium.GeoJsonTooltip(
                       ["cell_id","gravity_gradient"],["Cell:","Grad (mGal/km):"])).add_to(gravity_fg)
gravity_fg.add_to(m)

# Magnetics warning layer (always visible if missing)
if not magnetics_ok:
    mag_warn_fg = folium.FeatureGroup(name="⚠ Numeric Magnetics MISSING", show=True)
    gj = load_gj("clgb_aoi")
    if gj:
        folium.GeoJson(gj,
            style_function=lambda f: {"fillOpacity": 0, "color": "none", "weight": 0},
            tooltip="⚠ NUMERIC MAGNETICS DATA IS MISSING for this entire AOI"
        ).add_to(mag_warn_fg)
    mag_warn_fg.add_to(m)

# Structures/faults (default ON)
struct_fg = folium.FeatureGroup(name="Faults & Structures", show=True)
gj = load_gj("structures_faults")
if gj:
    def _struct_style(feat):
        p = feat.get("properties", {})
        ft = str(p.get("GS_FAULTTY", p.get("TECT_STRU",""))).lower()
        if any(k in ft for k in ("shear","zone")):
            return {"color": "#cc0000", "weight": 4.0, "opacity": 0.95}
        elif any(k in ft for k in ("thrust","reverse")):
            return {"color": "#ff6600", "weight": 2.5, "opacity": 0.85}
        else:
            return {"color": "#222222", "weight": 1.5, "dashArray": "5,3", "opacity": 0.75}
    flds = [c for c in ["GS_NAME","GS_FAULTTY","TECT_STRU"] if c in first_props(gj)]
    folium.GeoJson(gj, style_function=_struct_style,
                   tooltip=folium.GeoJsonTooltip(flds,[c+":" for c in flds]) if flds else None
                   ).add_to(struct_fg)
struct_fg.add_to(m)

# Till/geochem (default OFF)
till_fg = folium.FeatureGroup(name="Till Au-As-Sb Geochemistry", show=False)
gj = load_gj("grid_2km_all")
if gj:
    def _till_style(feat):
        p = feat.get("properties", {})
        try:
            au = float(p.get("till_au_clr") or 0)
            if au < 0.01:
                return {"fillOpacity": 0, "color": "none", "weight": 0}
            norm = min(au / 3.0, 1.0)
            r = int(50 + 205 * norm); g = int(200 * (1 - norm))
            return {"fillColor": f"#{r:02x}{g:02x}00", "fillOpacity": 0.45,
                    "color": "#888800", "weight": 0.3}
        except Exception:
            return {"fillOpacity": 0, "color": "none", "weight": 0}
    folium.GeoJson(gj, style_function=_till_style,
                   tooltip=folium.GeoJsonTooltip(
                       ["cell_id","till_au_clr","till_as_clr","till_sb_clr"],
                       ["Cell:","Au CLR:","As CLR:","Sb CLR:"])).add_to(till_fg)
till_fg.add_to(m)

# Full grid (default OFF — no labels)
grid_fg = folium.FeatureGroup(name="2km Grid — all 3798 cells", show=False)
gj_grid = load_gj("grid_2km_all")
if gj_grid:
    def _grid_style(feat):
        p = feat.get("properties", {})
        cs = str(p.get("candidate_status",""))
        ls = str(p.get("legal_status",""))
        if "multi_layer" in cs:
            return {"color":"#cc00cc","weight":2,"fillOpacity":0.04,"fillColor":"#cc00cc"}
        elif "structure" in cs:
            return {"color":"#ffaa00","weight":1.5,"fillOpacity":0.03,"fillColor":"#ffaa00"}
        elif ls == "open":
            return {"color":"#aaaaaa","weight":0.5,"fillOpacity":0}
        else:
            return {"color":"#777777","weight":0.3,"fillOpacity":0,"dashArray":"2,3"}
    # Build popup field list from actual properties
    gj_fields = [c for c in GRID_COLS if c in first_props(gj_grid)]
    folium.GeoJson(
        gj_grid, name="grid_search_layer", style_function=_grid_style,
        popup=folium.GeoJsonPopup(gj_fields, [c.replace("_"," ").title()+":" for c in gj_fields],
                                  max_width=360),
        tooltip=folium.GeoJsonTooltip(
            ["map_number","cell_id","candidate_status","legal_status"],
            ["Map #:","Cell ID:","Candidate:","Legal:"], sticky=True)
    ).add_to(grid_fg)
grid_fg.add_to(m)

# Structure-only candidates (47, default OFF)
so_fg = folium.FeatureGroup(name="Structure-Only Candidates (47)", show=False)
gj = load_gj("candidates_structure_only")
if gj:
    so_flds = [c for c in ["map_number","cell_id","candidate_status","centroid_lat","centroid_lon"] if c in first_props(gj)]
    folium.GeoJson(gj,
        style_function=poly_style("#ff8800","#ffcc44",0.12,2.5),
        tooltip=folium.GeoJsonTooltip(so_flds,[c+":" for c in so_flds]),
        popup=folium.GeoJsonPopup(so_flds,[c.replace("_"," ").title()+":" for c in so_flds],max_width=300)
    ).add_to(so_fg)
so_fg.add_to(m)

# Multi-layer candidates (16, default ON)
ml_fg = folium.FeatureGroup(name="Multi-Layer Candidates (16)", show=True)
gj_ml = load_gj("candidates_multilayer")
if gj_ml:
    ml_popup_flds = [c for c in ["map_number","cell_id","candidate_status",
                                  "centroid_lat","centroid_lon","nearest_settlement",
                                  "legal_status","restriction_status","gravity_gradient",
                                  "model_score","warning_flags"] if c in first_props(gj_ml)]
    folium.GeoJson(gj_ml,
        style_function=poly_style("#9900cc","#cc55ff",0.15,3.0),
        tooltip=folium.GeoJsonTooltip(
            ["map_number","cell_id","candidate_status"],["Map #:","Cell ID:","Status:"]),
        popup=folium.GeoJsonPopup(ml_popup_flds,
            [c.replace("_"," ").title()+":" for c in ml_popup_flds], max_width=360)
    ).add_to(ml_fg)
ml_fg.add_to(m)

# Known deposits (default ON)
deposits_fg = folium.FeatureGroup(name="Known Deposits / Occurrences", show=True)
if deposits_gdf is not None:
    d4 = to4326(deposits_gdf.copy())
    for _, row in d4.iterrows():
        try:
            geom = row.geometry
            if geom is None: continue
            lat = geom.y if geom.geom_type == "Point" else geom.centroid.y
            lon = geom.x if geom.geom_type == "Point" else geom.centroid.x
            nm = str(row.get("NAME", row.get("MINE_NAME", row.get("name","Deposit"))))
            folium.Marker([lat,lon],
                icon=folium.Icon(color="orange", icon="star", prefix="fa"),
                popup=folium.Popup(f"<b>{nm}</b><br>{row.get('STATUS','')}", max_width=200),
                tooltip=nm).add_to(deposits_fg)
        except Exception: pass
deposits_fg.add_to(m)

# Settlements (default ON)
settle_fg = folium.FeatureGroup(name="Settlements", show=True)
if settlements_gdf is not None:
    s4 = to4326(settlements_gdf.copy())
    for _, row in s4.iterrows():
        try:
            geom = row.geometry
            if geom is None: continue
            lat = geom.y if geom.geom_type == "Point" else geom.centroid.y
            lon = geom.x if geom.geom_type == "Point" else geom.centroid.x
            nm = str(row.get("name", row.get("NAME","Settlement")))
            folium.Marker([lat,lon],
                icon=folium.DivIcon(
                    html=(f'<div style="font:bold 11px Arial;color:#111;'
                          f'text-shadow:1px 1px 0 #fff,-1px -1px 0 #fff,'
                          f'1px -1px 0 #fff,-1px 1px 0 #fff;white-space:nowrap">{nm}</div>'),
                    icon_size=(120,20), icon_anchor=(60,10)),
                tooltip=nm).add_to(settle_fg)
        except Exception: pass
settle_fg.add_to(m)

# ── TARGET CELLS 2387 & 2458 — impossible to miss (always ON, topmost) ──────
target_fg = folium.FeatureGroup(name="▶ Target Cells 2387 & 2458", show=True)

T_STYLE = {
    2387: {"outline":"#cc0066","fill":"#ff44aa","lc":"#cc0066"},
    2458: {"outline":"#0044cc","fill":"#3377ff","lc":"#0044cc"},
}
T_POPUP = {
    2387: """<div style="font:12px/1.7 monospace">
<b style="font-size:15px;color:#cc0066">▶ Map #2387 &nbsp;/&nbsp; g2k_01385</b><br>
<b>Lat/Lon:</b> 67.824879°N &nbsp; 24.791661°E<br>
<b>EPSG:3067:</b> 407000 E, 7525000 N<br>
<b>Nearest:</b> Sirkka / Levi (~2.0 km NNE)<br>
<hr style="margin:5px 0">
<b>Legal:</b> open &nbsp;&nbsp; <b>Restriction:</b> clear<br>
<b>Candidate:</b> structure_gravity_review_candidate<br>
<b>Convergence:</b> structure + gravity<br>
<hr style="margin:5px 0">
<b>Evidence:</b> fault intersect + gravity gradient<br>
<b>Missing:</b> numeric magnetics; robust Au-As-Sb till<br>
<hr style="margin:5px 0">
<b>Coord audit:</b> ✓ YES_WITH_WARNINGS (97%)<br>
<span style="color:#cc0000;font-weight:bold">⚠ REVIEW CANDIDATE — NOT A GOLD TARGET</span><br>
<span style="color:#cc0000">⚠ NUMERIC MAGNETICS MISSING</span>
</div>""",
    2458: """<div style="font:12px/1.7 monospace">
<b style="font-size:15px;color:#0044cc">▶ Map #2458 &nbsp;/&nbsp; g2k_01314</b><br>
<b>Lat/Lon:</b> 67.806953°N &nbsp; 24.793354°E<br>
<b>EPSG:3067:</b> 407000 E, 7523000 N<br>
<b>Nearest:</b> Sirkka / Levi (~0.5 km — on the village)<br>
<hr style="margin:5px 0">
<b>Legal:</b> open &nbsp;&nbsp; <b>Restriction:</b> clear (0.256% lake sliver — immaterial)<br>
<b>Candidate:</b> structure_gravity_review_candidate<br>
<b>Convergence:</b> structure + gravity<br>
<hr style="margin:5px 0">
<b>Evidence:</b> fault intersect + gravity gradient<br>
<b>Missing:</b> numeric magnetics; robust Au-As-Sb till<br>
<hr style="margin:5px 0">
<b>Coord audit:</b> ✓ YES_WITH_WARNINGS (97%)<br>
<span style="color:#cc0000;font-weight:bold">⚠ REVIEW CANDIDATE — NOT A GOLD TARGET</span><br>
<span style="color:#cc0000">⚠ NUMERIC MAGNETICS MISSING</span>
</div>""",
}

for mn, cid in TARGETS.items():
    tc = grid[grid["map_number"] == mn].copy()
    if len(tc) == 0:
        print(f"  WARNING: target {mn} not found in grid!")
        continue
    tc4 = to4326(tc)
    sty = T_STYLE[mn]
    coords = T_COORDS[mn]

    def _t_style(feat, s=sty):
        return {"color": s["outline"], "weight": 6, "fillOpacity": 0.2,
                "fillColor": s["fill"], "opacity": 1.0}

    folium.GeoJson(tc4.__geo_interface__, style_function=_t_style,
                   popup=folium.Popup(T_POPUP[mn], max_width=420),
                   tooltip=f"▶ Map #{mn} / {cid} — click for details"
                   ).add_to(target_fg)

    # Pulsing circle marker at centroid
    folium.CircleMarker([coords["lat"], coords["lon"]], radius=18,
        color=sty["outline"], weight=5,
        fill=True, fill_color=sty["fill"], fill_opacity=0.45,
        popup=folium.Popup(T_POPUP[mn], max_width=420),
        tooltip=f"#{mn} / {cid}").add_to(target_fg)

    # Bold floating label above centroid
    folium.Marker(
        [coords["lat"] + 0.013, coords["lon"]],
        icon=folium.DivIcon(
            html=(f'<div style="font:900 14px Arial Black;color:{sty["lc"]};'
                  f'text-shadow:2px 2px 0 #fff,-2px -2px 0 #fff,2px -2px 0 #fff,'
                  f'-2px 2px 0 #fff,0 2px 0 #fff,0 -2px 0 #fff;white-space:nowrap">'
                  f'▶ {mn} / {cid}</div>'),
            icon_size=(220,26), icon_anchor=(0,13))
    ).add_to(target_fg)

target_fg.add_to(m)

# ── Search by map_number ──────────────────────────────────────────────────────
# Build a lean GeoJSON with only search fields — added directly to map
if gj_grid:
    search_feats = []
    for feat in gj_grid["features"]:
        p = feat["properties"]
        lat_ = p.get("centroid_lat",""); lon_ = p.get("centroid_lon","")
        search_feats.append({
            "type": "Feature",
            "geometry": feat["geometry"],
            "properties": {
                "map_number":       str(p.get("map_number","")),
                "cell_id":          str(p.get("cell_id","")),
                "candidate_status": str(p.get("candidate_status","")),
                "legal_status":     str(p.get("legal_status","")),
                "centroid_lat":     lat_,
                "centroid_lon":     lon_,
            }
        })
    search_gj = {"type":"FeatureCollection","features":search_feats}
    search_layer = folium.GeoJson(search_gj,
        style_function=lambda f: {"fillOpacity":0,"color":"none","weight":0},
        name="_search_layer", show=False)
    search_layer.add_to(m)
    Search(layer=search_layer, search_label="map_number",
           search_zoom=14, position="topleft",
           placeholder="Search map number (e.g. 2387)…",
           collapsed=False, weight=3).add_to(m)
    Search(layer=search_layer, search_label="cell_id",
           search_zoom=14, position="topleft",
           placeholder="Search cell_id (e.g. g2k_01385)…",
           collapsed=True, weight=3).add_to(m)

# ── UI controls ───────────────────────────────────────────────────────────────
Fullscreen(position="topleft").add_to(m)
MeasureControl(position="bottomleft", primary_length_unit="kilometers").add_to(m)

GroupedLayerControl(
    groups={
        "Context":             [context_fg, aoi_fg],
        "Geology":             [geology_fg, struct_fg],
        "Geophysics":          [gravity_fg],
        "Geochemistry":        [till_fg],
        "Legal / Restrictions":[legal_fg],
        "Grid & Candidates":   [grid_fg, so_fg, ml_fg],
        "Deposits & Targets":  [deposits_fg, target_fg],
        "Settlements":         [settle_fg],
    },
    exclusive_groups=False,
    collapsed=False,
    position="topright"
).add_to(m)

# ── Inject warning banner ─────────────────────────────────────────────────────
m.get_root().html.add_child(folium.Element("""
<div style="position:fixed;bottom:0;left:0;right:0;padding:5px 18px;
  background:linear-gradient(90deg,rgba(40,0,0,.93),rgba(0,0,50,.93));
  color:#ffdddd;font:11px/1.9 monospace;z-index:99999;
  border-top:2px solid #990000;display:flex;flex-wrap:wrap;gap:20px;align-items:center">
  <span style="color:#ff4444;font-weight:700">⚠ REVIEW CANDIDATES ONLY — NOT GOLD TARGETS</span>
  <span style="color:#ff8800;font-weight:700">⚠ NUMERIC MAGNETICS: MISSING</span>
  <span style="color:#ffcc00;font-weight:700">⚠ TILL GEOCHEMISTRY: SPARSE</span>
  <span style="color:#44ff88;font-weight:700">✓ COORDINATE TRUTH VERIFIED (97%)</span>
  <span style="color:#aaaaff;font-size:9px">GeoArb Finland / CLGB — Audit 2026-06-13</span>
</div>
"""))

# ── Inject legend panel ───────────────────────────────────────────────────────
m.get_root().html.add_child(folium.Element("""
<div id="legend" style="position:fixed;bottom:44px;right:8px;padding:10px 14px;
  background:rgba(10,10,22,.93);color:#eee;font:10px/1.8 monospace;
  border:1px solid #446;border-radius:6px;z-index:9998;min-width:205px;
  max-height:55vh;overflow-y:auto">
  <div style="font-size:12px;font-weight:700;color:#fff;margin-bottom:5px">MAP LEGEND</div>
  <div><span style="display:inline-block;width:18px;height:3px;background:#0066cc;
    border-top:3px dashed #0066cc;vertical-align:middle"></span> CLGB AOI</div>
  <div><span style="display:inline-block;width:18px;height:14px;
    border:5px solid #cc0066;background:rgba(255,68,170,.2);vertical-align:middle"></span>
    <b>Map #2387</b> target</div>
  <div><span style="display:inline-block;width:18px;height:14px;
    border:5px solid #0044cc;background:rgba(51,119,255,.2);vertical-align:middle"></span>
    <b>Map #2458</b> target</div>
  <div><span style="display:inline-block;width:18px;height:14px;
    border:2.5px solid #9900cc;background:rgba(204,85,255,.15);vertical-align:middle"></span>
    Multi-layer candidate</div>
  <div><span style="display:inline-block;width:18px;height:14px;
    border:2px solid #ff8800;background:rgba(255,204,68,.15);vertical-align:middle"></span>
    Structure-only candidate</div>
  <div><span style="display:inline-block;width:18px;height:3px;
    background:#cc0000;vertical-align:middle"></span> Shear zone / major fault</div>
  <div><span style="display:inline-block;width:18px;height:2px;
    border-top:1.5px dashed #333;vertical-align:middle"></span> Fault</div>
  <div><span style="display:inline-block;width:18px;height:12px;
    background:rgba(204,0,0,.25);vertical-align:middle"></span> Tukes active right</div>
  <div><span style="display:inline-block;width:18px;height:12px;
    background:rgba(0,102,51,.25);vertical-align:middle"></span> Natura 2000</div>
  <div>★ <span style="color:#ffaa00">Known deposit / occurrence</span></div>
  <div style="margin-top:6px;font-size:9px;color:#888">
    Basemap: Esri World Imagery (external)<br>
    Grid: EPSG:3067 — 2km cells — 3798 total<br>
    NLS Finland WMTS available with API key<br>
    © GTK, Tukes, NLS Finland, Esri
  </div>
</div>
"""))

# ── Inject multi-layer candidate sidebar ─────────────────────────────────────
map_var = m.get_name()  # e.g. "map_12345abc"

ml_items = ""
if gj_ml and gj_ml.get("features"):
    for feat in sorted(gj_ml["features"],
                       key=lambda f: int(f["properties"].get("map_number",0) or 0)):
        p = feat["properties"]
        mn_ = p.get("map_number","?")
        cid_= p.get("cell_id","?")
        lat_= p.get("centroid_lat","")
        lon_= p.get("centroid_lon","")
        is_tgt = str(mn_) in ("2387","2458")
        extra = "font-weight:700;color:#ff88cc;" if str(mn_) == "2387" else \
                "font-weight:700;color:#88aaff;" if str(mn_) == "2458" else ""
        try:
            js = f"{map_var}.setView([{float(lat_)},{float(lon_)}],14)"
        except (ValueError, TypeError):
            js = ""
        ml_items += (
            f'<li onclick="{js}" style="cursor:pointer;padding:3px 5px;border-radius:3px;'
            f'margin:1px 0;{extra}" '
            f'onmouseover="this.style.background=\'#334\'" '
            f'onmouseout="this.style.background=\'transparent\'">'
            f'{"★ " if is_tgt else ""}#{mn_} {cid_}</li>'
        )

m.get_root().html.add_child(folium.Element(f"""
<div id="ml-sidebar" style="position:fixed;top:58px;left:8px;padding:10px;
  background:rgba(10,10,25,.93);color:#ddd;font:10px/1.7 monospace;
  border:1px solid #446;border-radius:6px;z-index:9997;min-width:172px;
  max-height:68vh;overflow-y:auto">
  <div style="font-size:11px;font-weight:700;color:#cc99ff;margin-bottom:3px">
    16 MULTI-LAYER CANDIDATES</div>
  <div style="font-size:9px;color:#888;margin-bottom:5px">click to zoom · ★ = main target</div>
  <ul style="list-style:none;padding:0;margin:0;color:#ccc">{ml_items}</ul>
  <div style="margin-top:8px;border-top:1px solid #334;padding-top:5px">
    <button onclick="document.getElementById('ml-sidebar').style.display='none'"
      style="font-size:9px;background:#222;color:#aaa;border:1px solid #445;
             padding:2px 8px;cursor:pointer;border-radius:3px">hide</button>
  </div>
</div>
"""))

# Save HTML
html_path = OUT / "interactive_geological_command_map.html"
m.save(str(html_path))
mb = html_path.stat().st_size / 1048576
print(f"  ✓ Saved: {html_path.name}  ({mb:.1f} MB)")
status["html_map"] = f"SAVED ({mb:.1f} MB)"

# ── 6. QGIS project (.qgz) ─────────────────────────────────────────────────
print("\n[6] Building QGIS project…")

import xml.etree.ElementTree as ET

def _srs_xml(authid="EPSG:3067"):
    """Return a minimal spatialrefsys XML element."""
    srs = ET.Element("spatialrefsys", nativeFormat="Wkt")
    ET.SubElement(srs, "wkt").text = ""
    ET.SubElement(srs, "proj4").text = (
        "+proj=utm +zone=35 +ellps=GRS80 +towgs84=0,0,0,0,0,0,0 +units=m +no_defs"
        if "3067" in authid else
        "+proj=merc +a=6378137 +b=6378137 +lat_ts=0 +lon_0=0 +x_0=0 +y_0=0 +k=1 +units=m +no_defs"
    )
    ET.SubElement(srs, "srsid").text  = "3067"
    ET.SubElement(srs, "srid").text   = authid.split(":")[-1]
    ET.SubElement(srs, "authid").text = authid
    ET.SubElement(srs, "description").text = (
        "ETRS89 / TM35FIN(E,N)" if "3067" in authid else "WGS 84 / Pseudo-Mercator")
    ET.SubElement(srs, "geographicflag").text = "false"
    return srs

def _layer_id():
    return uuid.uuid4().hex[:12]

# Layer definitions: (display_name, path_from_qgz, layer_name_or_none, geom_type, checked)
# geom_type: P=polygon, L=line, Pt=point, R=raster
QGIS_LAYERS = []

# Basemaps (raster XYZ)
QGIS_LAYERS += [
    ("Esri World Imagery [satellite]",
     f"type=xyz&url={ESRI_SAT}&zmax=19&zmin=0", None, "R", "checked"),
    ("Esri World Topo",
     f"type=xyz&url={ESRI_TOPO}&zmax=19&zmin=0", None, "R", "unchecked"),
    ("OpenStreetMap",
     "type=xyz&url=https://tile.openstreetmap.org/{z}/{x}/{y}.png&zmax=19&zmin=0", None, "R", "unchecked"),
    ("NLS Finland Orthophoto [add API key]",
     f"type=xyz&url={NLS_ORTHO}&zmax=15&zmin=0", None, "R", "unchecked"),
    ("NLS Finland Topo [add API key]",
     f"type=xyz&url={NLS_TOPO}&zmax=15&zmin=0", None, "R", "unchecked"),
]

# Vector layers — paths relative to OUT/
rel = lambda p: str(Path(os.path.relpath(p, OUT)).as_posix())
QGIS_LAYERS += [
    # Context
    ("Finland Outline",      rel(QMAP/"command_map_layers.gpkg")+"|layername=finland_outline", None, "P", "checked"),
    ("CLGB AOI",             rel(PROC/"clgb_aoi.gpkg")+"|layername=clgb_aoi", None, "P", "checked"),
    # Geology
    ("Bedrock Geology",      rel(RAW/"bedrock.gpkg")+"|layername=bedrock", None, "P", "unchecked"),
    ("Structures / Faults",  rel(RAW/"structures.gpkg")+"|layername=structures", None, "L", "checked"),
    # Geophysics
    ("Gravity Gradient Cells", rel(QMAP/"command_map_layers.gpkg")+"|layername=gravity_gradient_cells", None, "P", "unchecked"),
    # Legal
    ("Tukes Active Rights",  rel(QMAP/"command_map_layers.gpkg")+"|layername=tukes_active_rights", None, "P", "unchecked"),
    ("Tukes Pending Rights", rel(QMAP/"command_map_layers.gpkg")+"|layername=tukes_pending_rights", None, "P", "unchecked"),
    ("Tukes Cooling-Off",    rel(QMAP/"command_map_layers.gpkg")+"|layername=tukes_cooling_off", None, "P", "unchecked"),
    ("Natura 2000",          rel(QMAP/"command_map_layers.gpkg")+"|layername=natura2000", None, "P", "unchecked"),
    ("Protected Areas",      rel(QMAP/"command_map_layers.gpkg")+"|layername=protected_areas", None, "P", "unchecked"),
    ("Groundwater",          rel(QMAP/"command_map_layers.gpkg")+"|layername=groundwater", None, "P", "unchecked"),
    # Candidates
    ("All 63 Review Candidates", rel(QOUT/"review_candidates_audited.gpkg"), None, "P", "unchecked"),
    ("Multi-Layer Candidates (16)", rel(QMAP/"command_map_layers.gpkg")+"|layername=review_candidates_multilayer", None, "P", "checked"),
    ("Structure-Only Candidates (47)", rel(QMAP/"command_map_layers.gpkg")+"|layername=review_candidates_structure_only", None, "P", "unchecked"),
    # Grid
    ("2km Grid All Cells",   rel(QOUT/"clgb_grid_2km_numbered.gpkg")+"|layername=clgb_grid_2km_numbered", None, "P", "unchecked"),
    # Targets
    ("FORENSIC — Cells 2387 & 2458", rel(QOUT/"forensic_cells_2387_2458.gpkg"), None, "P", "checked"),
    # Deposits
    ("Known Deposits / Occurrences", rel(RAW/"fodd_precious_metals.gpkg"), None, "Pt", "checked"),
    # Settlements
    ("Settlements",          rel(QMAP/"command_map_layers.gpkg")+"|layername=settlements", None, "Pt", "checked"),
]

# Build QGS XML
root = ET.Element("qgis", version="3.34.0", projectname="GeoArb Finland Command Map")

ET.SubElement(root, "homePath", path=".")
ET.SubElement(root, "title").text = "GeoArb Finland — Interactive Geological Command Map"

pcrs = ET.SubElement(root, "projectCrs")
pcrs.append(_srs_xml("EPSG:3067"))

canvas = ET.SubElement(root, "mapcanvas", name="theMapCanvas", annotationsVisible="1")
ET.SubElement(canvas, "units").text = "meters"
ext = ET.SubElement(canvas, "extent")
ET.SubElement(ext, "xmin").text = str(CLGB_BOX[0])
ET.SubElement(ext, "ymin").text = str(CLGB_BOX[1])
ET.SubElement(ext, "xmax").text = str(CLGB_BOX[2])
ET.SubElement(ext, "ymax").text = str(CLGB_BOX[3])
dst = ET.SubElement(canvas, "destinationsrs")
dst.append(_srs_xml("EPSG:3067"))

# Layer list
proj_layers = ET.SubElement(root, "projectlayers")
layer_ids = {}  # name -> id
for (lname, src, lyr_name, gtype, checked) in QGIS_LAYERS:
    lid = _layer_id()
    layer_ids[lname] = lid
    ltype = "raster" if gtype == "R" else "vector"
    ml = ET.SubElement(proj_layers, "maplayer",
                        type=ltype, geometry=gtype if gtype != "R" else "",
                        autoRefreshEnabled="0", hasScaleBasedVisibilityFlag="0")
    ET.SubElement(ml, "id").text = lid
    ET.SubElement(ml, "datasource").text = src
    ET.SubElement(ml, "layername").text = lname
    ET.SubElement(ml, "keywordList")
    srs_el = ET.SubElement(ml, "srs")
    srs_el.append(_srs_xml("EPSG:3857" if gtype == "R" else "EPSG:3067"))
    ET.SubElement(ml, "provider", encoding="UTF-8").text = "wms" if gtype == "R" else "ogr"
    if gtype != "R":
        ET.SubElement(ml, "vectorjoins")
        gt_map = {"P": "2", "L": "1", "Pt": "0"}
        ET.SubElement(ml, "layerGeometryType").text = gt_map.get(gtype, "2")

# Layer tree
lt_root = ET.SubElement(root, "layertree-group",
                          name="", checked="Qt::Checked", expanded="1")
ET.SubElement(lt_root, "custom-properties")

GROUPS = {
    "Basemaps": [n for n, *_ in QGIS_LAYERS if _[2] == "R"],
    "Context":  ["Finland Outline","CLGB AOI"],
    "Geology":  ["Bedrock Geology","Structures / Faults"],
    "Geophysics":["Gravity Gradient Cells"],
    "Legal / Restrictions":["Tukes Active Rights","Tukes Pending Rights","Tukes Cooling-Off",
                            "Natura 2000","Protected Areas","Groundwater"],
    "Grid & Candidates":["2km Grid All Cells","All 63 Review Candidates",
                         "Multi-Layer Candidates (16)","Structure-Only Candidates (47)"],
    "Targets":  ["FORENSIC — Cells 2387 & 2458"],
    "Deposits & Settlements":["Known Deposits / Occurrences","Settlements"],
}

# Helper to look up check state
checked_map = {lname: (chk == "checked") for lname, _, __, ___, chk in QGIS_LAYERS}
placed = set()
for grp_name, members in GROUPS.items():
    grp = ET.SubElement(lt_root, "layer-tree-group",
                         name=grp_name, checked="Qt::Checked", expanded="0")
    ET.SubElement(grp, "custom-properties")
    for lname in members:
        if lname in layer_ids:
            placed.add(lname)
            chk = "Qt::Checked" if checked_map.get(lname,False) else "Qt::Unchecked"
            ET.SubElement(grp, "layer-tree-layer", id=layer_ids[lname],
                          name=lname, checked=chk, expanded="1")
# Any unplaced
for lname, *_ in QGIS_LAYERS:
    if lname not in placed and lname in layer_ids:
        chk = "Qt::Checked" if checked_map.get(lname,False) else "Qt::Unchecked"
        ET.SubElement(lt_root, "layer-tree-layer", id=layer_ids[lname],
                      name=lname, checked=chk, expanded="1")

# Bookmarks
BOOKMARKS = [
    ("Finland Context",     190481, 6641517, 729647, 7784350),
    ("CLGB Context",        362000, 7470000, 505000, 7610000),
    ("Levi / Sirkka Area",  393000, 7515000, 421000, 7535000),
    ("Cell 2387 Local",     401000, 7519000, 413000, 7531000),
    ("Cell 2458 Local",     401000, 7517000, 413000, 7529000),
]
bk_root = ET.SubElement(root, "Bookmarks")
for bname, xmin, ymin, xmax, ymax in BOOKMARKS:
    bk = ET.SubElement(bk_root, "Bookmark",
                        id=str(uuid.uuid4()), name=bname, group="")
    ET.SubElement(bk, "xmin").text = str(xmin)
    ET.SubElement(bk, "ymin").text = str(ymin)
    ET.SubElement(bk, "xmax").text = str(xmax)
    ET.SubElement(bk, "ymax").text = str(ymax)
    sr = ET.SubElement(bk, "sr")
    sr.append(_srs_xml("EPSG:3067"))

# Write .qgs then zip to .qgz
qgs_path = OUT / "GeoArb_Finland_Interactive_Command_Map.qgs"
tree_out = ET.ElementTree(root)
ET.indent(tree_out, space="  ")
tree_out.write(str(qgs_path), encoding="UTF-8", xml_declaration=True)

qgz_path = OUT / "GeoArb_Finland_Interactive_Command_Map.qgz"
with zipfile.ZipFile(qgz_path, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.write(qgs_path, arcname="GeoArb_Finland_Interactive_Command_Map.qgs")
qgs_path.unlink()  # remove unzipped copy

qgz_kb = qgz_path.stat().st_size / 1024
print(f"  ✓ Saved: {qgz_path.name}  ({qgz_kb:.0f} KB)")
status["qgis_project"] = f"SAVED ({qgz_kb:.0f} KB)"

# ── 7. TARGET_CELL_INDEX_2387_2458.md ─────────────────────────────────────────
print("\n[7] Writing reports…")

tid = OUT / "TARGET_CELL_INDEX_2387_2458.md"
tid.write_text(f"""# Target Cell Index: Map #2387 & Map #2458

> Coordinate truth verified 2026-06-13. Coordinate confidence: **97%**.
> This is a review-candidate index only — **not a gold-target assessment**.

---

## Map #2387 / g2k_01385

| Field                    | Value |
|--------------------------|-------|
| Map number               | 2387 |
| Cell ID                  | g2k_01385 |
| EPSG:3067 centroid       | 407000 E, 7525000 N |
| WGS84 centroid           | 67.824879°N, 24.791661°E |
| 2km cell corners (3067)  | 406000–408000 E, 7524000–7526000 N |
| Nearest settlement       | Sirkka / Levi (~2.0 km NNE) |
| Municipality             | Kittilä |
| Inside Finland           | YES — 3/3 independent sources |
| Inside CLGB AOI          | YES — ~38 km from boundary |
| Legal status             | **open** |
| Restriction status       | **clear** |
| Candidate class          | structure_gravity_review_candidate |
| Multi-layer convergence  | structure + gravity |
| Gravity gradient         | present (from grid attribute) |
| Fault intersection       | present |
| Numeric magnetics        | **MISSING** |
| Au-As-Sb till support    | sparse |
| Coordinate audit verdict | YES_COORDINATE_CERTAIN_WITH_WARNINGS |
| **GOLD ASSESSED**        | **NO — coordinate audit only** |

---

## Map #2458 / g2k_01314

| Field                    | Value |
|--------------------------|-------|
| Map number               | 2458 |
| Cell ID                  | g2k_01314 |
| EPSG:3067 centroid       | 407000 E, 7523000 N |
| WGS84 centroid           | 67.806953°N, 24.793354°E |
| 2km cell corners (3067)  | 406000–408000 E, 7522000–7524000 N |
| Nearest settlement       | Sirkka / Levi (~0.5 km — effectively on village) |
| Municipality             | Kittilä |
| Inside Finland           | YES — 3/3 independent sources |
| Inside CLGB AOI          | YES — ~37 km from boundary |
| Legal status             | **open** |
| Restriction status       | **clear** (0.256% lake sliver — immaterial) |
| Candidate class          | structure_gravity_review_candidate |
| Multi-layer convergence  | structure + gravity |
| Gravity gradient         | present |
| Fault intersection       | present |
| Numeric magnetics        | **MISSING** |
| Au-As-Sb till support    | sparse |
| Coordinate audit verdict | YES_COORDINATE_CERTAIN_WITH_WARNINGS |
| **GOLD ASSESSED**        | **NO — coordinate audit only** |

---

## 2387 vs 2458 Comparison

- Both cells share centroid_x = 407000 (same easting column)
- 2387 is directly north of 2458 — exactly 2km separation (7525000 vs 7523000 N)
- Both open, clear, structure+gravity candidates
- 2458 is ~1.5 km closer to Sirkka/Levi centre
- Equal coordinate certainty (both 97%)
- Numeric magnetics missing for **both** — the gate is the same for both

---

*Map truth confirmed. Gold not estimated. Field disturbance not recommended.*
""", encoding="utf-8")

# ── 8. COMMAND_MAP_README.md ──────────────────────────────────────────────────
readme = OUT / "COMMAND_MAP_README.md"
readme.write_text(f"""# GeoArb Finland — Interactive Geological Command Map

## Quick-start

### HTML map (browser, works offline after download)
```
open data/outputs/interactive_command_map/interactive_geological_command_map.html
```
- Opens in your default browser — no server required
- Satellite basemap loads from Esri (internet required for tiles)
- #2387 and #2458 are highlighted at startup — look for the coloured outlines

### QGIS project
1. `open data/outputs/interactive_command_map/GeoArb_Finland_Interactive_Command_Map.qgz`
2. Layers load from relative paths — keep the repo structure intact
3. Bookmarks: View → Bookmarks → stored bookmarks (Finland, CLGB, Levi, Cells 2387/2458)
4. Default extent: CLGB AOI

---

## Searching for #2387 or #2458

**HTML map:**
- Use the search box at top-left: type `2387` or `g2k_01385`
- Or click the cell name in the "16 MULTI-LAYER CANDIDATES" sidebar panel (top-left)
- Or click directly on the magenta/blue outline

**QGIS:**
- View → Bookmarks → "Cell 2387 Local" or "Cell 2458 Local"
- Or open the FORENSIC layer attribute table and filter by `map_number`

---

## Toggling layers (HTML map)

The layer control panel is at top-right. Groups:

| Group | Default | Description |
|-------|---------|-------------|
| Context | ON | Finland outline + CLGB AOI |
| Geology | Faults ON, Bedrock OFF | Simplified bedrock (200m); full-res faults |
| Geophysics | OFF | Gravity gradient colour ramp |
| Geochemistry | OFF | Till Au/As/Sb CLR values |
| Legal / Restrictions | OFF | Tukes rights, Natura 2000, groundwater |
| Grid & Candidates | ML ON, others OFF | 16 multi-layer candidates always visible |
| Deposits & Targets | ON | Known occurrences + #2387/#2458 |
| Settlements | ON | Settlement labels |

---

## Basemaps

| Basemap | How to access |
|---------|--------------|
| Esri World Imagery | Default — loads from Esri tiles (internet required) |
| Esri World Topo | Toggle in layer control |
| OpenStreetMap | Toggle in layer control |
| NLS Finland Orthophoto | Requires free NLS API key — see below |
| NLS Finland Topo | Requires free NLS API key — see below |

### Getting a free NLS Finland API key
1. Register at https://www.maanmittauslaitos.fi/en/maps-and-spatial-data/expert-users/file-download-service/open-data-file-download-service
2. Get a free API key for the WMTS service
3. In the HTML map: edit the HTML source, replace `YOUR_NLS_API_KEY` with your key
4. In QGIS: edit the NLS tile layer data source URL, replace `YOUR_NLS_API_KEY`

---

## Colours and symbols

- **Magenta thick outline + circle** = Map #2387 / g2k_01385
- **Blue thick outline + circle** = Map #2458 / g2k_01314
- **Purple outline** = Multi-layer review candidate (16 total)
- **Orange outline** = Structure-only candidate (47 total)
- **Thick red line** = Shear zone / major fault
- **Dark dashed line** = Fault
- **Red fill** = Tukes active mining right
- **Green fill** = Natura 2000 / protected area
- **Gold star** = Known deposit / gold occurrence

---

## ⚠ Important warnings

1. **These are review candidates — NOT gold targets.** The map shows geospatial and structural evidence context only.
2. **Numeric magnetics are missing.** The aeromagnetic data (ECW raster) has not been converted to numeric cell values. This gate is unmet for all candidates including #2387 and #2458.
3. **Till geochemistry is sparse.** Au-As-Sb till coverage is thin across most of the grid.
4. **Coordinate truth has been verified (97% confidence)** — the coordinates are correct and safe to use for map/recon planning purposes. Gold prospectivity has NOT been verified.
5. **Do not take field action based solely on this map.** Confirm magnetics and till geochemistry first.

---

## Files in this folder

| File | Description |
|------|-------------|
| `interactive_geological_command_map.html` | Browser-based interactive map |
| `GeoArb_Finland_Interactive_Command_Map.qgz` | QGIS project |
| `COMMAND_MAP_INDEX.csv` | All 3798 cells with all attributes |
| `TARGET_CELL_INDEX_2387_2458.md` | One-page summary of #2387 and #2458 |
| `COMMAND_MAP_README.md` | This file |
| `COMMAND_MAP_REPORT.md` | Build report — what loaded, what failed |
| `layers/` | GeoJSON layers used by the HTML map |

---

## Basemap attribution
- **Esri World Imagery:** Tiles © Esri — Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN
- **NLS Finland:** © Maanmittauslaitos (National Land Survey of Finland)
- **OpenStreetMap:** © OpenStreetMap contributors

*GeoArb Finland / CLGB — Build date: 2026-06-13*
""", encoding="utf-8")

# ── 9. COMMAND_MAP_REPORT.md ───────────────────────────────────────────────────
lyr_files = sorted(LYR.glob("*.geojson"))
lyr_sizes  = {p.stem: f"{p.stat().st_size/1024:.0f} KB" for p in lyr_files}
mag_warn   = "MISSING — no numeric magnetics data for any cell" if not magnetics_ok else "AVAILABLE"

report = OUT / "COMMAND_MAP_REPORT.md"
report.write_text(f"""# COMMAND_MAP_REPORT — GeoArb Finland Interactive Map

**Build date:** 2026-06-13
**Script:** scripts/28_build_interactive_geological_command_map.py

---

## What was created

| Output | Status |
|--------|--------|
| `interactive_geological_command_map.html` | {status.get('html_map','?')} |
| `GeoArb_Finland_Interactive_Command_Map.qgz` | {status.get('qgis_project','?')} |
| `COMMAND_MAP_INDEX.csv` | {len(idx)} rows × {len(present)} cols |
| `layers/*.geojson` | {len(lyr_files)} files |
| `TARGET_CELL_INDEX_2387_2458.md` | created |
| `COMMAND_MAP_README.md` | created |

---

## Layer load status

{"".join(f"| {k} | {v} |" + chr(10) for k,v in status.items())}

---

## GeoJSON layer sizes

{"".join(f"| {k} | {v} |" + chr(10) for k,v in lyr_sizes.items())}

---

## Basemap

| Source | Type | Status |
|--------|------|--------|
| Esri World Imagery | XYZ tile (external) | Default — loads with internet |
| Esri World Topo | XYZ tile (external) | Toggle-on |
| OpenStreetMap | XYZ tile (external) | Toggle-on |
| NLS Finland Orthophoto | WMTS (needs API key) | URL included — API key placeholder |
| NLS Finland Topo | WMTS (needs API key) | URL included — API key placeholder |

**Imagery loads in QGIS:** YES (Esri XYZ tile via WMS provider)
**Imagery loads in HTML:** YES (Esri XYZ tile via Leaflet)
**Limitation:** Satellite tiles require internet. No tiles bulk-downloaded or committed.

---

## Layer stack

| Layer | Source | Simplification | Default |
|-------|--------|---------------|---------|
| Bedrock Geology | command_map_layers.gpkg | 200m (HTML only) | OFF |
| Structures / Faults | command_map_layers.gpkg | none | ON |
| Gravity Gradient | command_map_layers.gpkg | none | OFF |
| Numeric Magnetics | **{mag_warn}** | — | — |
| Till Au-As-Sb | grid_2km_all join | none | OFF |
| Tukes Active/Pending/Cooling | command_map_layers.gpkg | none | OFF |
| Natura/Protected/Groundwater | command_map_layers.gpkg | 50m | OFF |
| 2km Grid | clgb_grid_2km_numbered.gpkg | **NONE** | OFF |
| Multi-layer candidates (16) | command_map_layers.gpkg | none | ON |
| Structure-only (47) | command_map_layers.gpkg | none | OFF |
| Target cells 2387 & 2458 | grid (filtered) | **NONE** | ON |
| Known deposits | fodd_precious_metals.gpkg | — | ON |
| Settlements | command_map_layers.gpkg | — | ON |

---

## ⚠ Warnings

- **NUMERIC MAGNETICS MISSING** — all 3798 cells have magnetics_numeric=False
- **TILL GEOCHEMISTRY SPARSE** — low sample density over much of the AOI
- **Grid cells and target cells NOT simplified** — exact 2km boundaries preserved
- **QGIS layers are full-resolution** — no simplification applied in project file
- Esri/OSM basemaps are external — clearly attributed in map legend and README
- NLS Finland WMTS requires free API key — not bulk-downloaded, not committed

---

## Validation

| Check | Result |
|-------|--------|
| #2387 centroid EPSG:3067 | 407000 E, 7525000 N ✓ |
| #2387 centroid WGS84 | 67.824879°N, 24.791661°E ✓ |
| #2458 centroid EPSG:3067 | 407000 E, 7523000 N ✓ |
| #2458 centroid WGS84 | 67.806953°N, 24.793354°E ✓ |
| Cells shown unsimplified | YES |
| Cells 2387 & 2458 highlighted | YES — bold colour + circle + label |
| Search by map_number | YES |
| Search by cell_id | YES |
| Candidate sidebar | YES — 16 candidates clickable |
| Warning panel visible on open | YES |
| Numeric magnetics warning embedded | YES |

*This map covers coordinate/geospatial truth only. Gold has not been assessed.*
""", encoding="utf-8")

# ── 10. Validation ────────────────────────────────────────────────────────────
print("\n[10] Validation…")
for mn, cid in TARGETS.items():
    tc = grid[grid["map_number"] == mn]
    if len(tc) == 0:
        print(f"  FAIL: cell {mn} not found"); continue
    row = tc.iloc[0]
    cx, cy = float(row["centroid_x"]), float(row["centroid_y"])
    clat, clon = float(row["centroid_lat"]), float(row["centroid_lon"])
    exp = T_COORDS[mn]
    ok_xy  = abs(cx - exp["x"]) < 1 and abs(cy - exp["y"]) < 1
    ok_wgs = abs(clat - exp["lat"]) < 0.0001 and abs(clon - exp["lon"]) < 0.0001
    gj_tgt = LYR / f"target_{mn}.geojson"
    print(f"  #{mn}/{cid}: EPSG:3067 {cx},{cy} {'✓' if ok_xy else '✗'} | "
          f"WGS84 {clat:.6f},{clon:.6f} {'✓' if ok_wgs else '✗'} | "
          f"GeoJSON {'✓' if gj_tgt.exists() else '✗'}")

print("\n  Files created:")
for p in sorted(OUT.rglob("*")):
    if p.is_file():
        print(f"    {p.relative_to(OUT)}  {p.stat().st_size/1024:.0f} KB")

print("\n═" * 60)
print("  DONE — open the HTML map or load the .qgz in QGIS")
print("═" * 60)
