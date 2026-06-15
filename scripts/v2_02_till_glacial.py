#!/usr/bin/env python3
"""
v2_02_till_glacial.py — Till Au/Te evidence (regional-referenced) + glacial up-ice back-projection.

HARD RULES (per brief):
  - As, Sb, Bi, W are ABSENT in the till data → set NaN, flag pathfinder_incomplete=True.
  - Transform Au/Te with empirical CDF (percentile vs regional AOI background). NOT CLR.
  - Back-project till up-ice using glacial lineation ICE_FLOW_DIRECTION (100 m – 5 km).
Outputs per cell: till_au_direct, till_au_5km, till_te_5km, till_backproj_au,
                  till_evidence (0-1), n_au_5km, ice_flow_deg, backproj_supported, pathfinder_incomplete
"""
import numpy as np, pandas as pd, geopandas as gpd, warnings, re
from pathlib import Path
warnings.filterwarnings("ignore")
ROOT = Path("/Users/mk/AL_THAHAB/gold_sniper")
GDB = "/Users/mk/Desktop/DATA_FINLAND/regional_till_geochemistry_etrs_tm35fin_gdb/regional_till_geochemistry.gdb"
GLAC = "/Users/mk/Desktop/DATA_FINLAND/glacial_features_epsg3067_gdb/glacial_features.gdb"
CELLS = ROOT/"data/outputs/geology_ranked_modelling_candidates.gpkg"
OUTP = ROOT/"data/processed"; OUTP.mkdir(parents=True, exist_ok=True)
TOP10=["g2k_01385","g2k_00779","g2k_00780","g2k_02275","g2k_01922","g2k_02274","g2k_01993","g2k_01850","g2k_01386","g2k_01314"]

cells = gpd.read_file(CELLS).to_crs(3067)[["cell_id","geometry"]].copy()
cells["ccx"]=cells.geometry.centroid.x; cells["ccy"]=cells.geometry.centroid.y

# --- Au (two layers) + Te ---
au1 = gpd.read_file(GDB,layer="alym_519u")[["Au_ppm_519U","geometry"]].rename(columns={"Au_ppm_519U":"Au"}); au1["Te"]=np.nan
au2 = gpd.read_file(GDB,layer="almr_519u")[["Au_ppm_519U","Te_ppm_519U","geometry"]].rename(columns={"Au_ppm_519U":"Au","Te_ppm_519U":"Te"})
au = pd.concat([au1,au2],ignore_index=True); au = gpd.GeoDataFrame(au,geometry="geometry",crs=3067)
au = au[au.Au.notna() & (au.Au>0)].copy()
au["px"]=au.geometry.x; au["py"]=au.geometry.y
xmin,ymin,xmax,ymax = cells.total_bounds
inaoi = au.px.between(xmin-6000,xmax+6000) & au.py.between(ymin-6000,ymax+6000)
au_aoi = au[inaoi].copy()
# empirical CDF reference (regional background, Au and Te)
au_sorted = np.sort(au_aoi.Au.values)
te_vals = au_aoi.Te.dropna().values; te_sorted = np.sort(te_vals)
def ecdf(v, ref):  # percentile 0-1 of v vs ref
    return np.searchsorted(ref, v, side="right")/max(len(ref),1)
print(f"Au samples AOI: {len(au_aoi):,} | Te samples AOI: {len(te_sorted):,}")

# --- ice flow per cell (nearest lineation ICE_FLOW_DIRECTION) ---
lin = gpd.read_file(GLAC, layer="gf_glacial_lineation_moraine").to_crs(3067)
ifd_col = "ICE_FLOW_DIRECTION"
print("ICE_FLOW_DIRECTION sample:", list(pd.Series(lin[ifd_col].dropna().unique())[:8]))
lin["ifd"] = pd.to_numeric(lin[ifd_col], errors="coerce")
lin.loc[lin.ifd < 0, "ifd"] = np.nan          # -1 == no recorded direction
lin_valid = lin[lin.ifd.notna()].copy()
# regional AOI ice-flow fallback (CLGB dominant flow)
linx = lin_valid.geometry.representative_point().x; liny = lin_valid.geometry.representative_point().y
in_aoi_lin = linx.between(xmin-10000,xmax+10000) & liny.between(ymin-10000,ymax+10000)
regional_ice = float(np.nanmedian(lin_valid.ifd[in_aoi_lin.values])) if in_aoi_lin.any() else float(np.nanmedian(lin_valid.ifd))
print(f"regional fallback ice-flow azimuth: {regional_ice:.0f} deg (n_valid_aoi={int(in_aoi_lin.sum())})")
lin_pt = lin_valid.copy(); lin_pt["geometry"] = lin_valid.geometry.representative_point()
near = gpd.sjoin_nearest(cells[["cell_id","geometry"]].copy(), lin_pt[["ifd","geometry"]],
                         how="left", max_distance=8000, distance_col="lin_dist")
ice = near.groupby("cell_id").agg(ice_flow_local=("ifd","median"), lin_dist=("lin_dist","min")).reset_index()
ice["ice_flow_deg"] = ice.ice_flow_local.fillna(regional_ice)
ice["ice_flow_confidence"] = np.where(ice.ice_flow_local.notna() & (ice.lin_dist<=5000), "local", "regional_fallback")

# --- spatial join Au samples within 5km of each cell ---
buf = cells.copy(); buf["geometry"]=buf.geometry.buffer(5000)
pairs = gpd.sjoin(au[["Au","Te","geometry"]].copy(), buf[["cell_id","ccx","ccy","geometry"]], predicate="within", how="inner")
pairs["sx"]=pairs.geometry.x; pairs["sy"]=pairs.geometry.y
pairs["dist"]=np.hypot(pairs.sx-pairs.ccx, pairs.sy-pairs.ccy)
# bearing FROM cell TO sample (deg from north, clockwise)
pairs["bearing"]=(np.degrees(np.arctan2(pairs.sx-pairs.ccx, pairs.sy-pairs.ccy)))%360
pairs = pairs.merge(ice[["cell_id","ice_flow_deg"]], on="cell_id", how="left")
# down-ice if sample bearing aligns with ice-flow direction (±55°); that means cell is UP-ice source
def angdiff(a,b): d=np.abs((a-b+180)%360-180); return d
pairs["downice"] = angdiff(pairs.bearing, pairs.ice_flow_deg) <= 55
pairs.loc[pairs.ice_flow_deg.isna(),"downice"] = False  # unknown ice flow → no backproj credit

def agg_cell(g):
    au_in = g[g.dist<=1000]; au_5 = g
    dwn = g[g.downice & (g.dist>=100) & (g.dist<=5000)]
    return pd.Series({
        "n_au_5km": len(au_5),
        "au_direct": au_in.Au.max() if len(au_in) else np.nan,
        "au_5km": au_5.Au.max() if len(au_5) else np.nan,
        "te_5km": au_5.Te.dropna().max() if au_5.Te.notna().any() else np.nan,
        "backproj_au": dwn.Au.max() if len(dwn) else np.nan,
    })
cg = pairs.groupby("cell_id").apply(agg_cell).reset_index()
cg = cells[["cell_id"]].merge(cg, on="cell_id", how="left").merge(ice, on="cell_id", how="left")

# --- scores (empirical CDF vs regional background) ---
cg["till_au_direct"] = ecdf(cg.au_direct.fillna(0).values, au_sorted)
cg["till_au_5km"]    = ecdf(cg.au_5km.fillna(0).values, au_sorted)
cg["till_te_5km"]    = ecdf(cg.te_5km.fillna(0).values, te_sorted) if len(te_sorted) else 0.0
cg["till_backproj_au"]= ecdf(cg.backproj_au.fillna(0).values, au_sorted)
cg["backproj_supported"] = cg.backproj_au.notna()
# back-projection credit is confidence-aware: full only where ice-flow is LOCALLY measured.
# In the candidate area ICE_FLOW_DIRECTION is unrecorded (regional fallback) -> down-weighted,
# so till_evidence is driven mainly by the direction-agnostic 5km neighbourhood anomaly.
bp_mult = np.where(cg.ice_flow_confidence.values=="local", 0.95, 0.72)
cg["till_evidence"] = np.maximum.reduce([
    cg.till_au_direct.values,
    bp_mult*cg.till_backproj_au.fillna(0).values,
    0.70*cg.till_au_5km.values,
    0.50*cg.till_te_5km.values,
])
# missing classic pathfinder penalty (As/Sb/Bi/W absent) — cap confidence
cg["pathfinder_incomplete"] = True
cg["till_evidence"] = cg.till_evidence * 0.85  # incompleteness discount (Au+Te only, no As/Sb halo)
cg["till_evidence"] = cg.till_evidence.clip(0,1)
for c in ["As","Sb","Bi","W"]: cg[f"till_{c.lower()}_clr"]=np.nan

cg.to_parquet(OUTP/"till_glacial_v2_features.parquet", index=False)
print("[saved] till_glacial_v2_features.parquet  rows=",len(cg))
print("\nTop-10 till+glacial evidence:")
show=["cell_id","n_au_5km","au_5km","till_au_direct","till_au_5km","till_te_5km","ice_flow_deg","backproj_supported","till_backproj_au","till_evidence"]
print(cg[cg.cell_id.isin(TOP10)][show].round(3).to_string(index=False))
