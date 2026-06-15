#!/usr/bin/env python3
"""
v2_01_magnetics.py — Process NUMERIC high-altitude aeromagnetic data → 1VD per cell.

Input : DATA_FINLAND/aeromagnetic_high_altitude_data_of_finland_epsg3067_xyz/HA_MG_Euref.XYZ
        (420k pts, EPSG:3067, col dF1965_150 = residual magnetic anomaly nT @150 m)
        The Geosoft .grd is NOT GDAL-readable here, so we use the numeric XYZ.
Output: data/processed/magnetics_v2_1vd.tif (gridded 1VD)
        data/processed/magnetics_v2_features.parquet  (per-cell mag_1vd_score, magnetic_break_score)
Method: grid anomaly → FFT first-vertical-derivative (|k| operator) → percentile scores.
        magnetic_confidence = high  (this IS numeric anomaly data, not a rendered image).
"""
import numpy as np, pandas as pd, geopandas as gpd, warnings
from pathlib import Path
from scipy.interpolate import griddata
warnings.filterwarnings("ignore")

ROOT = Path("/Users/mk/AL_THAHAB/gold_sniper")
XYZ = Path("/Users/mk/Desktop/DATA_FINLAND/aeromagnetic_high_altitude_data_of_finland_epsg3067_xyz/HA_MG_Euref.XYZ")
CELLS = ROOT/"data/outputs/geology_ranked_modelling_candidates.gpkg"
OUTP = ROOT/"data/processed"; OUTP.mkdir(parents=True, exist_ok=True)
RES = 500.0  # grid resolution m
PAD = 8000.0 # AOI pad for FFT edge effects

cells = gpd.read_file(CELLS).to_crs(3067)
xmin,ymin,xmax,ymax = cells.total_bounds
xmin-=PAD; ymin-=PAD; xmax+=PAD; ymax+=PAD
print(f"AOI(+pad) bounds: {xmin:.0f},{ymin:.0f} .. {xmax:.0f},{ymax:.0f}")

# --- read XYZ (header lines start with '/') ---
cols = ["X","Y","Lat","Lon","alt","dF","F1965","FDGRF"]
df = pd.read_csv(XYZ, sep=r"\s+", comment="/", header=None, names=cols, engine="python")
for c in ["X","Y","dF"]:
    df[c] = pd.to_numeric(df[c], errors="coerce")
df = df.dropna(subset=["X","Y","dF"])
print(f"XYZ points total: {len(df):,}")
m = (df.X>=xmin)&(df.X<=xmax)&(df.Y>=ymin)&(df.Y<=ymax)
sub = df[m]
print(f"points in AOI(+pad): {len(sub):,}  dF range nT: {sub.dF.min():.1f}..{sub.dF.max():.1f}")
if len(sub) < 500:
    raise SystemExit("Too few magnetic points in AOI — abort, do not fabricate.")

# --- grid to regular raster ---
nx = int((xmax-xmin)/RES); ny = int((ymax-ymin)/RES)
gx = xmin + (np.arange(nx)+0.5)*RES
gy = ymin + (np.arange(ny)+0.5)*RES
GX, GY = np.meshgrid(gx, gy)
grid = griddata((sub.X.values, sub.Y.values), sub.dF.values, (GX, GY), method="linear")
# fill remaining NaN with nearest so FFT is defined
nanmask = ~np.isfinite(grid)
if nanmask.any():
    gridn = griddata((sub.X.values, sub.Y.values), sub.dF.values, (GX, GY), method="nearest")
    grid[nanmask] = gridn[nanmask]
print(f"grid {ny}x{nx}  cellsize {RES} m")

# --- FFT First Vertical Derivative: 1VD = IFFT(|k| * FFT(field)) ---
field = grid - np.nanmean(grid)
# Hann window edges to reduce FFT ringing
wy = np.hanning(ny)[:,None]; wx = np.hanning(nx)[None,:]
win = 1 - 0.15*(1-wy)*(1-wx)  # mild taper
F = np.fft.fft2(field*win)
ky = np.fft.fftfreq(ny, d=RES)*2*np.pi
kx = np.fft.fftfreq(nx, d=RES)*2*np.pi
KX,KY = np.meshgrid(kx,ky)
K = np.sqrt(KX**2+KY**2)
vd1 = np.real(np.fft.ifft2(F*K))                # first vertical derivative
# horizontal gradient magnitude (structural-break proxy)
gyd, gxd = np.gradient(field, RES)
hgrad = np.sqrt(gxd**2+gyd**2)

def pctile_scale(a):
    a = np.asarray(a,float); flat=a[np.isfinite(a)]
    lo,hi = np.nanpercentile(flat,[2,98])
    return np.clip((a-lo)/max(hi-lo,1e-9),0,1)

vd1_s = pctile_scale(np.abs(vd1))
hg_s  = pctile_scale(hgrad)

# --- sample per cell centroid ---
def sample(arr, xs, ys):
    ix = np.clip(((xs-xmin)/RES).astype(int),0,nx-1)
    iy = np.clip(((ys-ymin)/RES).astype(int),0,ny-1)
    return arr[iy,ix]
cx = cells.geometry.centroid.x.values; cy = cells.geometry.centroid.y.values
feat = pd.DataFrame({
    "cell_id": cells.cell_id.values,
    "mag_anomaly_nT": sample(grid, cx, cy),
    "mag_1vd_score": sample(vd1_s, cx, cy),
    "magnetic_break_score": sample(hg_s, cx, cy),
})
feat["magnetic_confidence"] = "high"   # numeric anomaly data, not rendered image
feat.to_parquet(OUTP/"magnetics_v2_features.parquet", index=False)

# save 1VD raster (optional GeoTIFF)
try:
    import rasterio
    from rasterio.transform import from_origin
    tr = from_origin(xmin, ymax, RES, RES)
    with rasterio.open(OUTP/"magnetics_v2_1vd.tif","w",driver="GTiff",height=ny,width=nx,
                       count=1,dtype="float32",crs="EPSG:3067",transform=tr) as dst:
        dst.write(np.flipud(vd1).astype("float32"),1)
    print("[saved] magnetics_v2_1vd.tif")
except Exception as e:
    print("raster save skipped:", e)

print("[saved] magnetics_v2_features.parquet")
print("\nTop-10 cell magnetics (numeric, magnetic_confidence=high):")
TOP10=["g2k_01385","g2k_00779","g2k_00780","g2k_02275","g2k_01922","g2k_02274","g2k_01993","g2k_01850","g2k_01386","g2k_01314"]
print(feat[feat.cell_id.isin(TOP10)].round(3).to_string(index=False))
