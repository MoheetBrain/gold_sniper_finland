"""
21 - Validate local gravity and magnetic geophysics files.

The Desktop files are linked under data/raw/gtk/gravity and data/raw/gtk/magnetics.
This script records what the local GDAL/rasterio build can actually read, and
separately inspects sidecar metadata/XYZ files so ECW or Geosoft driver failures do
not get mistaken for missing data.

Outputs
    data/outputs/LOCAL_GEOPHYSICS_VALIDATION_REPORT.md
    data/outputs/LOCAL_GEOPHYSICS_VALIDATION.csv
"""
from __future__ import annotations

import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from pyproj import CRS, Transformer
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import get_logger, get_path, load_config  # noqa: E402

log = get_logger("21_local_geophysics")

GRAVITY_DIR = Path("gtk/gravity")
MAGNETICS_DIR = Path("gtk/magnetics")
MAGNETICS_NUMERIC_DIR = Path("gtk/magnetics_numeric")
GRAVITY_XYZ_CRS = CRS.from_proj4(
    "+proj=tmerc +lat_0=0 +lon_0=21 +k=1 +x_0=1500000 +y_0=0 "
    "+ellps=WGS84 +units=m +no_defs"
)
PROJECT_CRS = CRS.from_epsg(3067)


def _as_yes_no(value: bool) -> str:
    return "YES" if value else "NO"


def _safe_float(value):
    try:
        if value is None or value == "":
            return np.nan
        return float(value)
    except Exception:  # noqa: BLE001
        return np.nan


def _gdalinfo(path: Path) -> tuple[bool, str]:
    exe = Path(sys.executable).with_name("gdalinfo")
    cmd = [str(exe if exe.exists() else "gdalinfo"), str(path)]
    try:
        p = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=45)
    except FileNotFoundError as exc:
        return False, f"gdalinfo not found: {exc}"
    except Exception as exc:  # noqa: BLE001
        return False, f"gdalinfo failed to run: {type(exc).__name__}: {exc}"
    msg = (p.stdout + "\n" + p.stderr).strip()
    return p.returncode == 0, msg


def _driver_note() -> str:
    with rasterio.Env() as env:
        drivers = env.drivers()
    ecw = drivers.get("ECW")
    jp2ecw = drivers.get("JP2ECW")
    if not ecw and not jp2ecw:
        return "ECW/JP2ECW drivers are absent from this GDAL build."
    return f"ECW driver={ecw}; JP2ECW driver={jp2ecw}"


def _load_clgb_box(outputs: Path, processed: Path):
    grid = outputs / "clgb_grid_2km.gpkg"
    aoi = processed / "clgb_aoi.gpkg"
    if grid.exists():
        gdf = gpd.read_file(grid).to_crs(3067)
        return box(*gdf.total_bounds)
    if aoi.exists():
        gdf = gpd.read_file(aoi).to_crs(3067)
        return box(*gdf.total_bounds)
    return None


def _overlap(bounds_3067, clgb_geom) -> tuple[str, float]:
    if bounds_3067 is None or clgb_geom is None:
        return "UNKNOWN", 0.0
    geom = box(*bounds_3067)
    inter = geom.intersection(clgb_geom)
    if inter.is_empty:
        return "NO", 0.0
    pct = 100.0 * inter.area / max(1.0, clgb_geom.area)
    return "YES", pct


def _xml_text(root: ET.Element, tag: str):
    elem = root.find(f".//{tag}")
    return elem.text if elem is not None else None


def _xml_all_text(root: ET.Element, tag: str) -> list[str]:
    return [e.text for e in root.findall(f".//{tag}") if e.text not in (None, "")]


def _xml_metadata(path: Path) -> dict:
    xml = path.with_suffix(path.suffix + ".xml")
    if not xml.exists():
        return {}
    try:
        root = ET.parse(xml).getroot()
    except Exception as exc:  # noqa: BLE001
        return {"metadata_error": f"{type(exc).__name__}: {exc}"}

    west = _safe_float(_xml_text(root, "westBL"))
    east = _safe_float(_xml_text(root, "eastBL"))
    south = _safe_float(_xml_text(root, "southBL"))
    north = _safe_float(_xml_text(root, "northBL"))
    bounds = None if np.isnan([west, east, south, north]).any() else (west, south, east, north)
    res_values = [_safe_float(v) for v in _xml_all_text(root, "value")]
    res_values = [v for v in res_values if np.isfinite(v) and v > 0]
    band_names = _xml_all_text(root, "dimDescrp")
    bands = _xml_text(root, "NumBands")
    pixel_depth = _xml_text(root, "PixelDepth")
    pixel_type = _xml_text(root, "PixelType")
    crs = _xml_text(root, "identCode") or _xml_text(root, "projcsn")
    visual = False
    if bands == "4" and pixel_depth == "8":
        visual = True
    if any(b.lower() in {"red", "green", "blue", "allopacity"} for b in band_names):
        visual = True
    return {
        "metadata_xml": str(xml),
        "xml_crs": f"EPSG:{crs}" if str(crs).isdigit() else crs,
        "xml_bounds_3067": bounds,
        "xml_resolution": min(res_values) if res_values else np.nan,
        "xml_bands": bands,
        "xml_pixel_depth": pixel_depth,
        "xml_pixel_type": pixel_type,
        "xml_band_names": ", ".join(band_names),
        "xml_visual_display": visual,
    }


def _validate_raster(path: Path, clgb_geom) -> dict:
    row = {
        "path": str(path),
        "file_type": path.suffix.lower().lstrip(".") or "unknown",
        "exists": path.exists(),
        "gdal_rasterio_readable": "NO",
        "driver": "",
        "crs": "",
        "bounds": "",
        "overlap_clgb_aoi": "UNKNOWN",
        "overlap_clgb_pct": 0.0,
        "pixel_resolution": "",
        "bands": "",
        "dtype": "",
        "nodata": "",
        "min": np.nan,
        "max": np.nan,
        "mean": np.nan,
        "numeric_or_display": "unknown",
        "suitable_for_modelling": "NO",
        "visual_only": "NO",
        "error": "",
    }
    meta = _xml_metadata(path)

    try:
        with rasterio.open(path) as ds:
            row.update({
                "gdal_rasterio_readable": "YES",
                "driver": ds.driver,
                "crs": str(ds.crs) if ds.crs else "",
                "bounds": tuple(round(v, 3) for v in ds.bounds),
                "pixel_resolution": tuple(round(abs(v), 3) for v in ds.res),
                "bands": ds.count,
                "dtype": ",".join(ds.dtypes),
                "nodata": ds.nodata,
            })
            bounds_3067 = tuple(ds.bounds)
            if ds.crs and str(ds.crs).upper() != "EPSG:3067":
                transformer = Transformer.from_crs(ds.crs, PROJECT_CRS, always_xy=True)
                xs, ys = transformer.transform(
                    [ds.bounds.left, ds.bounds.right, ds.bounds.right, ds.bounds.left],
                    [ds.bounds.bottom, ds.bounds.bottom, ds.bounds.top, ds.bounds.top],
                )
                bounds_3067 = (min(xs), min(ys), max(xs), max(ys))
            ov, pct = _overlap(bounds_3067, clgb_geom)
            row["overlap_clgb_aoi"] = ov
            row["overlap_clgb_pct"] = round(pct, 2)

            arr = ds.read(1, masked=True, out_shape=(min(512, ds.height), min(512, ds.width)))
            if arr.count():
                row["min"] = float(arr.min())
                row["max"] = float(arr.max())
                row["mean"] = float(arr.mean())
            is_visual = ds.count >= 3 and all(str(dt).startswith("uint8") for dt in ds.dtypes)
            row["numeric_or_display"] = "rendered RGB/greyscale display" if is_visual else "numeric raster/grid"
            row["visual_only"] = _as_yes_no(is_visual)
            row["suitable_for_modelling"] = _as_yes_no(not is_visual)
            return row
    except Exception as exc:  # noqa: BLE001
        row["error"] = f"{type(exc).__name__}: {exc}"

    ok, gdal_msg = _gdalinfo(path)
    if not ok and gdal_msg:
        row["error"] = f"{row['error']} | gdalinfo: {gdal_msg}".strip(" |")
    if path.suffix.lower() == ".ecw":
        row["error"] = f"{row['error']} | {_driver_note()}".strip(" |")

    if meta:
        bounds_3067 = meta.get("xml_bounds_3067")
        ov, pct = _overlap(bounds_3067, clgb_geom)
        row["crs"] = meta.get("xml_crs") or row["crs"]
        row["bounds"] = bounds_3067 or row["bounds"]
        row["overlap_clgb_aoi"] = ov
        row["overlap_clgb_pct"] = round(pct, 2)
        row["pixel_resolution"] = meta.get("xml_resolution") or row["pixel_resolution"]
        row["bands"] = meta.get("xml_bands") or row["bands"]
        row["dtype"] = (
            f"{meta.get('xml_pixel_type', '')} {meta.get('xml_pixel_depth', '')}-bit".strip()
            or row["dtype"]
        )
        if meta.get("xml_visual_display"):
            row["numeric_or_display"] = "rendered RGB/greyscale display from XML metadata"
            row["visual_only"] = "YES"
            row["suitable_for_modelling"] = "NO"
    return row


def _validate_xyz(path: Path, clgb_geom) -> dict:
    row = {
        "path": str(path),
        "file_type": "XYZ text grid",
        "exists": path.exists(),
        "gdal_rasterio_readable": "NO",
        "driver": "manual XYZ parser",
        "crs": "WGS84 / Gauss-Krueger CM 21E false easting 1500000",
        "bounds": "",
        "overlap_clgb_aoi": "UNKNOWN",
        "overlap_clgb_pct": 0.0,
        "pixel_resolution": "",
        "bands": 1,
        "dtype": "float",
        "nodata": "",
        "min": np.nan,
        "max": np.nan,
        "mean": np.nan,
        "numeric_or_display": "numeric XYZ Bouguer anomaly",
        "suitable_for_modelling": "YES",
        "visual_only": "NO",
        "error": "",
    }
    if not path.exists():
        row["error"] = "file missing"
        return row
    try:
        df = pd.read_csv(path, comment="/", sep=r"\s+", names=["x", "y", "dg"], engine="python")
        xs = np.sort(df["x"].unique())
        ys = np.sort(df["y"].unique())
        transformer = Transformer.from_crs(GRAVITY_XYZ_CRS, PROJECT_CRS, always_xy=True)
        tx, ty = transformer.transform(df["x"].to_numpy(), df["y"].to_numpy())
        bounds_3067 = (float(np.min(tx)), float(np.min(ty)), float(np.max(tx)), float(np.max(ty)))
        ov, pct = _overlap(bounds_3067, clgb_geom)
        dx = float(np.median(np.diff(xs))) if len(xs) > 1 else np.nan
        dy = float(np.median(np.diff(ys))) if len(ys) > 1 else np.nan
        row.update({
            "gdal_rasterio_readable": "NO; parsed manually",
            "bounds": tuple(round(v, 3) for v in bounds_3067),
            "overlap_clgb_aoi": ov,
            "overlap_clgb_pct": round(pct, 2),
            "pixel_resolution": f"{dx:g} x {dy:g} m",
            "min": float(df["dg"].min()),
            "max": float(df["dg"].max()),
            "mean": float(df["dg"].mean()),
        })
        ok, gdal_msg = _gdalinfo(path)
        if not ok and gdal_msg:
            row["error"] = f"GDAL cannot open XYZ directly: {gdal_msg}"
    except Exception as exc:  # noqa: BLE001
        row["suitable_for_modelling"] = "NO"
        row["error"] = f"{type(exc).__name__}: {exc}"
    return row


def _validate_generic_numeric_xyz(path: Path, clgb_geom, label: str) -> dict:
    row = {
        "path": str(path),
        "file_type": f"{label} numeric XYZ text grid",
        "exists": path.exists(),
        "gdal_rasterio_readable": "NO",
        "driver": "manual XYZ parser",
        "crs": "assumed EPSG:3067 unless sidecar metadata says otherwise",
        "bounds": "",
        "overlap_clgb_aoi": "UNKNOWN",
        "overlap_clgb_pct": 0.0,
        "pixel_resolution": "",
        "bands": 1,
        "dtype": "float",
        "nodata": "",
        "min": np.nan,
        "max": np.nan,
        "mean": np.nan,
        "numeric_or_display": f"numeric {label} XYZ grid candidate",
        "suitable_for_modelling": "YES",
        "visual_only": "NO",
        "error": "",
    }
    try:
        df = pd.read_csv(path, comment="/", sep=r"\s+", header=None, engine="python")
        if df.shape[1] < 3:
            raise ValueError("Expected at least three columns: x y value")
        data = df.iloc[:, :3].copy()
        data.columns = ["x", "y", "value"]
        for col in data.columns:
            data[col] = pd.to_numeric(data[col], errors="coerce")
        data = data.dropna()
        if data.empty:
            raise ValueError("No numeric x/y/value rows parsed")
        bounds_3067 = (
            float(data["x"].min()),
            float(data["y"].min()),
            float(data["x"].max()),
            float(data["y"].max()),
        )
        ov, pct = _overlap(bounds_3067, clgb_geom)
        xs = np.sort(data["x"].unique())
        ys = np.sort(data["y"].unique())
        dx = float(np.median(np.diff(xs))) if len(xs) > 1 else np.nan
        dy = float(np.median(np.diff(ys))) if len(ys) > 1 else np.nan
        row.update({
            "gdal_rasterio_readable": "NO; parsed manually",
            "bounds": tuple(round(v, 3) for v in bounds_3067),
            "overlap_clgb_aoi": ov,
            "overlap_clgb_pct": round(pct, 2),
            "pixel_resolution": f"{dx:g} x {dy:g} m" if np.isfinite(dx) and np.isfinite(dy) else "",
            "min": float(data["value"].min()),
            "max": float(data["value"].max()),
            "mean": float(data["value"].mean()),
        })
    except Exception as exc:  # noqa: BLE001
        row["suitable_for_modelling"] = "NO"
        row["error"] = f"{type(exc).__name__}: {exc}"
    return row


def _missing_numeric_magnetics_row(path: Path) -> dict:
    return {
        "path": str(path),
        "file_type": "numeric magnetics search directory",
        "exists": path.exists(),
        "gdal_rasterio_readable": "NO",
        "driver": "",
        "crs": "",
        "bounds": "",
        "overlap_clgb_aoi": "UNKNOWN",
        "overlap_clgb_pct": 0.0,
        "pixel_resolution": "",
        "bands": "",
        "dtype": "",
        "nodata": "",
        "min": np.nan,
        "max": np.nan,
        "mean": np.nan,
        "numeric_or_display": "no numeric magnetic grid supplied yet",
        "suitable_for_modelling": "NO",
        "visual_only": "NO",
        "error": "Drop GDAL-readable numeric magnetic anomaly grids into this directory.",
    }


def main() -> int:
    cfg = load_config()
    raw = get_path(cfg, "raw")
    processed = get_path(cfg, "processed")
    outputs = get_path(cfg, "outputs", create=True)
    clgb_geom = _load_clgb_box(outputs, processed)

    candidates = [
        raw / GRAVITY_DIR / "Fenno_Bouguer_Fin_ETRS89_TM35FIN.grd",
        raw / GRAVITY_DIR / "BA_FIN.XYZ",
        raw / GRAVITY_DIR / "Fenno_Bouguer_FIN_ETRS89_TM35FIN.ecw",
        raw / MAGNETICS_DIR / "aeromagnetic_anomaly_grey_epsg3067.ecw",
    ]
    mag_numeric_dir = raw / MAGNETICS_NUMERIC_DIR
    mag_numeric_dir.mkdir(parents=True, exist_ok=True)
    numeric_candidates = [
        p for p in sorted(mag_numeric_dir.iterdir())
        if p.is_file()
        and p.suffix.lower() not in {".xml", ".aux", ".ovr", ".tfw", ".prj", ".qml", ".gi"}
    ]
    candidates.extend(numeric_candidates)

    rows = []
    for path in candidates:
        log.info("Validating %s", path)
        if path == raw / GRAVITY_DIR / "BA_FIN.XYZ":
            rows.append(_validate_xyz(path, clgb_geom))
        elif path.parent == mag_numeric_dir and path.suffix.lower() in {".xyz", ".csv", ".txt"}:
            rows.append(_validate_generic_numeric_xyz(path, clgb_geom, "magnetic anomaly"))
        else:
            rows.append(_validate_raster(path, clgb_geom))
    if not numeric_candidates:
        rows.append(_missing_numeric_magnetics_row(mag_numeric_dir))

    df = pd.DataFrame(rows)
    csv_path = outputs / "LOCAL_GEOPHYSICS_VALIDATION.csv"
    df.to_csv(csv_path, index=False)

    lines = [
        "# Local Geophysics Validation Report",
        "",
        f"GDAL driver note: {_driver_note()}",
        "",
        "## Files Checked",
        "",
        "| file | readable | CRS | bounds | overlap CLGB | resolution | bands | numeric/display | modelling | visual-only |",
        "|------|----------|-----|--------|--------------|------------|-------|-----------------|-----------|-------------|",
    ]
    for row in rows:
        lines.append(
            f"| `{Path(row['path']).name}` | {row['gdal_rasterio_readable']} | "
            f"{row['crs']} | {row['bounds']} | {row['overlap_clgb_aoi']} "
            f"({row['overlap_clgb_pct']}%) | {row['pixel_resolution']} | {row['bands']} | "
            f"{row['numeric_or_display']} | {row['suitable_for_modelling']} | {row['visual_only']} |"
        )

    lines += [
        "",
        "## Numeric Statistics",
        "",
        "| file | min | max | mean | nodata | error / driver message |",
        "|------|-----|-----|------|--------|------------------------|",
    ]
    for row in rows:
        err = str(row.get("error", "")).replace("\n", " ").replace("|", "/")[:700]
        lines.append(
            f"| `{Path(row['path']).name}` | {row['min']} | {row['max']} | "
            f"{row['mean']} | {row['nodata']} | {err} |"
        )

    lines += [
        "",
        "## Decisions",
        "",
        "- Gravity: the preferred Geosoft `.grd` is present but not readable by this GDAL build. "
        "The `BA_FIN.XYZ` text grid is numeric, overlaps the CLGB AOI, and is suitable for "
        "the interim gravity-gradient feature.",
        "- Gravity ECW: metadata says it is an 8-bit, 4-band ECW display product; GDAL also "
        "cannot open ECW in this environment.",
        "- Magnetics: the ECW metadata says 4 bands, 8-bit Red/Green/Blue/opacity. That is a "
        "rendered greyscale/RGBA display, not a numeric magnetic anomaly grid. It is visual-only "
        "and not suitable for `mag_1vd` or `mag_low_in_high_proxy`.",
        "- Future numeric magnetics: place GDAL-readable numeric grids under "
        "`data/raw/gtk/magnetics_numeric/`; this validator will include them automatically.",
        "",
    ]
    report_path = outputs / "LOCAL_GEOPHYSICS_VALIDATION_REPORT.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    log.info("Wrote %s and %s", report_path, csv_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
