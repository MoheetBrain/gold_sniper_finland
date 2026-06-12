"""
06c - Process local aeromagnetic data if defensible.

The supplied file is `aeromagnetic_anomaly_grey_epsg3067.ecw`. Its XML metadata
describes a 4-band 8-bit RGB/opacity ECW, i.e. a rendered greyscale display. That
is not a numeric magnetic anomaly grid. If the local GDAL build cannot read ECW,
the script still writes a null feature table and a report explaining why magnetic
modelling features were not fabricated.

Output
    data/processed/magnetics_features_2km.parquet
    data/outputs/MAGNETICS_PROCESSING_REPORT.md
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import get_logger, get_path, load_config  # noqa: E402

log = get_logger("06c_magnetics")


def _xml_text(root: ET.Element, tag: str):
    elem = root.find(f".//{tag}")
    return elem.text if elem is not None else None


def inspect_xml(path: Path) -> dict:
    xml = path.with_suffix(path.suffix + ".xml")
    if not xml.exists():
        return {"xml_exists": False}
    root = ET.parse(xml).getroot()
    band_names = [e.text for e in root.findall(".//dimDescrp") if e.text]
    return {
        "xml_exists": True,
        "xml_path": str(xml),
        "bands": _xml_text(root, "NumBands"),
        "pixel_depth": _xml_text(root, "PixelDepth"),
        "pixel_type": _xml_text(root, "PixelType"),
        "format": _xml_text(root, "Format"),
        "band_names": band_names,
        "west": _xml_text(root, "westBL"),
        "south": _xml_text(root, "southBL"),
        "east": _xml_text(root, "eastBL"),
        "north": _xml_text(root, "northBL"),
    }


def gdal_error(path: Path) -> str:
    exe = Path(sys.executable).with_name("gdalinfo")
    cmd = [str(exe if exe.exists() else "gdalinfo"), str(path)]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=45)
        return (p.stdout + "\n" + p.stderr).strip()
    except Exception as exc:  # noqa: BLE001
        return f"{type(exc).__name__}: {exc}"


def ecw_driver_note() -> str:
    with rasterio.Env() as env:
        drivers = env.drivers()
    if not drivers.get("ECW") and not drivers.get("JP2ECW"):
        return "ECW/JP2ECW drivers are absent from this GDAL build."
    return f"ECW={drivers.get('ECW')}; JP2ECW={drivers.get('JP2ECW')}"


def main() -> int:
    cfg = load_config()
    raw = get_path(cfg, "raw")
    processed = get_path(cfg, "processed", create=True)
    outputs = get_path(cfg, "outputs", create=True)
    grid = gpd.read_file(outputs / cfg["step2"]["primary_grid"])
    mag_path = raw / "gtk/magnetics/aeromagnetic_anomaly_grey_epsg3067.ecw"

    xml = inspect_xml(mag_path)
    readable = False
    raster_summary = ""
    numeric = False
    visual_only = False
    try:
        with rasterio.open(mag_path) as ds:
            readable = True
            raster_summary = (
                f"driver={ds.driver}; crs={ds.crs}; bounds={tuple(ds.bounds)}; "
                f"res={ds.res}; bands={ds.count}; dtypes={ds.dtypes}"
            )
            visual_only = ds.count >= 3 and all(str(dt).startswith("uint8") for dt in ds.dtypes)
            numeric = not visual_only and ds.count == 1
    except Exception as exc:  # noqa: BLE001
        raster_summary = f"{type(exc).__name__}: {exc}; gdalinfo: {gdal_error(mag_path)}"

    if xml.get("bands") == "4" and xml.get("pixel_depth") == "8":
        visual_only = True
        numeric = False
    if any(str(b).lower() in {"red", "green", "blue", "allopacity"} for b in xml.get("band_names", [])):
        visual_only = True
        numeric = False

    out = pd.DataFrame({
        "cell_id": grid["cell_id"].to_numpy(),
        "mag_1vd": np.nan,
        "mag_low_in_high_proxy": np.nan,
        "mag_visual_proxy_low_confidence": np.nan,
        "magnetics_status": "visual_only_unreadable_ecw" if visual_only else "unreadable_ecw",
        "magnetics_numeric": False,
    })
    out.to_parquet(processed / "magnetics_features_2km.parquet", index=False)

    lines = [
        "# Magnetics Processing Report",
        "",
        f"Magnetics file used: `{mag_path}`",
        "",
        "## Readability",
        "",
        f"- Rasterio/GDAL readable: {'YES' if readable else 'NO'}",
        f"- GDAL driver note: {ecw_driver_note()}",
        f"- Raster/GDAL message: `{raster_summary[:1200]}`",
        "",
        "## Metadata Interpretation",
        "",
        f"- XML exists: {xml.get('xml_exists')}",
        f"- XML bands: {xml.get('bands')}",
        f"- XML pixel depth/type: {xml.get('pixel_depth')} / {xml.get('pixel_type')}",
        f"- XML band names: {', '.join(xml.get('band_names', []))}",
        f"- XML bounds: {xml.get('west')}, {xml.get('south')}, {xml.get('east')}, {xml.get('north')}",
        "",
        "## Decision",
        "",
        "- The supplied ECW is a rendered greyscale/RGBA display product, not a defensible "
        "numeric magnetic-anomaly grid.",
        "- `mag_1vd` was not created.",
        "- `mag_low_in_high_proxy` was not created.",
        "- `mag_visual_proxy_low_confidence` was not created because ECW pixels cannot be "
        "read in this GDAL build; even if readable, it would be a low-confidence visual "
        "texture/intensity proxy only.",
        "- Downstream validation must flag `magnetics_low_confidence`.",
        "",
    ]
    (outputs / "MAGNETICS_PROCESSING_REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    log.info("Wrote magnetics_features_2km.parquet; numeric=%s visual_only=%s", numeric, visual_only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
