"""
25 - Build a zoomable vector command map for the CLGB 2 km grid.

This is a spatial-orientation product only. It does not change model outputs,
does not promote review candidates, and does not create target memos.

Primary outputs are vector layers and a QGIS project:
    data/outputs/qgis_command_map/GeoArb_Finland_Command_Map.qgz
    data/outputs/qgis_command_map/clgb_grid_2km_numbered.gpkg
    data/outputs/qgis_command_map/clgb_grid_2km_number_lookup.csv
    data/outputs/qgis_command_map/finland_context_vector.pdf
    data/outputs/qgis_command_map/clgb_zoom_vector.pdf
    data/outputs/qgis_command_map/COMMAND_MAP_README.md
    data/outputs/qgis_command_map/COMMAND_MAP_REPORT.md
"""
from __future__ import annotations

import csv
import io
import json
import math
import os
import sqlite3
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "gold_sniper_mpl"))

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams["pdf.fonttype"] = 42
matplotlib.rcParams["ps.fonttype"] = 42
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pyproj import Transformer
from scipy.spatial import cKDTree
from shapely.geometry import Point, box

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import get_logger, get_path, load_config  # noqa: E402

log = get_logger("25_zoomable_command_map")

PROJECT_CRS = "EPSG:3067"
WGS84 = "EPSG:4326"
SETTLEMENT_BUFFER_M = 50_000
GEONAMES_URL = "https://download.geonames.org/export/dump/FI.zip"

STATUS_COLORS = {
    "restricted_area": "#e88f94",
    "legally_blocked": "#f2a55e",
    "insufficient_data": "#ededed",
    "structure_only_candidate": "#f6c445",
    "structure_gravity_review_candidate": "#4b3fbc",
    "model_supported_review_candidate": "#f6c445",
}
STATUS_EDGES = {
    "restricted_area": "#9b1c24",
    "legally_blocked": "#b55a00",
    "insufficient_data": "#c5c5c5",
    "structure_only_candidate": "#995f00",
    "structure_gravity_review_candidate": "#17106f",
    "model_supported_review_candidate": "#995f00",
}

PLACE_RANK = {
    "city": 1,
    "town": 2,
    "municipality_centre": 3,
    "village": 4,
    "hamlet": 5,
    "locality": 6,
}

FALLBACK_SETTLEMENTS = [
    ("Kittila", 67.6555, 24.9088, "town"),
    ("Sodankyla", 67.4167, 26.6000, "town"),
    ("Sirkka", 67.8050, 24.8250, "village"),
    ("Levi", 67.8060, 24.8020, "locality"),
    ("Kiistala", 67.5530, 25.4190, "village"),
    ("Kaukonen", 67.5410, 24.6450, "village"),
    ("Kaukinen", 67.6090, 24.7610, "village"),
    ("Kongas", 67.8270, 25.1040, "village"),
    ("Tepasto", 67.9770, 25.2660, "village"),
    ("Raattama", 68.0930, 24.1580, "village"),
    ("Muonio", 67.9550, 23.6820, "town"),
    ("Kolari", 67.3300, 23.7770, "town"),
    ("Pokka", 68.1670, 25.8000, "village"),
    ("Sattanen", 67.4550, 26.9000, "village"),
    ("Kelujarvi", 67.4770, 27.0980, "village"),
    ("Kersilo", 67.2930, 26.7400, "village"),
    ("Jeesio", 67.6880, 26.7060, "village"),
    ("Unari", 67.1470, 26.1130, "village"),
]

FALLBACK_MAJOR_CITIES = [
    ("Helsinki", 60.1699, 24.9384, "city"),
    ("Tampere", 61.4978, 23.7610, "city"),
    ("Turku", 60.4518, 22.2666, "city"),
    ("Oulu", 65.0121, 25.4651, "city"),
    ("Rovaniemi", 66.5039, 25.7294, "city"),
    ("Kemi", 65.7360, 24.5637, "town"),
    ("Tornio", 65.8481, 24.1466, "town"),
    ("Kittila", 67.6555, 24.9088, "town"),
    ("Sodankyla", 67.4167, 26.6000, "town"),
    ("Kolari", 67.3300, 23.7770, "town"),
    ("Muonio", 67.9550, 23.6820, "town"),
]


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def clean_for_gpkg(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    out = gdf.copy()
    for col in out.columns:
        if col == "geometry":
            continue
        if pd.api.types.is_object_dtype(out[col]) or pd.api.types.is_bool_dtype(out[col]):
            out[col] = out[col].apply(
                lambda value: json.dumps(value) if isinstance(value, (list, dict)) else value
            )
            out[col] = out[col].astype("string").fillna("")
    return out


def write_layer(gdf: gpd.GeoDataFrame, path: Path, layer: str) -> None:
    if gdf.empty:
        log.warning("Skipping empty layer: %s", layer)
        return
    clean_for_gpkg(gdf).to_file(path, layer=layer, driver="GPKG")


def assign_map_numbers(grid: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    out = grid.copy()
    out["_row_y"] = out["centroid_y"].round(3)
    row_lookup = {
        row_y: idx + 1
        for idx, row_y in enumerate(sorted(out["_row_y"].unique(), reverse=True))
    }
    out["row_index"] = out["_row_y"].map(row_lookup).astype(int)
    out = out.sort_values(["row_index", "centroid_x"], ascending=[True, True]).reset_index(drop=True)
    out["col_index"] = out.groupby("row_index").cumcount() + 1
    out["map_number"] = np.arange(1, len(out) + 1, dtype=int)
    return out.drop(columns="_row_y")


def load_candidate_context(outputs: Path) -> pd.DataFrame:
    cand_path = outputs / "geology_ranked_modelling_candidates.gpkg"
    if not cand_path.exists():
        return pd.DataFrame(columns=["cell_id"])

    cand = gpd.read_file(cand_path).drop(columns="geometry", errors="ignore")
    keep = [
        "cell_id",
        "cluster_id",
        "legal_status_conservative",
        "legal_status_strict_active_only",
        "restriction_status",
        "final_status",
        "model_score",
        "baseline_score",
        "model_minus_baseline",
        "topk_percentile",
        "false_positive_flags",
    ]
    keep = [col for col in keep if col in cand.columns]
    context = cand[keep].copy()
    context = context.rename(columns={
        "legal_status_conservative": "legal_status",
        "final_status": "base_candidate_status",
    })

    audit_path = outputs / "review_candidates_audited.csv"
    if audit_path.exists():
        audit = pd.read_csv(audit_path)
        audit_keep = [
            "cell_id",
            "audit_status",
            "multi_layer_convergence",
            "top_contributing_features",
            "signal_domain_count",
            "gravity_signal",
            "till_signal",
            "structure_lithology_domain",
        ]
        audit_keep = [col for col in audit_keep if col in audit.columns]
        context = context.merge(audit[audit_keep], on="cell_id", how="left")

    if "audit_status" not in context.columns:
        context["audit_status"] = ""
    if "multi_layer_convergence" not in context.columns:
        context["multi_layer_convergence"] = False

    def candidate_status(row: pd.Series) -> str:
        base = row.get("base_candidate_status", "insufficient_data")
        audit = row.get("audit_status")
        if base == "model_supported_review_candidate":
            if audit == "multi_layer_review_candidate":
                return "structure_gravity_review_candidate"
            if audit == "structure_only_candidate":
                return "structure_only_candidate"
            return "structure_only_candidate"
        return base if isinstance(base, str) and base else "insufficient_data"

    context["candidate_status"] = context.apply(candidate_status, axis=1)
    return context


def read_optional_vector(path: Path, target_crs: str = PROJECT_CRS) -> gpd.GeoDataFrame | None:
    if not path.exists():
        return None
    try:
        gdf = gpd.read_file(path)
        if gdf.empty:
            return None
        return gdf.to_crs(target_crs)
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not read %s: %s", path, exc)
        return None


def clip_to(gdf: gpd.GeoDataFrame | None, geom, name: str) -> gpd.GeoDataFrame | None:
    if gdf is None or gdf.empty:
        return None
    try:
        return gpd.clip(gdf, geom).reset_index(drop=True)
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not clip %s: %s", name, exc)
        return gdf[gdf.intersects(geom)].copy().reset_index(drop=True)


def local_settlement_candidates(command_dir: Path, outputs: Path) -> list[Path]:
    return [
        command_dir / "settlements.gpkg",
        outputs / "clgb_settlement_labels.gpkg",
        Path("/Users/mk/Desktop/clgb_settlement_labels.gpkg"),
    ]


def load_local_settlements(command_dir: Path, outputs: Path, clgb_buffer) -> tuple[gpd.GeoDataFrame | None, str]:
    for path in local_settlement_candidates(command_dir, outputs):
        if not path.exists():
            continue
        try:
            gdf = gpd.read_file(path).to_crs(PROJECT_CRS)
        except Exception as exc:  # noqa: BLE001
            log.warning("Local settlement file unreadable %s: %s", path, exc)
            continue
        if gdf.empty or not gdf.intersects(clgb_buffer).any():
            continue
        source_values = set(gdf.get("source", pd.Series(dtype=str)).astype(str).str.lower())
        robust = len(gdf) >= 25 and not any("fallback" in s for s in source_values)
        if robust:
            return normalize_settlements(gdf, f"local settlement file ({path})"), f"local settlement file ({path})"
        log.info("Local settlement file found but not robust enough: %s (%d features)", path, len(gdf))
    return None, ""


def download_geonames(raw_dir: Path, timeout_s: int = 35) -> Path | None:
    ensure_dir(raw_dir)
    zip_path = raw_dir / "FI.zip"
    if zip_path.exists() and zip_path.stat().st_size > 100_000:
        return zip_path
    try:
        req = urllib.request.Request(GEONAMES_URL, headers={"User-Agent": "gold-sniper-command-map/1.0"})
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            data = resp.read()
        if len(data) < 100_000:
            raise RuntimeError(f"GeoNames response unexpectedly small: {len(data)} bytes")
        zip_path.write_bytes(data)
        return zip_path
    except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
        log.warning("GeoNames download failed: %s", exc)
        return None


def place_type_from_geonames(feature_code: str, population: int) -> str:
    if feature_code == "PPLC" or population >= 50_000:
        return "city"
    if feature_code.startswith("PPLA") or population >= 5_000:
        return "town"
    if population >= 500:
        return "municipality_centre"
    if population >= 50:
        return "village"
    return "hamlet"


def parse_geonames(zip_path: Path) -> gpd.GeoDataFrame | None:
    columns = [
        "geonameid", "name", "asciiname", "alternatenames", "latitude", "longitude",
        "feature_class", "feature_code", "country_code", "cc2", "admin1_code",
        "admin2_code", "admin3_code", "admin4_code", "population", "elevation",
        "dem", "timezone", "modification_date",
    ]
    try:
        with zipfile.ZipFile(zip_path) as zf:
            with zf.open("FI.txt") as fh:
                text = io.TextIOWrapper(fh, encoding="utf-8")
                df = pd.read_csv(text, sep="\t", header=None, names=columns, quoting=csv.QUOTE_NONE)
    except Exception as exc:  # noqa: BLE001
        log.warning("GeoNames parse failed: %s", exc)
        return None

    df = df[df["feature_class"] == "P"].copy()
    useful_codes = {"PPLC", "PPLA", "PPLA2", "PPLA3", "PPLA4", "PPL", "PPLF", "PPLG", "PPLL", "PPLX"}
    df = df[df["feature_code"].isin(useful_codes)].copy()
    df["population"] = pd.to_numeric(df["population"], errors="coerce").fillna(0).astype(int)
    df["place_type"] = [
        place_type_from_geonames(code, pop) for code, pop in zip(df["feature_code"], df["population"])
    ]
    rows = []
    for row in df.itertuples():
        name = row.name if isinstance(row.name, str) and row.name else row.asciiname
        if not isinstance(name, str) or not name.strip():
            continue
        rows.append({
            "name": name.strip(),
            "place_type": row.place_type,
            "feature_code": row.feature_code,
            "population": row.population,
            "source": "GeoNames FI country dump",
            "latitude": float(row.latitude),
            "longitude": float(row.longitude),
            "geometry": Point(float(row.longitude), float(row.latitude)),
        })
    if not rows:
        return None
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=WGS84).to_crs(PROJECT_CRS)


def fallback_settlements() -> gpd.GeoDataFrame:
    rows = [
        {
            "name": name,
            "place_type": place_type,
            "feature_code": "",
            "population": 0,
            "source": "fallback curated settlement list",
            "latitude": lat,
            "longitude": lon,
            "geometry": Point(lon, lat),
        }
        for name, lat, lon, place_type in FALLBACK_SETTLEMENTS
    ]
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=WGS84).to_crs(PROJECT_CRS)


def fallback_major_cities() -> gpd.GeoDataFrame:
    rows = [
        {
            "name": name,
            "place_type": place_type,
            "population": 0,
            "source": "fallback major city list",
            "latitude": lat,
            "longitude": lon,
            "geometry": Point(lon, lat),
        }
        for name, lat, lon, place_type in FALLBACK_MAJOR_CITIES
    ]
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=WGS84).to_crs(PROJECT_CRS)


def normalize_settlements(gdf: gpd.GeoDataFrame, source: str) -> gpd.GeoDataFrame:
    out = gdf.copy()
    if "name" not in out.columns:
        name_cols = [col for col in out.columns if col.lower() in {"name", "nimi", "asciiname"}]
        out["name"] = out[name_cols[0]] if name_cols else ""
    if "place_type" not in out.columns:
        if "place" in out.columns:
            out["place_type"] = out["place"].astype(str)
        else:
            out["place_type"] = "locality"
    if "source" not in out.columns:
        out["source"] = source
    out = out.to_crs(WGS84)
    out["latitude"] = out.geometry.y
    out["longitude"] = out.geometry.x
    return out.to_crs(PROJECT_CRS)


def filter_and_rank_settlements(all_places: gpd.GeoDataFrame, clgb_geom, clgb_buffer) -> gpd.GeoDataFrame:
    places = all_places.copy()
    places = places[places.geometry.within(clgb_buffer)].copy()
    if places.empty:
        return places
    places["distance_to_clgb_km"] = (places.geometry.distance(clgb_geom) / 1000.0).round(2)
    places.loc[places.geometry.within(clgb_geom), "distance_to_clgb_km"] = 0.0
    places["place_rank"] = places["place_type"].map(PLACE_RANK).fillna(9).astype(int)
    places["name_key"] = places["name"].astype(str).str.casefold()
    places = (
        places.sort_values(["name_key", "place_rank", "distance_to_clgb_km"])
        .drop_duplicates("name_key", keep="first")
        .sort_values(["place_rank", "distance_to_clgb_km", "name"])
        .reset_index(drop=True)
    )
    places["settlement_id"] = np.arange(1, len(places) + 1, dtype=int)
    return places.drop(columns=["name_key"])


def build_settlements(command_dir: Path, outputs: Path, data_root: Path, clgb_geom) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, str, bool]:
    clgb_buffer = clgb_geom.buffer(SETTLEMENT_BUFFER_M)
    local, local_source = load_local_settlements(command_dir, outputs, clgb_buffer)
    if local is not None:
        source = local_source
        places_all = local
        fallback_used = False
    else:
        zip_path = download_geonames(data_root / "raw" / "geonames")
        places_all = parse_geonames(zip_path) if zip_path else None
        if places_all is not None:
            source = f"GeoNames FI country dump ({GEONAMES_URL})"
            fallback_used = False
        else:
            places_all = fallback_settlements()
            source = "fallback curated settlement list; GeoNames bulk retrieval failed"
            fallback_used = True
            write_settlement_needed(command_dir)

    settlements = filter_and_rank_settlements(places_all, clgb_geom, clgb_buffer)
    if settlements.empty:
        settlements = filter_and_rank_settlements(fallback_settlements(), clgb_geom, clgb_buffer)
        source = "fallback curated settlement list; robust source returned no buffered settlements"
        fallback_used = True
        write_settlement_needed(command_dir)

    if not fallback_used and "GeoNames" in source:
        major = places_all.copy()
        major["population"] = pd.to_numeric(major.get("population", 0), errors="coerce").fillna(0).astype(int)
        major["place_rank"] = major["place_type"].map(PLACE_RANK).fillna(9).astype(int)
        major = major[(major["population"] >= 40_000) | (major["name"].isin(["Rovaniemi", "Kittila", "Kittilä", "Sodankyla", "Sodankylä", "Kolari", "Muonio"]))]
        major = major.sort_values(["place_rank", "population"], ascending=[True, False]).head(45).copy()
    else:
        major = fallback_major_cities()
    major = normalize_settlements(major, source)
    return settlements, major, source, fallback_used


def write_settlement_needed(command_dir: Path) -> None:
    text = """# Settlement Data Needed

The command-map script could not retrieve a robust settlement dataset online.

Preferred manual dataset:
- Source: GeoNames country dump for Finland
- URL: https://download.geonames.org/export/dump/FI.zip
- Expected file: `FI.zip` containing `FI.txt`
- Drop folder: `data/raw/geonames/FI.zip`

Acceptable alternatives:
- OpenStreetMap populated-place points as GeoPackage/Shapefile/GeoJSON
- GeoNames populated-place export as CSV/TXT
- Any open settlement point dataset with name, latitude, longitude, and place type

Do not use:
- Natural feature labels
- Raster map labels
- PDF/PNG/JPG legend images

After placing the file, run:

```bash
/Users/mk/miniconda3/envs/geoarb/bin/python scripts/25_build_zoomable_command_map.py
```
"""
    (command_dir / "SETTLEMENT_DATA_NEEDED.md").write_text(text, encoding="utf-8")


def assign_nearest_settlements(grid: gpd.GeoDataFrame, settlements: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    out = grid.copy()
    tree = cKDTree(np.c_[settlements.geometry.x, settlements.geometry.y])
    dist, idx = tree.query(np.c_[out["centroid_x"], out["centroid_y"]], k=1)
    nearest = settlements.iloc[idx].reset_index(drop=True)
    out["nearest_settlement"] = nearest["name"].to_numpy()
    out["nearest_settlement_type"] = nearest["place_type"].to_numpy()
    out["distance_to_nearest_settlement_km"] = (dist / 1000.0).round(2)
    return out


def make_review_layers(numbered: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, gpd.GeoDataFrame]:
    review = numbered[numbered["candidate_status"].isin([
        "structure_only_candidate", "structure_gravity_review_candidate"
    ])].copy()
    multilayer = review[review["candidate_status"] == "structure_gravity_review_candidate"].copy()
    structure_only = review[review["candidate_status"] == "structure_only_candidate"].copy()
    points = review.copy()
    points["geometry"] = gpd.points_from_xy(points["centroid_x"], points["centroid_y"], crs=numbered.crs)
    points = gpd.GeoDataFrame(points, geometry="geometry", crs=numbered.crs)
    return review, multilayer, structure_only, points


def qml_single_fill(fill: str, outline: str, outline_width: float = 0.3, alpha: float = 1.0) -> str:
    return f"""<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.34.0" styleCategories="AllStyleCategories">
  <renderer-v2 type="singleSymbol" symbollevels="0" enableorderby="0" forceraster="0">
    <symbols>
      <symbol type="fill" name="0" alpha="{alpha}">
        <layer class="SimpleFill" pass="0" locked="0" enabled="1">
          <prop k="color" v="{fill}"/>
          <prop k="outline_color" v="{outline}"/>
          <prop k="outline_width" v="{outline_width}"/>
        </layer>
      </symbol>
    </symbols>
  </renderer-v2>
</qgis>
"""


def qml_single_line(color: str, width: float = 0.4) -> str:
    return f"""<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.34.0" styleCategories="AllStyleCategories">
  <renderer-v2 type="singleSymbol" symbollevels="0" enableorderby="0" forceraster="0">
    <symbols>
      <symbol type="line" name="0" alpha="1">
        <layer class="SimpleLine" pass="0" locked="0" enabled="1">
          <prop k="line_color" v="{color}"/>
          <prop k="line_width" v="{width}"/>
        </layer>
      </symbol>
    </symbols>
  </renderer-v2>
</qgis>
"""


def qml_settlements(label_field: str = "name") -> str:
    return f"""<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.34.0" styleCategories="AllStyleCategories">
  <renderer-v2 type="singleSymbol" symbollevels="0" enableorderby="0" forceraster="0">
    <symbols>
      <symbol type="marker" name="0" alpha="1">
        <layer class="SimpleMarker" pass="0" locked="0" enabled="1">
          <prop k="name" v="circle"/>
          <prop k="color" v="0,0,0,255"/>
          <prop k="outline_color" v="255,255,255,255"/>
          <prop k="size" v="1.6"/>
        </layer>
      </symbol>
    </symbols>
  </renderer-v2>
  <customproperties>
    <Option type="Map">
      <Option name="labeling" type="QString" value="pal"/>
      <Option name="labeling/enabled" type="bool" value="true"/>
      <Option name="labeling/fieldName" type="QString" value="{label_field}"/>
      <Option name="labeling/fontFamily" type="QString" value="Arial"/>
      <Option name="labeling/fontSize" type="double" value="9"/>
      <Option name="labeling/bufferDraw" type="bool" value="true"/>
      <Option name="labeling/bufferSize" type="double" value="0.8"/>
      <Option name="labeling/scaleVisibility" type="bool" value="true"/>
      <Option name="labeling/scaleMax" type="double" value="250000"/>
      <Option name="labeling/scaleMin" type="double" value="1"/>
    </Option>
  </customproperties>
</qgis>
"""


def qml_grid() -> str:
    symbols = []
    categories = []
    for idx, status in enumerate([
        "restricted_area",
        "legally_blocked",
        "insufficient_data",
        "structure_only_candidate",
        "structure_gravity_review_candidate",
    ]):
        color = STATUS_COLORS[status]
        edge = STATUS_EDGES[status]
        rgba = hex_to_qgis_rgba(color, alpha=90 if status in {"restricted_area", "legally_blocked"} else 70)
        edge_rgba = hex_to_qgis_rgba(edge, alpha=255)
        width = 0.18
        if status == "structure_only_candidate":
            width = 0.8
        if status == "structure_gravity_review_candidate":
            width = 1.2
        symbols.append(f"""
      <symbol type="fill" name="{idx}" alpha="1">
        <layer class="SimpleFill" pass="0" locked="0" enabled="1">
          <prop k="color" v="{rgba}"/>
          <prop k="outline_color" v="{edge_rgba}"/>
          <prop k="outline_width" v="{width}"/>
        </layer>
      </symbol>""")
        categories.append(f'<category render="true" symbol="{idx}" value="{status}" label="{status}"/>')
    return f"""<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.34.0" styleCategories="AllStyleCategories">
  <renderer-v2 attr="candidate_status" type="categorizedSymbol" symbollevels="0" enableorderby="0" forceraster="0">
    <categories>
      {''.join(categories)}
    </categories>
    <symbols>
      {''.join(symbols)}
    </symbols>
  </renderer-v2>
  <customproperties>
    <Option type="Map">
      <Option name="labeling" type="QString" value="pal"/>
      <Option name="labeling/enabled" type="bool" value="true"/>
      <Option name="labeling/fieldName" type="QString" value="map_number"/>
      <Option name="labeling/fontFamily" type="QString" value="Arial"/>
      <Option name="labeling/fontSize" type="double" value="7"/>
      <Option name="labeling/bufferDraw" type="bool" value="true"/>
      <Option name="labeling/bufferSize" type="double" value="0.6"/>
      <Option name="labeling/scaleVisibility" type="bool" value="true"/>
      <Option name="labeling/scaleMax" type="double" value="30000"/>
      <Option name="labeling/scaleMin" type="double" value="1"/>
    </Option>
  </customproperties>
</qgis>
"""


def qml_review_points() -> str:
    return """<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.34.0" styleCategories="AllStyleCategories">
  <renderer-v2 attr="candidate_status" type="categorizedSymbol" symbollevels="0" enableorderby="0" forceraster="0">
    <categories>
      <category render="true" symbol="0" value="structure_gravity_review_candidate" label="16 structure+gravity review candidates"/>
      <category render="true" symbol="1" value="structure_only_candidate" label="47 structure-only candidates"/>
    </categories>
    <symbols>
      <symbol type="marker" name="0" alpha="1">
        <layer class="SimpleMarker" pass="0" locked="0" enabled="1">
          <prop k="name" v="star"/>
          <prop k="color" v="75,63,188,255"/>
          <prop k="outline_color" v="255,255,255,255"/>
          <prop k="outline_width" v="0.35"/>
          <prop k="size" v="4.0"/>
        </layer>
      </symbol>
      <symbol type="marker" name="1" alpha="1">
        <layer class="SimpleMarker" pass="0" locked="0" enabled="1">
          <prop k="name" v="circle"/>
          <prop k="color" v="246,196,69,255"/>
          <prop k="outline_color" v="153,95,0,255"/>
          <prop k="outline_width" v="0.25"/>
          <prop k="size" v="2.6"/>
        </layer>
      </symbol>
    </symbols>
  </renderer-v2>
</qgis>
"""


def hex_to_qgis_rgba(hex_color: str, alpha: int = 255) -> str:
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return f"{r},{g},{b},{alpha}"


def write_qml_files(command_dir: Path) -> dict[str, Path]:
    styles_dir = ensure_dir(command_dir / "styles")
    styles = {
        "finland_outline": qml_single_fill("230,230,230,110", "145,145,145,255", 0.25),
        "clgb_aoi_box": qml_single_fill("0,0,0,0", "20,58,120,255", 1.4),
        "current_project_aoi": qml_single_fill("0,0,0,0", "20,58,120,255", 0.8),
        "clgb_aoi": qml_single_fill("0,0,0,0", "20,58,120,255", 1.0),
        "bedrock_geology_clip": qml_single_fill("186,206,168,70", "130,150,118,120", 0.15),
        "structures_faults_clip": qml_single_line("70,70,70,230", 0.45),
        "gravity_gradient_cells": qml_single_fill("91,134,168,80", "63,98,130,150", 0.12),
        "tukes_active_rights": qml_single_fill("230,82,82,70", "160,45,45,255", 0.35),
        "tukes_pending_rights": qml_single_fill("245,168,61,70", "168,100,0,255", 0.35),
        "tukes_cooling_off": qml_single_fill("145,112,201,70", "85,52,145,255", 0.35),
        "natura2000": qml_single_fill("80,180,100,80", "40,130,65,255", 0.3),
        "protected_areas": qml_single_fill("40,150,80,75", "20,100,50,255", 0.3),
        "groundwater": qml_single_fill("90,170,220,65", "35,110,170,255", 0.3),
        "open_cells_after_restrictions": qml_single_fill("255,255,255,0", "35,160,80,180", 0.22),
        "clgb_grid_2km_numbered": qml_grid(),
        "review_candidates_all": qml_single_fill("0,0,0,0", "55,55,55,255", 0.8),
        "review_candidates_multilayer": qml_single_fill("75,63,188,80", "23,16,111,255", 1.2),
        "review_candidates_structure_only": qml_single_fill("246,196,69,80", "153,95,0,255", 0.8),
        "review_candidate_points": qml_review_points(),
        "settlements": qml_settlements("name"),
        "finland_major_cities": qml_settlements("name"),
    }
    paths = {}
    for name, qml in styles.items():
        path = styles_dir / f"{name}.qml"
        path.write_text(qml, encoding="utf-8")
        paths[name] = path
    return paths


def store_gpkg_style(gpkg_path: Path, layer: str, qml_path: Path) -> None:
    if not gpkg_path.exists() or not qml_path.exists():
        return
    qml = qml_path.read_text(encoding="utf-8")
    with sqlite3.connect(gpkg_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS layer_styles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                f_table_catalog TEXT,
                f_table_schema TEXT,
                f_table_name TEXT,
                f_geometry_column TEXT,
                styleName TEXT,
                styleQML TEXT,
                styleSLD TEXT,
                useAsDefault INTEGER,
                description TEXT,
                owner TEXT,
                ui TEXT,
                update_time DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute("DELETE FROM layer_styles WHERE f_table_name = ?", (layer,))
        conn.execute(
            """
            INSERT INTO layer_styles (
                f_table_catalog, f_table_schema, f_table_name, f_geometry_column,
                styleName, styleQML, styleSLD, useAsDefault, description, owner, ui
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("", "", layer, "geom", "default", qml, "", 1, "GeoArb command map default style", "gold_sniper", ""),
        )
        conn.commit()


def qml_inner(qml_path: Path | None) -> str:
    if qml_path is None or not qml_path.exists():
        return "<customproperties/>"
    lines = []
    for line in qml_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("<!DOCTYPE") or stripped.startswith("<qgis") or stripped == "</qgis>":
            continue
        lines.append(line)
    return "\n".join(lines) if lines else "<customproperties/>"


def qgs_layer(layer_id: str, name: str, source: str, geometry: str, style_xml: str) -> str:
    return f"""
    <maplayer simplifyDrawingHints="1" minScale="100000000" maxScale="0" styleCategories="AllStyleCategories" type="vector" geometry="{geometry}" labelsEnabled="1">
      <id>{escape(layer_id)}</id>
      <layername>{escape(name)}</layername>
      <datasource>{escape(source)}</datasource>
      <provider encoding="UTF-8">ogr</provider>
      {style_xml}
    </maplayer>"""


def layer_tree_layer(layer_id: str, name: str, source: str, checked: bool = True) -> str:
    checked_value = "Qt::Checked" if checked else "Qt::Unchecked"
    return f'<layer-tree-layer expanded="1" checked="{checked_value}" id="{escape(layer_id)}" name="{escape(name)}" source="{escape(source)}" providerKey="ogr"><customproperties/></layer-tree-layer>'


def write_qgis_project(command_dir: Path, layer_specs: list[dict], styles: dict[str, Path]) -> Path:
    groups = [
        ("Finland context", [
            "finland_outline", "major_cities", "clgb_aoi_box", "current_project_aoi",
        ]),
        ("CLGB base", [
            "clgb_aoi", "bedrock_geology_clip", "structures_faults_clip", "gravity_gradient_cells",
        ]),
        ("Legal / restrictions", [
            "tukes_active_rights", "tukes_pending_rights", "tukes_cooling_off",
            "natura2000", "protected_areas", "groundwater", "open_cells_after_restrictions",
        ]),
        ("Numbered grid", ["clgb_grid_2km_numbered"]),
        ("Review candidates", [
            "review_candidates_multilayer", "review_candidates_structure_only", "review_candidate_points",
        ]),
        ("Settlements", ["settlements"]),
    ]
    spec_by_key = {spec["key"]: spec for spec in layer_specs}
    layer_tree_groups = []
    for group_name, keys in groups:
        layer_lines = []
        for key in keys:
            spec = spec_by_key.get(key)
            if not spec:
                continue
            layer_lines.append(layer_tree_layer(spec["id"], spec["name"], spec["source"], spec.get("checked", True)))
        layer_tree_groups.append(
            f'<layer-tree-group expanded="1" checked="Qt::Checked" name="{escape(group_name)}">\n'
            + "\n".join(layer_lines)
            + "\n</layer-tree-group>"
        )
    maplayers = "\n".join(
        qgs_layer(
            spec["id"],
            spec["name"],
            spec["source"],
            spec["geometry"],
            qml_inner(styles.get(spec.get("style_key", spec["key"]))),
        )
        for spec in layer_specs
    )
    qgs = f"""<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.34.0" projectname="GeoArb Finland Command Map">
  <title>GeoArb Finland Command Map</title>
  <homePath>{escape(str(command_dir))}</homePath>
  <projectCrs>
    <spatialrefsys>
      <proj4>+proj=utm +zone=35 +ellps=GRS80 +units=m +no_defs</proj4>
      <srsid>3067</srsid>
      <srid>3067</srid>
      <authid>EPSG:3067</authid>
      <description>ETRS89 / TM35FIN(E,N)</description>
      <projectionacronym>utm</projectionacronym>
      <ellipsoidacronym>EPSG:7019</ellipsoidacronym>
      <geographicflag>false</geographicflag>
    </spatialrefsys>
  </projectCrs>
  <layer-tree-group expanded="1" checked="Qt::Checked" name="">
    {''.join(layer_tree_groups)}
  </layer-tree-group>
  <mapcanvas name="theMapCanvas" annotationsVisible="1">
    <units>meters</units>
    <destinationsrs>
      <spatialrefsys>
        <authid>EPSG:3067</authid>
        <srid>3067</srid>
      </spatialrefsys>
    </destinationsrs>
  </mapcanvas>
  <projectlayers>
    {maplayers}
  </projectlayers>
</qgis>
"""
    qgs_name = "GeoArb_Finland_Command_Map.qgs"
    qgz_path = command_dir / "GeoArb_Finland_Command_Map.qgz"
    with zipfile.ZipFile(qgz_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(qgs_name, qgs)
    (command_dir / qgs_name).write_text(qgs, encoding="utf-8")
    return qgz_path


def plot_status_grid(ax, grid: gpd.GeoDataFrame, linewidth: float = 0.1) -> None:
    for status, part in grid.groupby("candidate_status", dropna=False):
        status = str(status)
        face = STATUS_COLORS.get(status, "#ededed")
        edge = STATUS_EDGES.get(status, "#c5c5c5")
        alpha = 0.34 if status in {"restricted_area", "legally_blocked"} else 0.22
        width = linewidth
        if status == "structure_only_candidate":
            width = 0.42
        if status == "structure_gravity_review_candidate":
            width = 0.75
        part.plot(ax=ax, facecolor=face, edgecolor=edge, linewidth=width, alpha=alpha)


def add_scale_bar(ax, length_km: int, location=(0.07, 0.07)) -> None:
    xmin, xmax = ax.get_xlim()
    ymin, ymax = ax.get_ylim()
    x0 = xmin + (xmax - xmin) * location[0]
    y0 = ymin + (ymax - ymin) * location[1]
    length_m = length_km * 1000
    ax.plot([x0, x0 + length_m], [y0, y0], color="black", linewidth=2)
    ax.plot([x0, x0], [y0 - length_m * 0.03, y0 + length_m * 0.03], color="black", linewidth=1)
    ax.plot([x0 + length_m, x0 + length_m], [y0 - length_m * 0.03, y0 + length_m * 0.03], color="black", linewidth=1)
    ax.text(x0 + length_m / 2, y0 + length_m * 0.07, f"{length_km} km", ha="center", fontsize=8)


def make_finland_pdf(command_dir: Path, finland: gpd.GeoDataFrame, clgb_box: gpd.GeoDataFrame, major: gpd.GeoDataFrame) -> None:
    fig, ax = plt.subplots(figsize=(10, 15))
    finland.plot(ax=ax, facecolor="#e6e6e6", edgecolor="#909090", linewidth=0.45)
    clgb_box.plot(ax=ax, facecolor="none", edgecolor="#143a78", linewidth=2.2)
    major.plot(ax=ax, color="#111111", markersize=7)
    for row in major.itertuples():
        ax.text(row.geometry.x + 9000, row.geometry.y + 9000, row.name, fontsize=6.5, color="#111111")
    xmin, ymin, xmax, ymax = finland.total_bounds
    ax.set_xlim(xmin - 80_000, xmax + 80_000)
    ax.set_ylim(ymin - 80_000, ymax + 80_000)
    ax.set_aspect("equal")
    ax.set_title("Finland Context - CLGB Command Map", fontsize=14)
    ax.text(0.94, 0.95, "N", transform=ax.transAxes, ha="center", va="center", fontsize=13, weight="bold")
    ax.annotate("", xy=(0.94, 0.93), xytext=(0.94, 0.88), xycoords="axes fraction",
                arrowprops={"arrowstyle": "-|>", "lw": 1.5, "color": "black"})
    add_scale_bar(ax, 200, location=(0.08, 0.05))
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(command_dir / "finland_context_vector.pdf")
    plt.close(fig)


def make_clgb_pdf(command_dir: Path, grid: gpd.GeoDataFrame, clgb: gpd.GeoDataFrame,
                  settlements: gpd.GeoDataFrame, structures: gpd.GeoDataFrame | None,
                  review_points: gpd.GeoDataFrame) -> None:
    fig, ax = plt.subplots(figsize=(30, 34))
    clgb.plot(ax=ax, facecolor="none", edgecolor="#143a78", linewidth=1.3)
    plot_status_grid(ax, grid, linewidth=0.11)
    if structures is not None and not structures.empty:
        structures.plot(ax=ax, color="#444444", linewidth=0.32, alpha=0.75)
    if not settlements.empty:
        settlements.plot(ax=ax, color="#111111", markersize=6, zorder=5)
        for row in settlements.itertuples():
            size = 5.8 if row.place_rank <= 2 else 4.8
            ax.text(row.geometry.x + 450, row.geometry.y + 450, row.name,
                    fontsize=size, color="#111111", zorder=6,
                    bbox={"facecolor": "white", "alpha": 0.58, "edgecolor": "none", "pad": 0.35})
    for row in grid.itertuples():
        ax.text(row.centroid_x, row.centroid_y, str(row.map_number),
                ha="center", va="center", fontsize=2.9, color="#1f1f1f", zorder=7)
    for status, marker, color, size in [
        ("structure_gravity_review_candidate", "*", "#4b3fbc", 45),
        ("structure_only_candidate", "o", "#995f00", 18),
    ]:
        part = review_points[review_points["candidate_status"] == status]
        if not part.empty:
            part.plot(ax=ax, marker=marker, color=color, markersize=size, zorder=8)
    xmin, ymin, xmax, ymax = grid.total_bounds
    ax.set_xlim(xmin - 9000, xmax + 9000)
    ax.set_ylim(ymin - 9000, ymax + 9000)
    ax.set_aspect("equal")
    ax.set_title("CLGB Zoom - Numbered 2 km Grid", fontsize=16)
    add_scale_bar(ax, 20, location=(0.06, 0.055))
    ax.text(0.95, 0.94, "N", transform=ax.transAxes, ha="center", va="center", fontsize=13, weight="bold")
    ax.annotate("", xy=(0.95, 0.925), xytext=(0.95, 0.875), xycoords="axes fraction",
                arrowprops={"arrowstyle": "-|>", "lw": 1.5, "color": "black"})
    ax.set_xlabel("Easting EPSG:3067 (m)")
    ax.set_ylabel("Northing EPSG:3067 (m)")
    ax.grid(alpha=0.16, linewidth=0.25)
    fig.tight_layout()
    fig.savefig(command_dir / "clgb_zoom_vector.pdf")
    plt.close(fig)


def build_reports(command_dir: Path, numbered: gpd.GeoDataFrame, settlements: gpd.GeoDataFrame,
                  settlement_source: str, fallback_used: bool, multilayer: gpd.GeoDataFrame,
                  structure_only: gpd.GeoDataFrame) -> None:
    first = numbered.sort_values("map_number").iloc[0]
    last = numbered.sort_values("map_number").iloc[-1]
    multilayer_rows = []
    for row in multilayer.sort_values("map_number").itertuples():
        multilayer_rows.append(
            f"| {row.map_number} | {row.cell_id} | {row.nearest_settlement} | "
            f"{row.distance_to_nearest_settlement_km:.2f} | {row.centroid_lat:.6f} | {row.centroid_lon:.6f} |"
        )
    multilayer_table = "\n".join(multilayer_rows)

    report = f"""# Zoomable Command Map Report

This is a spatial-orientation product only. It does not create target memos, gold targets, drill targets, reservation candidates, or staking claims.

## Why The Previous 18-Page Atlas Was Created

The previous atlas tiled the CLGB grid into 18 static pages because a single page cannot legibly show 3,798 grid labels at print scale. That solved print readability, but it was the wrong primary product for spatial intuition because navigation is page-based.

## Why This Product Is Better

The new command map is vector-first. The primary deliverable is a QGIS project with searchable vector layers, scale-dependent grid labels, settlement labels, legal/restriction layers, and candidate review layers. You can zoom deeply without raster blur and use QGIS attribute filters to find any `map_number` or `cell_id`.

## How To Open

Open:

`data/outputs/qgis_command_map/GeoArb_Finland_Command_Map.qgz`

The data layers sit in the same folder as GeoPackages. If QGIS asks about paths, keep the whole `qgis_command_map` folder together.

## Useful Layers

- Finland context: start here for all-Finland orientation and the CLGB box.
- Numbered grid: turn this on for the 2 km grid. Labels are `map_number`.
- Review candidates: shows the 16 structure+gravity review cells and 47 structure-only review cells.
- Legal / restrictions: turn these on/off to inspect masks.
- Settlements: labels towns/villages/hamlets near the CLGB AOI.

## Search By Map Number

In QGIS, open the attribute table for `clgb_grid_2km_numbered`, then filter:

`"map_number" = 2458`

You can also use Select by Expression with the same expression.

## Coordinate Lookup

Open:

`data/outputs/qgis_command_map/clgb_grid_2km_number_lookup.csv`

It maps each `map_number` to `cell_id`, EPSG:3067 centroid, WGS84 latitude/longitude, candidate status, and nearest settlement.

## Counts

- Numbered 2 km cells: **{len(numbered)}**
- Settlements labelled: **{len(settlements)}**
- Settlement source: **{settlement_source}**
- Fallback settlement list used: **{'YES' if fallback_used else 'NO'}**
- Review candidates: **{len(multilayer) + len(structure_only)}**
- Multi-layer structure+gravity review candidates: **{len(multilayer)}**
- Structure-only review candidates: **{len(structure_only)}**

## Numbering Extents

- First map number: **{int(first.map_number)}**, cell `{first.cell_id}`, centroid EPSG:3067 ({first.centroid_x:.1f}, {first.centroid_y:.1f}), lat/lon ({first.centroid_lat:.6f}, {first.centroid_lon:.6f})
- Last map number: **{int(last.map_number)}**, cell `{last.cell_id}`, centroid EPSG:3067 ({last.centroid_x:.1f}, {last.centroid_y:.1f}), lat/lon ({last.centroid_lat:.6f}, {last.centroid_lon:.6f})

## The 16 Multi-Layer Review Candidates

| map_number | cell_id | nearest_settlement | distance_km | centroid_lat | centroid_lon |
|------------|---------|--------------------|-------------|--------------|--------------|
{multilayer_table}
"""
    (command_dir / "COMMAND_MAP_REPORT.md").write_text(report, encoding="utf-8")

    readme = f"""# GeoArb Finland Command Map

Open `GeoArb_Finland_Command_Map.qgz` in QGIS.

Primary workflow:

1. Use the Finland context group to orient yourself to the CLGB box.
2. Zoom into the CLGB AOI and enable the numbered grid.
3. At close zoom, inspect `map_number` labels.
4. Search `clgb_grid_2km_numbered` by `map_number` or `cell_id`.
5. Use `clgb_grid_2km_number_lookup.csv` for coordinates and nearest settlement lookup.

Candidate labels are frozen as review categories only:

- `structure_gravity_review_candidate`
- `structure_only_candidate`
- `insufficient_data`
- legal/restriction masks

No target memos or gold targets are created by this map.

Settlement source: {settlement_source}
"""
    (command_dir / "COMMAND_MAP_README.md").write_text(readme, encoding="utf-8")


def main() -> int:
    cfg = load_config()
    outputs = get_path(cfg, "outputs", create=True)
    data_root = outputs.parent
    command_dir = ensure_dir(outputs / "qgis_command_map")

    styles = write_qml_files(command_dir)

    grid_path = outputs / "clgb_grid_2km.gpkg"
    if not grid_path.exists():
        raise FileNotFoundError(f"2 km CLGB grid missing: {grid_path}")
    grid = gpd.read_file(grid_path).to_crs(PROJECT_CRS)
    numbered = assign_map_numbers(grid)
    context = load_candidate_context(outputs)
    numbered = numbered.merge(context, on="cell_id", how="left")
    numbered["cluster_id"] = numbered.get("cluster_id", pd.Series([""] * len(numbered))).fillna("")
    numbered["legal_status"] = numbered.get("legal_status", pd.Series(["unknown"] * len(numbered))).fillna("unknown")
    numbered["restriction_status"] = numbered.get("restriction_status", pd.Series(["unknown"] * len(numbered))).fillna("unknown")
    numbered["candidate_status"] = numbered.get("candidate_status", pd.Series(["insufficient_data"] * len(numbered))).fillna("insufficient_data")

    clgb = read_optional_vector(data_root / "processed" / "clgb_aoi.gpkg")
    if clgb is None:
        clgb = gpd.GeoDataFrame({"name": ["CLGB AOI"]}, geometry=[box(*numbered.total_bounds)], crs=PROJECT_CRS)
    clgb_geom = clgb.geometry.unary_union
    clgb_box = gpd.GeoDataFrame(
        {"name": ["CLGB AOI bounding box"], "source": ["numbered grid total bounds"]},
        geometry=[box(*numbered.total_bounds)],
        crs=PROJECT_CRS,
    )

    settlements, major_cities, settlement_source, fallback_used = build_settlements(
        command_dir, outputs, data_root, clgb_geom
    )
    if not fallback_used:
        settlement_needed = command_dir / "SETTLEMENT_DATA_NEEDED.md"
        if settlement_needed.exists():
            settlement_needed.unlink()
    numbered = assign_nearest_settlements(numbered, settlements)

    lookup_cols = [
        "map_number",
        "cell_id",
        "centroid_x",
        "centroid_y",
        "centroid_lat",
        "centroid_lon",
        "row_index",
        "col_index",
        "cluster_id",
        "legal_status",
        "restriction_status",
        "candidate_status",
        "nearest_settlement",
        "nearest_settlement_type",
        "distance_to_nearest_settlement_km",
    ]

    review, multilayer, structure_only, review_points = make_review_layers(numbered)

    gravity_path = data_root / "processed" / "gravity_features_2km.parquet"
    if gravity_path.exists():
        gravity = pd.read_parquet(gravity_path)
        gravity_grid = numbered.merge(gravity, on="cell_id", how="left")
        gravity_grid = gravity_grid[gravity_grid["gravity_gradient"].notna()].copy()
    else:
        gravity_grid = gpd.GeoDataFrame(columns=numbered.columns, geometry=[], crs=PROJECT_CRS)

    finland = read_optional_vector(data_root / "raw" / "finland_boundary.geojson")
    if finland is None:
        raise FileNotFoundError("Finland boundary missing: data/raw/finland_boundary.geojson")
    finland = finland.to_crs(PROJECT_CRS)

    buffer_geom = clgb_geom.buffer(15_000)
    bedrock = clip_to(read_optional_vector(data_root / "raw" / "gtk" / "bedrock.gpkg"), buffer_geom, "bedrock")
    structures = clip_to(read_optional_vector(data_root / "raw" / "gtk" / "structures.gpkg"), buffer_geom, "structures")
    restriction_masks = clip_to(read_optional_vector(data_root / "processed" / "restriction_masks.gpkg"), buffer_geom, "restriction_masks")
    tukes = clip_to(read_optional_vector(data_root / "processed" / "tukes_rights_classified.gpkg"), buffer_geom, "tukes_rights")
    protected = clip_to(read_optional_vector(data_root / "raw" / "restrictions" / "protected_areas" / "protected_areas.gpkg"), buffer_geom, "protected_areas")
    natura = clip_to(read_optional_vector(data_root / "raw" / "restrictions" / "natura2000" / "natura2000.gpkg"), buffer_geom, "natura2000")
    groundwater = clip_to(read_optional_vector(data_root / "raw" / "restrictions" / "water_bodies" / "groundwater.gpkg"), buffer_geom, "groundwater")
    open_cells = read_optional_vector(outputs / "open_cells_after_restrictions.gpkg")
    if open_cells is None:
        open_cells = numbered[(numbered["legal_status"] == "open") & (numbered["restriction_status"] == "clear")].copy()

    grid_gpkg = command_dir / "clgb_grid_2km_numbered.gpkg"
    context_gpkg = command_dir / "command_map_layers.gpkg"
    for path in [grid_gpkg, context_gpkg]:
        if path.exists():
            path.unlink()

    write_layer(numbered, grid_gpkg, "clgb_grid_2km_numbered")
    numbered[lookup_cols].to_csv(command_dir / "clgb_grid_2km_number_lookup.csv", index=False)

    write_layer(finland, context_gpkg, "finland_outline")
    write_layer(major_cities, context_gpkg, "major_cities")
    write_layer(clgb_box, context_gpkg, "clgb_aoi_box")
    write_layer(clgb, context_gpkg, "current_project_aoi")
    write_layer(clgb, context_gpkg, "clgb_aoi")
    if bedrock is not None:
        write_layer(bedrock, context_gpkg, "bedrock_geology_clip")
    if structures is not None:
        write_layer(structures, context_gpkg, "structures_faults_clip")
    if not gravity_grid.empty:
        write_layer(gravity_grid, context_gpkg, "gravity_gradient_cells")
    if tukes is not None:
        write_layer(tukes[tukes["legal_class"] == "active"], context_gpkg, "tukes_active_rights")
        write_layer(tukes[tukes["legal_class"] == "pending"], context_gpkg, "tukes_pending_rights")
        write_layer(tukes[tukes["legal_class"] == "cooling_off"], context_gpkg, "tukes_cooling_off")
    if natura is not None:
        write_layer(natura, context_gpkg, "natura2000")
    if protected is not None:
        write_layer(protected, context_gpkg, "protected_areas")
    if groundwater is not None:
        write_layer(groundwater, context_gpkg, "groundwater")
    write_layer(open_cells, context_gpkg, "open_cells_after_restrictions")
    write_layer(review, context_gpkg, "review_candidates_all")
    write_layer(multilayer, context_gpkg, "review_candidates_multilayer")
    write_layer(structure_only, context_gpkg, "review_candidates_structure_only")
    write_layer(review_points, context_gpkg, "review_candidate_points")
    write_layer(settlements, context_gpkg, "settlements")

    for layer, style_key in [
        ("clgb_grid_2km_numbered", "clgb_grid_2km_numbered"),
    ]:
        store_gpkg_style(grid_gpkg, layer, styles[style_key])
    for layer in [
        "finland_outline", "major_cities", "clgb_aoi_box", "current_project_aoi", "clgb_aoi",
        "bedrock_geology_clip", "structures_faults_clip", "gravity_gradient_cells",
        "tukes_active_rights", "tukes_pending_rights", "tukes_cooling_off",
        "natura2000", "protected_areas", "groundwater", "open_cells_after_restrictions",
        "review_candidates_all", "review_candidates_multilayer", "review_candidates_structure_only",
        "review_candidate_points", "settlements",
    ]:
        if layer in styles:
            store_gpkg_style(context_gpkg, layer, styles[layer])
    store_gpkg_style(context_gpkg, "major_cities", styles["finland_major_cities"])

    layer_specs = [
        {"key": "finland_outline", "id": "finland_outline_3067", "name": "Finland outline", "source": "command_map_layers.gpkg|layername=finland_outline", "geometry": "Polygon"},
        {"key": "major_cities", "style_key": "finland_major_cities", "id": "major_cities_3067", "name": "major cities", "source": "command_map_layers.gpkg|layername=major_cities", "geometry": "Point"},
        {"key": "clgb_aoi_box", "id": "clgb_aoi_box_3067", "name": "CLGB AOI rectangle", "source": "command_map_layers.gpkg|layername=clgb_aoi_box", "geometry": "Polygon"},
        {"key": "current_project_aoi", "id": "current_project_aoi_3067", "name": "current project AOI", "source": "command_map_layers.gpkg|layername=current_project_aoi", "geometry": "Polygon"},
        {"key": "clgb_aoi", "id": "clgb_aoi_3067", "name": "CLGB AOI polygon", "source": "command_map_layers.gpkg|layername=clgb_aoi", "geometry": "Polygon"},
        {"key": "bedrock_geology_clip", "id": "bedrock_geology_clip_3067", "name": "bedrock / geology", "source": "command_map_layers.gpkg|layername=bedrock_geology_clip", "geometry": "Polygon"},
        {"key": "structures_faults_clip", "id": "structures_faults_clip_3067", "name": "structures / faults", "source": "command_map_layers.gpkg|layername=structures_faults_clip", "geometry": "Line"},
        {"key": "gravity_gradient_cells", "id": "gravity_gradient_cells_3067", "name": "gravity gradient", "source": "command_map_layers.gpkg|layername=gravity_gradient_cells", "geometry": "Polygon"},
        {"key": "tukes_active_rights", "id": "tukes_active_rights_3067", "name": "Tukes active rights", "source": "command_map_layers.gpkg|layername=tukes_active_rights", "geometry": "Polygon"},
        {"key": "tukes_pending_rights", "id": "tukes_pending_rights_3067", "name": "Tukes pending rights", "source": "command_map_layers.gpkg|layername=tukes_pending_rights", "geometry": "Polygon"},
        {"key": "tukes_cooling_off", "id": "tukes_cooling_off_3067", "name": "Tukes cooling-off / karenssi", "source": "command_map_layers.gpkg|layername=tukes_cooling_off", "geometry": "Polygon"},
        {"key": "natura2000", "id": "natura2000_3067", "name": "Natura 2000", "source": "command_map_layers.gpkg|layername=natura2000", "geometry": "Polygon"},
        {"key": "protected_areas", "id": "protected_areas_3067", "name": "protected areas", "source": "command_map_layers.gpkg|layername=protected_areas", "geometry": "Polygon"},
        {"key": "groundwater", "id": "groundwater_3067", "name": "groundwater", "source": "command_map_layers.gpkg|layername=groundwater", "geometry": "Polygon"},
        {"key": "open_cells_after_restrictions", "id": "open_cells_after_restrictions_3067", "name": "open cells after restrictions", "source": "command_map_layers.gpkg|layername=open_cells_after_restrictions", "geometry": "Polygon", "checked": False},
        {"key": "clgb_grid_2km_numbered", "id": "clgb_grid_2km_numbered_3067", "name": "2 km grid numbered", "source": "clgb_grid_2km_numbered.gpkg|layername=clgb_grid_2km_numbered", "geometry": "Polygon"},
        {"key": "review_candidates_multilayer", "id": "review_candidates_multilayer_3067", "name": "16 multi-layer review candidates", "source": "command_map_layers.gpkg|layername=review_candidates_multilayer", "geometry": "Polygon"},
        {"key": "review_candidates_structure_only", "id": "review_candidates_structure_only_3067", "name": "47 structure-only candidates", "source": "command_map_layers.gpkg|layername=review_candidates_structure_only", "geometry": "Polygon"},
        {"key": "review_candidate_points", "id": "review_candidate_points_3067", "name": "63 review candidate symbols", "source": "command_map_layers.gpkg|layername=review_candidate_points", "geometry": "Point"},
        {"key": "settlements", "id": "settlements_3067", "name": "settlements / towns / villages", "source": "command_map_layers.gpkg|layername=settlements", "geometry": "Point"},
    ]
    write_qgis_project(command_dir, layer_specs, styles)

    make_finland_pdf(command_dir, finland, clgb_box, major_cities)
    make_clgb_pdf(command_dir, numbered, clgb, settlements, structures, review_points)
    build_reports(command_dir, numbered, settlements, settlement_source, fallback_used, multilayer, structure_only)

    summary = {
        "status": "PASS" if not fallback_used else "PARTIAL",
        "total_2km_cells": int(len(numbered)),
        "numbered_cells": int(numbered["map_number"].notna().sum()),
        "settlements_labelled": int(len(settlements)),
        "settlement_source": settlement_source,
        "fallback_used": bool(fallback_used),
        "review_candidates": int(len(review)),
        "multi_layer_candidates": int(len(multilayer)),
        "structure_only_candidates": int(len(structure_only)),
        "multi_layer_map_numbers": [int(x) for x in multilayer.sort_values("map_number")["map_number"].tolist()],
        "first_map_number": {
            "map_number": int(numbered.sort_values("map_number").iloc[0]["map_number"]),
            "cell_id": numbered.sort_values("map_number").iloc[0]["cell_id"],
        },
        "last_map_number": {
            "map_number": int(numbered.sort_values("map_number").iloc[-1]["map_number"]),
            "cell_id": numbered.sort_values("map_number").iloc[-1]["cell_id"],
        },
    }
    (command_dir / "command_map_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    log.info("Wrote zoomable command map to %s", command_dir)
    log.info("Cells=%d settlements=%d review=%d multi-layer=%d",
             len(numbered), len(settlements), len(review), len(multilayer))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
