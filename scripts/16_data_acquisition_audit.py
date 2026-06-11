#!/Users/mk/miniconda3/envs/geoarb/bin/python
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import requests
import rasterio
from pyproj import Transformer
from rasterio.warp import transform_bounds
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import PROJECT_CRS, REPO_ROOT, load_config, resolve_path  # noqa: E402


OUT_DIR = resolve_path("data/acquisition_audit")
OUT_DIR.mkdir(parents=True, exist_ok=True)

GTK_ROOT = "https://gtkdata.gtk.fi/arcgis/rest/services"
GTK_HAKKU = "https://hakku.gtk.fi"
TUKES_MAP_FILES = "https://tukes.fi/en/mining-ore-prospecting-and-gold-panning/map-files"
TUKES_FEED = (
    "https://tukes.fi/karttatiedostot-rss-atomfeedina?"
    "p_p_id=fi_yja_feedbuilder_FeedXmlViewPortlet&p_p_lifecycle=2&"
    "p_p_state=normal&p_p_mode=view&p_p_cacheability=cacheLevelPage"
)
NLS_OPEN_DATA = "https://www.maanmittauslaitos.fi/en/e-services/open-data-file-download-service"
SYKE_OPEN_DATA = "https://www.syke.fi/en/open-information/open-data"
DIGIROAD_OPEN_DATA = "https://vayla.fi/en/transport-network/data/digiroad/open-data"
FINGRID_OPEN_DATA = "https://data.fingrid.fi/en/"
STATFI_GEODATA = "https://stat.fi/org/avoindata/paikkatietoaineistot_en.html"

REQUESTED_COLUMNS = [
    "dataset_name",
    "category",
    "why_needed",
    "official_source",
    "source_url",
    "access_method",
    "can_claude_download",
    "license",
    "CRS",
    "expected_format",
    "downloaded_file_path",
    "status",
    "failure_reason",
    "next_action",
]

VALIDATION_COLUMNS = [
    "validation_file_exists",
    "validation_crs",
    "validation_feature_count",
    "validation_raster_dimensions",
    "validation_intersects_aoi",
    "validation_bounds",
    "validation_notes",
]

ALL_COLUMNS = REQUESTED_COLUMNS + VALIDATION_COLUMNS

VECTOR_SUFFIXES = {".gpkg", ".geojson", ".json", ".shp", ".tab", ".mif"}
RASTER_SUFFIXES = {".tif", ".tiff", ".img", ".vrt"}


def arcgis_layer_url(service: str, layer: int | None = None) -> str:
    base_url = f"{GTK_ROOT}/{service}/MapServer"
    return f"{base_url}/{layer}" if layer is not None else base_url


def ds(
    dataset_name: str,
    category: str,
    why_needed: str,
    official_source: str,
    source_url: str,
    access_method: str,
    can_claude_download: str,
    license_text: str,
    source_crs: str,
    expected_format: str,
    paths: list[str] | None = None,
    next_action: str = "",
    failure_reason: str = "",
    auto_download: dict[str, Any] | None = None,
    blocker_rank: int | None = None,
) -> dict[str, Any]:
    return {
        "dataset_name": dataset_name,
        "category": category,
        "why_needed": why_needed,
        "official_source": official_source,
        "source_url": source_url,
        "access_method": access_method,
        "can_claude_download": can_claude_download,
        "license": license_text,
        "CRS": source_crs,
        "expected_format": expected_format,
        "candidate_paths": paths or [],
        "next_action": next_action,
        "failure_reason": failure_reason,
        "auto_download": auto_download,
        "blocker_rank": blocker_rank,
    }


def auto_wfs(
    service: str,
    layer: int,
    output_path: str,
    native_wkid: int = 3067,
) -> dict[str, Any]:
    return {
        "service": service,
        "layer": layer,
        "output_path": output_path,
        "native_wkid": native_wkid,
        "source_url": arcgis_layer_url(service, layer),
    }


DATASETS = [
    # A. Legal/cadastre
    ds("Tukes active exploration permits", "Legal/cadastre", "Exclude active hard-rock rights from open-ground targeting.", "Tukes", TUKES_MAP_FILES, "direct_download", "yes", "Tukes terms and copyright on source page", "EPSG:3067", "GPKG/SHP", ["data/processed/tukes_all_rights.gpkg"], "Refresh from Tukes feed before any investment decision."),
    ds("Tukes exploration applications", "Legal/cadastre", "Exclude or flag pending exploration permit ground.", "Tukes", TUKES_MAP_FILES, "direct_download", "yes", "Tukes terms and copyright on source page", "EPSG:3067", "GPKG/SHP", ["data/processed/tukes_all_rights.gpkg"], "Refresh from Tukes feed before any investment decision."),
    ds("Tukes reservations", "Legal/cadastre", "Avoid already-reserved ground and competitor positions.", "Tukes", TUKES_MAP_FILES, "direct_download", "yes", "Tukes terms and copyright on source page", "EPSG:3067", "GPKG/SHP", ["data/processed/tukes_all_rights.gpkg"], "Refresh from Tukes feed before any investment decision."),
    ds("Tukes reservation applications", "Legal/cadastre", "Flag near-term competitive pressure and pending reservations.", "Tukes", TUKES_MAP_FILES, "direct_download", "yes", "Tukes terms and copyright on source page", "EPSG:3067", "GPKG/SHP", ["data/processed/tukes_all_rights.gpkg"], "Refresh from Tukes feed before any investment decision."),
    ds("Tukes mining permits", "Legal/cadastre", "Exclude existing mining areas and concessions.", "Tukes", TUKES_MAP_FILES, "direct_download", "yes", "Tukes terms and copyright on source page", "EPSG:3067", "GPKG/SHP", ["data/processed/tukes_all_rights.gpkg"], "Refresh from Tukes feed before any investment decision."),
    ds("Tukes gold panning permits", "Legal/cadastre", "Separate placer gold rights from hard-rock exploration decisions.", "Tukes", TUKES_MAP_FILES, "direct_download", "yes", "Tukes terms and copyright on source page", "EPSG:3067", "GPKG/SHP", ["data/processed/tukes_all_rights.gpkg"], "Review whether placer permits are hard exclusions or scenario flags."),
    ds("Tukes Karenssi/cooling-off/lapsed status", "Legal/cadastre", "Identify lapsed or cooling-off ground and avoid legal misclassification.", "Tukes", TUKES_MAP_FILES, "direct_download", "yes", "Tukes terms and copyright on source page", "EPSG:3067", "GPKG/SHP", ["data/processed/tukes_rights_classified.gpkg", "data/processed/tukes_all_rights.gpkg"], "Validate legal interpretation with Tukes before staking."),
    # B. Core geology
    ds("GTK bedrock geology polygons", "Core geology", "Host-rock and geological-domain predictors.", "GTK ArcGIS REST", arcgis_layer_url("GTK_Bedrock_and_Superficial_Geology", 3), "REST", "yes", "GTK open data, CC BY 4.0", "EPSG:3067 target", "GPKG", ["data/raw/gtk/bedrock.gpkg"], "Replace 1:1M layer with DigiKP 1:200k before target ranking."),
    ds("GTK lithology attributes", "Core geology", "Lithology fields used for host-rock encoding.", "GTK ArcGIS REST", arcgis_layer_url("GTK_Bedrock_and_Superficial_Geology", 3), "REST", "yes", "GTK open data, CC BY 4.0", "EPSG:3067 target", "GPKG attributes", ["data/raw/gtk/bedrock.gpkg"], "Inspect lithology fields and harmonize before modelling."),
    ds("GTK stratigraphy/group attributes", "Core geology", "Stratigraphic grouping for greenstone-belt filtering.", "GTK ArcGIS REST", arcgis_layer_url("GTK_Bedrock_and_Superficial_Geology", 3), "REST", "yes", "GTK open data, CC BY 4.0", "EPSG:3067 target", "GPKG attributes", ["data/raw/gtk/bedrock.gpkg"], "Inspect stratigraphic fields and harmonize before modelling."),
    ds("Central Lapland Greenstone Belt boundary or derivable geology", "Core geology", "Define modelling domain and prevent off-belt leakage.", "Derived from GTK bedrock", arcgis_layer_url("GTK_Bedrock_and_Superficial_Geology", 3), "manual", "maybe", "Derived; inherits GTK source license", "EPSG:3067", "GPKG", ["data/processed/clgb_aoi.gpkg"], "Replace approximate or coarse CLGB boundary with authoritative geology-derived polygon.", blocker_rank=4),
    ds("GTK structures/faults/shear zones", "Core geology", "Distance-to-structure and corridor predictors.", "GTK ArcGIS REST", arcgis_layer_url("GTK_Bedrock_and_Superficial_Geology", 0), "REST", "yes", "GTK open data, CC BY 4.0", "EPSG:3067 target", "GPKG", ["data/raw/gtk/structures.gpkg"], "Replace coarse 1:1M structures with higher-resolution structures when available."),
    ds("Dykes if available", "Core geology", "Intrusion and competency-contrast predictors.", "GTK Hakku / GTK bedrock services", GTK_HAKKU, "manual", "maybe", "GTK open data, verify dataset terms", "EPSG:3067 preferred", "Vector", [], "Search GTK Hakku/DigiKP for dyke layers clipped to CLGB."),
    ds("Lithological contacts if available", "Core geology", "Rheological contrasts and contact-distance predictors.", "Derived from GTK bedrock", arcgis_layer_url("GTK_Bedrock_and_Superficial_Geology", 3), "manual", "maybe", "Derived; inherits GTK source license", "EPSG:3067", "Vector", [], "Derive contacts after authoritative bedrock polygons are finalized."),
    # C. Geophysics
    ds("GTK aeromagnetic TMI", "Geophysics", "Magnetic texture, structures, and alteration proxies under cover.", "GTK Geophysics / Hakku", arcgis_layer_url("MDaE/Geophysics", 63), "WMS", "maybe", "GTK open data, verify raster terms", "EPSG:3067 preferred", "GeoTIFF/IMG source grid", ["data/raw/gtk/magnetics_tmi.tif", "data/raw/gtk/magnetic_tmi.tif"], "Obtain source grid from GTK Hakku or WCS; WMS map image is not adequate for modelling.", "Only WMS visualization discovered automatically; source grid not downloaded.", blocker_rank=1),
    ds("Magnetic 1VD or raw TMI suitable for derivative calculation", "Geophysics", "Lineaments and derivative-ready magnetic predictors.", "GTK Geophysics / Hakku", arcgis_layer_url("MDaE/Geophysics", 63), "WMS", "maybe", "GTK open data, verify raster terms", "EPSG:3067 preferred", "GeoTIFF/IMG source grid", ["data/raw/gtk/magnetics_1vd.tif", "data/raw/gtk/magnetics_tmi.tif"], "Obtain source TMI or 1VD grid, not a rendered WMS layer.", "Only WMS visualization discovered automatically; source grid not downloaded.", blocker_rank=1),
    ds("Magnetic analytic signal if available", "Geophysics", "Magnetic-edge and source-location predictor.", "GTK Geophysics / Hakku", GTK_HAKKU, "unknown", "maybe", "GTK open data, verify dataset terms", "EPSG:3067 preferred", "GeoTIFF", ["data/raw/gtk/magnetics_analytic_signal.tif"], "Confirm whether GTK publishes analytic signal; otherwise derive from TMI."),
    ds("Magnetic tilt derivative if available", "Geophysics", "Structure mapping and magnetic-edge enhancement.", "Derived from magnetic TMI", arcgis_layer_url("MDaE/Geophysics", 63), "manual", "maybe", "Derived; inherits magnetic source license", "EPSG:3067", "GeoTIFF", ["data/raw/gtk/magnetics_tilt.tif"], "Derive locally after source TMI grid is acquired."),
    ds("Bouguer gravity", "Geophysics", "Deep structure and density-contrast predictor.", "GTK Geophysics / Hakku", arcgis_layer_url("MDaE/Geophysics", 58), "WMS", "maybe", "GTK open data, verify raster terms", "EPSG:3067 preferred", "GeoTIFF/IMG source grid", ["data/raw/gtk/bouguer_gravity.tif", "data/raw/gtk/gravity_bouguer.tif"], "Obtain source Bouguer grid; WMS map image is not adequate for modelling.", "Only WMS visualization discovered automatically; source grid not downloaded.", blocker_rank=2),
    ds("Gravity gradient / upward continuation if available", "Geophysics", "Deep-edge and regional-structure derivatives.", "Derived from Bouguer gravity", arcgis_layer_url("MDaE/Geophysics", 58), "manual", "maybe", "Derived; inherits gravity source license", "EPSG:3067", "GeoTIFF", ["data/raw/gtk/gravity_gradient.tif", "data/raw/gtk/gravity_upward_continuation.tif"], "Derive locally after Bouguer source grid is acquired.", blocker_rank=2),
    ds("Radiometric K, Th, U if available", "Geophysics", "Alteration and lithology proxies from radiometric channels.", "GTK Geophysics / Hakku", arcgis_layer_url("MDaE/Geophysics", 72), "WMS", "maybe", "GTK open data, verify raster terms", "EPSG:3067 preferred", "GeoTIFF/IMG source grids", ["data/raw/gtk/radiometric_k.tif", "data/raw/gtk/radiometric_th.tif", "data/raw/gtk/radiometric_u.tif"], "Obtain source K/Th/U grids; WMS rendered layers are not adequate."),
    ds("EM/electromagnetic data if publicly available", "Geophysics", "Conductivity and structure proxy where public airborne EM exists.", "GTK Geophysics / Hakku", arcgis_layer_url("MDaE/Geophysics", 66), "WMS", "maybe", "GTK open data, verify raster terms", "EPSG:3067 preferred", "GeoTIFF/IMG source grids", ["data/raw/gtk/em_apparent_resistivity.tif", "data/raw/gtk/em_in_phase.tif", "data/raw/gtk/em_quadrature.tif"], "Obtain source EM grids if available; WMS rendered layers are not adequate."),
    # D. Geochemistry
    ds("GTK till geochemistry Au", "Geochemistry", "Direct gold anomaly predictor in transported cover.", "GTK Maapera WFS", arcgis_layer_url("Rajapinnat/GTK_Maapera_WFS", 11), "REST", "yes", "GTK open data, CC BY 4.0", "EPSG:3067", "GPKG point layer", ["data/raw/gtk/till_geochemistry_almr_519u.gpkg"], "Use AU_PPM_519U and qualifier fields; account for transport direction.", auto_download=auto_wfs("Rajapinnat/GTK_Maapera_WFS", 11, "data/raw/gtk/till_geochemistry_almr_519u.gpkg")),
    ds("GTK till As", "Geochemistry", "Orogenic-gold pathfinder anomaly predictor.", "GTK Maapera WFS", arcgis_layer_url("Rajapinnat/GTK_Maapera_WFS", 52), "REST", "yes", "GTK open data, CC BY 4.0", "EPSG:3067", "GPKG point layer", ["data/raw/gtk/till_geochemistry_supraregional.gpkg"], "Use AS fields where coverage supports modelling; verify scale and detection limits.", auto_download=auto_wfs("Rajapinnat/GTK_Maapera_WFS", 52, "data/raw/gtk/till_geochemistry_supraregional.gpkg")),
    ds("GTK till Sb", "Geochemistry", "Orogenic-gold pathfinder anomaly predictor.", "GTK Maapera WFS", arcgis_layer_url("Rajapinnat/GTK_Maapera_WFS", 52), "REST", "yes", "GTK open data, CC BY 4.0", "EPSG:3067", "GPKG point layer", ["data/raw/gtk/till_geochemistry_supraregional.gpkg"], "Use SB fields where coverage supports modelling; verify scale and detection limits.", auto_download=auto_wfs("Rajapinnat/GTK_Maapera_WFS", 52, "data/raw/gtk/till_geochemistry_supraregional.gpkg")),
    ds("GTK till Bi", "Geochemistry", "Gold-system pathfinder if till Bi exists in public analytical package.", "GTK Hakku / Maapera WFS", GTK_HAKKU, "unknown", "maybe", "GTK open data, verify dataset terms", "EPSG:3067 preferred", "CSV/Vector", [], "No Bi field was found in discovered regional till layers; confirm in Hakku or with GTK and do not substitute stream-sediment Bi.", "Not found in automatically discovered till WFS layers.", blocker_rank=3),
    ds("GTK till Te", "Geochemistry", "Gold-system pathfinder and Au association check.", "GTK Maapera WFS", arcgis_layer_url("Rajapinnat/GTK_Maapera_WFS", 11), "REST", "yes", "GTK open data, CC BY 4.0", "EPSG:3067", "GPKG point layer", ["data/raw/gtk/till_geochemistry_almr_519u.gpkg"], "Use TE_PPM_519U and qualifier fields; account for censoring.", auto_download=auto_wfs("Rajapinnat/GTK_Maapera_WFS", 11, "data/raw/gtk/till_geochemistry_almr_519u.gpkg")),
    ds("GTK till W", "Geochemistry", "Pathfinder and granitoid/skarn discrimination check.", "GTK Maapera WFS", arcgis_layer_url("Rajapinnat/GTK_Maapera_WFS", 52), "REST", "yes", "GTK open data, CC BY 4.0", "EPSG:3067", "GPKG point layer", ["data/raw/gtk/till_geochemistry_supraregional.gpkg"], "Use W fields where coverage supports modelling; verify scale.", auto_download=auto_wfs("Rajapinnat/GTK_Maapera_WFS", 52, "data/raw/gtk/till_geochemistry_supraregional.gpkg")),
    ds("GTK till Cu", "Geochemistry", "Base-metal association and lithologic discrimination.", "GTK Maapera WFS", arcgis_layer_url("Rajapinnat/GTK_Maapera_WFS", 10), "REST", "yes", "GTK open data, CC BY 4.0", "EPSG:3067", "GPKG point layer", ["data/raw/gtk/till_geochemistry_almr_511p.gpkg"], "Use CU_PPM_511P and qualifier fields; account for transport direction.", auto_download=auto_wfs("Rajapinnat/GTK_Maapera_WFS", 10, "data/raw/gtk/till_geochemistry_almr_511p.gpkg")),
    ds("GTK till Co", "Geochemistry", "Mafic/ultramafic and base-metal association predictor.", "GTK Maapera WFS", arcgis_layer_url("Rajapinnat/GTK_Maapera_WFS", 10), "REST", "yes", "GTK open data, CC BY 4.0", "EPSG:3067", "GPKG point layer", ["data/raw/gtk/till_geochemistry_almr_511p.gpkg"], "Use CO_PPM_511P and qualifier fields; account for transport direction.", auto_download=auto_wfs("Rajapinnat/GTK_Maapera_WFS", 10, "data/raw/gtk/till_geochemistry_almr_511p.gpkg")),
    ds("GTK till Ni", "Geochemistry", "Mafic/ultramafic and base-metal association predictor.", "GTK Maapera WFS", arcgis_layer_url("Rajapinnat/GTK_Maapera_WFS", 10), "REST", "yes", "GTK open data, CC BY 4.0", "EPSG:3067", "GPKG point layer", ["data/raw/gtk/till_geochemistry_almr_511p.gpkg"], "Use NI_PPM_511P and qualifier fields; account for transport direction.", auto_download=auto_wfs("Rajapinnat/GTK_Maapera_WFS", 10, "data/raw/gtk/till_geochemistry_almr_511p.gpkg")),
    ds("Detection limits / sample fraction / survey metadata", "Geochemistry", "Censoring, normalization, and survey-comparability metadata.", "GTK Maapera WFS / Hakku", arcgis_layer_url("Rajapinnat/GTK_Maapera_WFS", 10), "REST", "yes", "GTK open data, CC BY 4.0", "EPSG:3067 for sample layers", "Fields in GPKG point layers", ["data/raw/gtk/till_geochemistry_almr_511p.gpkg", "data/raw/gtk/till_geochemistry_almr_519u.gpkg", "data/raw/gtk/till_geochemistry_supraregional.gpkg"], "Use FRACTION/LAJITE and *_T qualifier fields; obtain external analytical docs if needed.", auto_download=auto_wfs("Rajapinnat/GTK_Maapera_WFS", 10, "data/raw/gtk/till_geochemistry_almr_511p.gpkg")),
    ds("Stream sediment geochemistry if available", "Geochemistry", "Regional catchment-scale geochemical context.", "GTK Maapera WFS", arcgis_layer_url("Rajapinnat/GTK_Maapera_WFS", 53), "REST", "yes", "GTK open data, CC BY 4.0", "EPSG:3067", "GPKG point layer", ["data/raw/gtk/stream_sediment_geochemistry.gpkg"], "Use as regional context only; do not substitute for till anomalies.", auto_download=auto_wfs("Rajapinnat/GTK_Maapera_WFS", 53, "data/raw/gtk/stream_sediment_geochemistry.gpkg")),
    ds("Bedrock/lithogeochemistry if available", "Geochemistry", "Host-rock chemistry and alteration context.", "GTK Hakku", GTK_HAKKU, "manual", "maybe", "GTK open data, verify dataset terms", "EPSG:3067 preferred", "CSV/Vector", [], "Search Hakku for lithogeochemistry samples clipped to CLGB."),
    # E. Glacial/regolith
    ds("Surficial geology", "Glacial/regolith", "Cover type, transport regime, and sample media context.", "GTK Maapera WFS", arcgis_layer_url("Rajapinnat/GTK_Maapera_WFS", 48), "REST", "yes", "GTK open data, CC BY 4.0", "EPSG:3067", "GPKG polygon layer", ["data/raw/gtk/surficial_geology_50k.gpkg"], "Use 50k coverage now; add 20k layer where available for detailed work.", auto_download=auto_wfs("Rajapinnat/GTK_Maapera_WFS", 48, "data/raw/gtk/surficial_geology_50k.gpkg")),
    ds("Till cover / drift thickness if available", "Glacial/regolith", "Downweight masked or deeply covered areas.", "GTK Maapeitepaksuus / Hakku", arcgis_layer_url("Maapeitepaksuus_1m"), "WMS", "maybe", "GTK open data, verify raster terms", "EPSG:3067 preferred", "GeoTIFF/raster", ["data/raw/gtk/till_cover_thickness.tif", "data/raw/gtk/drift_thickness.tif"], "Obtain source grid, not a rendered WMS layer."),
    ds("Glacial flow indicators", "Glacial/regolith", "Up-ice shift and anomaly-transport correction.", "GTK Maapera WFS", arcgis_layer_url("Rajapinnat/GTK_Maapera_WFS", 31), "REST", "yes", "GTK open data, CC BY 4.0", "EPSG:3067", "GPKG point/line layer", ["data/raw/gtk/glacial_striae.gpkg"], "Use with lineation layers to parameterize till-shift direction.", auto_download=auto_wfs("Rajapinnat/GTK_Maapera_WFS", 31, "data/raw/gtk/glacial_striae.gpkg")),
    ds("Drumlins", "Glacial/regolith", "Ice-flow landform and transport-direction evidence.", "GTK Maapera WFS", arcgis_layer_url("Rajapinnat/GTK_Maapera_WFS", 58), "REST", "yes", "GTK open data, CC BY 4.0", "EPSG:3067", "GPKG line layer", ["data/raw/gtk/glacial_lineations.gpkg"], "Filter DEPOSIT_TYPE fields for drumlins/lineations before modelling.", auto_download=auto_wfs("Rajapinnat/GTK_Maapera_WFS", 58, "data/raw/gtk/glacial_lineations.gpkg")),
    ds("Ribbed moraines", "Glacial/regolith", "Ice dynamics and transport-complexity evidence.", "GTK Maapera WFS", arcgis_layer_url("Rajapinnat/GTK_Maapera_WFS", 60), "REST", "yes", "GTK open data, CC BY 4.0", "EPSG:3067", "GPKG polygon layer", ["data/raw/gtk/glaciofluvial_moraine_formations.gpkg"], "Filter DEPOSIT_TYPE fields for ribbed moraine or related moraine classes.", auto_download=auto_wfs("Rajapinnat/GTK_Maapera_WFS", 60, "data/raw/gtk/glaciofluvial_moraine_formations.gpkg")),
    ds("Eskers", "Glacial/regolith", "Glaciofluvial transport and permeability context.", "GTK Maapera WFS", arcgis_layer_url("Rajapinnat/GTK_Maapera_WFS", 60), "REST", "yes", "GTK open data, CC BY 4.0", "EPSG:3067", "GPKG polygon layer", ["data/raw/gtk/glaciofluvial_moraine_formations.gpkg"], "Filter DEPOSIT_TYPE fields for esker/glaciofluvial classes.", auto_download=auto_wfs("Rajapinnat/GTK_Maapera_WFS", 60, "data/raw/gtk/glaciofluvial_moraine_formations.gpkg")),
    ds("Peat/bog/wetland polygons", "Glacial/regolith", "Mask organic cover and geochemical attenuation areas.", "SYKE / NLS Finland", SYKE_OPEN_DATA, "manual", "maybe", "Open data license; verify product-specific terms", "EPSG:3067 preferred", "Vector", [], "Download wetland/peat/bog polygons from SYKE or NLS and clip to CLGB.", blocker_rank=5),
    ds("DEM/elevation", "Glacial/regolith", "Topographic context, drainage, and derivative terrain variables.", "NLS Finland", NLS_OPEN_DATA, "manual", "maybe", "NLS open data license; verify product-specific terms", "EPSG:3067 preferred", "GeoTIFF/DEM", ["data/raw/mml/dem.tif", "data/raw/gtk/dem.tif"], "Download DEM tiles covering the CLGB and mosaic/clip.", blocker_rank=4),
    ds("Slope", "Glacial/regolith", "Terrain derivative for geomorphology and accessibility.", "Derived from DEM", NLS_OPEN_DATA, "manual", "maybe", "Derived; inherits DEM source license", "EPSG:3067", "GeoTIFF", ["data/processed/slope.tif", "data/raw/mml/slope.tif"], "Derive from DEM after source elevation is acquired.", blocker_rank=4),
    ds("Water bodies", "Glacial/regolith", "Hard mask, access planning, and geochemical-context layer.", "NLS Finland / SYKE", NLS_OPEN_DATA, "manual", "maybe", "Open data license; verify product-specific terms", "EPSG:3067 preferred", "Vector", ["data/raw/restrictions/water_bodies/water_bodies.gpkg"], "Download lakes/rivers from NLS Topographic Database or SYKE; groundwater is not a water-body substitute.", blocker_rank=5),
    # F. Deposits/training labels
    ds("GTK/FODD mineral deposit database", "Deposits/training labels", "Positive-label source and deposit metadata.", "GTK FODD", arcgis_layer_url("Fodd/fodd_FDM_v5", 39), "REST", "yes", "GTK open data, CC BY 4.0", "EPSG:3067 target", "GPKG point layer", ["data/raw/gtk/fodd_precious_metals.gpkg"], "Keep only label classes appropriate for CLGB orogenic-gold modelling."),
    ds("Gold occurrences", "Deposits/training labels", "Gold occurrence labels and validation points.", "GTK FODD", arcgis_layer_url("Fodd/fodd_FDM_v5", 39), "REST", "yes", "GTK open data, CC BY 4.0", "EPSG:3067 target", "GPKG point layer", ["data/raw/gtk/fodd_precious_metals.gpkg"], "Filter commodities/genetic type and audit false positives."),
    ds("Orogenic gold labels", "Deposits/training labels", "Deposit-model-specific positive labels.", "Derived from GTK FODD", arcgis_layer_url("Fodd/fodd_FDM_v5", 39), "manual", "maybe", "Derived; inherits GTK source license", "EPSG:3067", "GPKG point layer", ["data/processed/clgb_positive_labels.gpkg"], "Review label rules and exclude non-orogenic systems."),
    ds("Known mines", "Deposits/training labels", "Mines, operating deposits, and high-confidence labels.", "GTK Mines and deposits", arcgis_layer_url("MDaE/Mines_deposits", 5), "REST", "yes", "GTK open data, CC BY 4.0", "EPSG:3067 target", "GPKG point layer", ["data/raw/gtk/gold_mines.gpkg"], "Validate mine status and commodity fields."),
    ds("Historical prospects", "Deposits/training labels", "Prospect and occurrence labels beyond active mines.", "GTK FODD / Hakku", arcgis_layer_url("Fodd/fodd_FDM_v5", 39), "REST", "maybe", "GTK open data, CC BY 4.0", "EPSG:3067 target", "GPKG/PDF", ["data/raw/gtk/fodd_precious_metals.gpkg"], "FODD occurrences exist; manually review Hakku reports for historical prospect detail.", blocker_rank=5),
    ds("Drillholes if available", "Deposits/training labels", "Subsurface validation and negative/positive label QA.", "GTK Hakku", GTK_HAKKU, "manual", "maybe", "GTK open data, verify dataset terms", "EPSG:3067 preferred", "CSV/Vector", [], "Download drillhole collars/intervals if public for CLGB prospects.", blocker_rank=5),
    ds("Historical exploration reports if downloadable", "Deposits/training labels", "Ground-truth context, assays, and target rationale.", "GTK Hakku", GTK_HAKKU, "manual", "maybe", "GTK open data, verify report terms", "N/A", "PDF", [], "Manually retrieve and index Hakku exploration reports for label QA.", blocker_rank=5),
    # G. Restrictions/social/environment
    ds("Natura 2000", "Restrictions/social/environment", "Hard environmental exclusion or high-friction mask.", "SYKE via GTK NatureETC", arcgis_layer_url("MDaE/NatureETC", 1), "REST", "yes", "Open data license; verify product-specific terms", "EPSG:3067 target", "GPKG polygon layer", ["data/raw/restrictions/natura2000/natura2000.gpkg"], "Refresh from SYKE/EEA before final land-access decisions."),
    ds("Protected areas", "Restrictions/social/environment", "Hard or high-friction environmental exclusion mask.", "SYKE via GTK NatureETC", arcgis_layer_url("MDaE/NatureETC", 2), "REST", "yes", "Open data license; verify product-specific terms", "EPSG:3067 target", "GPKG polygon layer", ["data/raw/restrictions/protected_areas/protected_areas.gpkg"], "Refresh from SYKE before final land-access decisions."),
    ds("Wilderness areas", "Restrictions/social/environment", "Hard/high-friction land-use restriction in northern Finland.", "Metsahallitus / SYKE", SYKE_OPEN_DATA, "manual", "maybe", "Open data license; verify product-specific terms", "EPSG:3067 preferred", "Vector", ["data/raw/restrictions/wilderness_areas/wilderness_areas.gpkg"], "Download wilderness-area polygons and clip to CLGB."),
    ds("Groundwater areas", "Restrictions/social/environment", "Environmental restriction and permitting-friction layer.", "SYKE via GTK NatureETC", arcgis_layer_url("MDaE/NatureETC", 0), "REST", "yes", "Open data license; verify product-specific terms", "EPSG:3067 target", "GPKG polygon layer", ["data/raw/restrictions/water_bodies/groundwater.gpkg"], "Keep separate from surface water-body masks."),
    ds("Water bodies", "Restrictions/social/environment", "Hard mask for lakes/rivers and field-access planning.", "NLS Finland / SYKE", NLS_OPEN_DATA, "manual", "maybe", "Open data license; verify product-specific terms", "EPSG:3067 preferred", "Vector", ["data/raw/restrictions/water_bodies/water_bodies.gpkg"], "Download surface water polygons; groundwater layer does not satisfy this dataset.", blocker_rank=5),
    # H. Commercial/infrastructure
    ds("Roads", "Commercial/infrastructure", "Access cost and distance-to-road predictors.", "Digiroad / NLS Finland", DIGIROAD_OPEN_DATA, "manual", "maybe", "Open data license; verify product-specific terms", "EPSG:3067 preferred", "Vector", ["data/raw/infrastructure/roads.gpkg"], "Download Digiroad roads and derive distance raster.", blocker_rank=5),
    ds("Railways", "Commercial/infrastructure", "Logistics context and distance-to-rail predictor.", "NLS Finland / Finnish Transport Infrastructure Agency", NLS_OPEN_DATA, "manual", "maybe", "Open data license; verify product-specific terms", "EPSG:3067 preferred", "Vector", ["data/raw/infrastructure/railways.gpkg"], "Download railway vectors and derive distance raster."),
    ds("Power lines if available", "Commercial/infrastructure", "Power-access and development-cost context.", "Fingrid / NLS Finland", FINGRID_OPEN_DATA, "manual", "maybe", "Open data license; verify product-specific terms", "EPSG:3067 preferred", "Vector", ["data/raw/infrastructure/power_lines.gpkg"], "Download transmission/distribution line data if public."),
    ds("Towns", "Commercial/infrastructure", "Community/access context and distance-to-settlement predictors.", "Statistics Finland / NLS Finland", STATFI_GEODATA, "manual", "maybe", "Open data license; verify product-specific terms", "EPSG:3067 preferred", "Vector", ["data/raw/infrastructure/towns.gpkg"], "Download settlement/town layer and derive distances."),
    ds("Kittila mine/mill location", "Commercial/infrastructure", "Anchor mine/mill context and development-distance feature.", "GTK Mines and deposits", arcgis_layer_url("MDaE/Mines_deposits", 5), "REST", "yes", "GTK open data, CC BY 4.0", "EPSG:3067 target", "GPKG point layer", ["data/raw/gtk/gold_mines.gpkg"], "Confirm mill coordinates from operator source if needed for engineering work."),
    ds("Active company claims nearby", "Commercial/infrastructure", "Competitor pressure and land-availability context.", "Tukes", TUKES_MAP_FILES, "direct_download", "yes", "Tukes terms and copyright on source page", "EPSG:3067", "GPKG polygon layer", ["data/processed/tukes_rights_classified.gpkg", "data/processed/tukes_all_rights.gpkg"], "Filter active/pending company-held claims and derive distance/overlap features."),
    ds("Distance-to-infrastructure layers", "Commercial/infrastructure", "Logistics score and development-friction predictors.", "Derived from roads/rail/power/towns", DIGIROAD_OPEN_DATA, "manual", "maybe", "Derived; inherits infrastructure source licenses", "EPSG:3067", "GeoTIFF/parquet", ["data/processed/distance_to_roads.tif", "data/processed/distance_to_infrastructure.parquet"], "Derive after roads, rail, power, and towns are acquired.", blocker_rank=5),
]


def rel_path(path: Path | str | None) -> str:
    if not path:
        return ""
    resolved_path = resolve_path(path)
    try:
        return str(resolved_path.relative_to(REPO_ROOT))
    except ValueError:
        return str(resolved_path)


def first_existing_path(paths: list[str]) -> Path | None:
    for candidate in paths:
        resolved_candidate = resolve_path(candidate)
        if resolved_candidate.exists():
            return resolved_candidate
    return None


def safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def safe_json_get(
    url: str,
    params: dict[str, Any] | None = None,
    timeout: int = 60,
) -> tuple[dict[str, Any] | None, str]:
    try:
        response = requests.get(url, params=params, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        return None, f"HTTP request failed: {exc}"
    try:
        payload = response.json()
    except ValueError as exc:
        return None, f"JSON parse failed: {exc}"
    if payload is None:
        return None, "JSON response was null"
    if not isinstance(payload, dict):
        return None, f"Unexpected JSON payload type: {type(payload).__name__}"
    if isinstance(payload.get("error"), dict):
        message = payload["error"].get("message") or payload["error"]
        return None, f"ArcGIS error: {message}"
    return payload, ""


def load_aoi() -> tuple[Any, tuple[float, float, float, float], str]:
    config = load_config()
    clgb_path = resolve_path("data/processed/clgb_aoi.gpkg")
    if clgb_path.exists():
        aoi_gdf = gpd.read_file(clgb_path)
        if aoi_gdf.crs and aoi_gdf.crs.to_string() != PROJECT_CRS:
            aoi_gdf = aoi_gdf.to_crs(PROJECT_CRS)
        aoi_geometry = aoi_gdf.geometry.union_all()
        return aoi_geometry, tuple(float(value) for value in aoi_geometry.bounds), rel_path(clgb_path)
    bounds = (
        config.get("gtk", {}).get("query_aoi_3067")
        or config.get("aoi", {}).get("bounds")
        or [350000, 7450000, 530000, 7620000]
    )
    aoi_geometry = box(*bounds)
    return aoi_geometry, tuple(float(value) for value in bounds), "configs/config.yaml:aoi.bounds"


def envelope_for_wkid(
    bounds_3067: tuple[float, float, float, float],
    native_wkid: int,
) -> dict[str, Any]:
    if native_wkid == 3067:
        xmin, ymin, xmax, ymax = bounds_3067
    else:
        transformer = Transformer.from_crs(PROJECT_CRS, f"EPSG:{native_wkid}", always_xy=True)
        transformed_points = [
            transformer.transform(x_coord, y_coord)
            for x_coord, y_coord in [
                (bounds_3067[0], bounds_3067[1]),
                (bounds_3067[2], bounds_3067[1]),
                (bounds_3067[0], bounds_3067[3]),
                (bounds_3067[2], bounds_3067[3]),
            ]
        ]
        x_values = [point[0] for point in transformed_points]
        y_values = [point[1] for point in transformed_points]
        xmin, ymin, xmax, ymax = min(x_values), min(y_values), max(x_values), max(y_values)
    return {
        "xmin": xmin,
        "ymin": ymin,
        "xmax": xmax,
        "ymax": ymax,
        "spatialReference": {"wkid": native_wkid},
    }


def wkid_from_metadata(metadata: dict[str, Any], fallback_wkid: int) -> int:
    spatial_refs = [
        (metadata.get("extent") or {}).get("spatialReference"),
        metadata.get("sourceSpatialReference"),
    ]
    for spatial_ref in spatial_refs:
        if isinstance(spatial_ref, dict):
            wkid = spatial_ref.get("latestWkid") or spatial_ref.get("wkid")
            if isinstance(wkid, int):
                return wkid
    return fallback_wkid


def download_arcgis_feature_layer(
    spec: dict[str, Any],
    aoi_bounds_3067: tuple[float, float, float, float],
    timeout: int,
    page_size: int,
) -> tuple[Path | None, str]:
    output_path = resolve_path(spec["output_path"])
    if output_path.exists():
        return output_path, ""

    service = spec["service"]
    layer = int(spec["layer"])
    layer_url = arcgis_layer_url(service, layer)
    metadata, metadata_error = safe_json_get(layer_url, {"f": "pjson"}, timeout)
    if metadata_error:
        return None, metadata_error

    if metadata.get("type") not in {"Feature Layer", None}:
        return None, f"Layer is {metadata.get('type')}, not a downloadable Feature Layer"

    native_wkid = wkid_from_metadata(metadata, int(spec.get("native_wkid") or 3067))
    envelope = envelope_for_wkid(aoi_bounds_3067, native_wkid)
    query_url = f"{layer_url}/query"
    base_params = {
        "where": "1=1",
        "geometry": json.dumps(envelope),
        "geometryType": "esriGeometryEnvelope",
        "inSR": str(native_wkid),
        "outSR": "3067",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "returnGeometry": "true",
        "f": "geojson",
    }

    features: list[dict[str, Any]] = []
    offset = 0
    while True:
        page_params = {
            **base_params,
            "resultRecordCount": page_size,
            "resultOffset": offset,
        }
        payload, query_error = safe_json_get(query_url, page_params, timeout)
        if query_error and offset == 0:
            payload, query_error = safe_json_get(query_url, base_params, timeout)
        if query_error:
            return None, query_error
        page_features = safe_list(payload.get("features") if payload else None)
        if not page_features:
            break
        features.extend(page_features)
        if len(page_features) < page_size:
            break
        offset += page_size
        if offset > 250000:
            return None, f"Pagination guard stopped after {len(features)} features"

    if not features:
        return None, "No features returned inside AOI"

    feature_collection = {"type": "FeatureCollection", "features": features}
    gdf = gpd.GeoDataFrame.from_features(feature_collection, crs=PROJECT_CRS)
    if gdf.empty:
        return None, "GeoJSON parsed to an empty GeoDataFrame"
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
    if gdf.empty:
        return None, "All returned geometries were null or empty"
    invalid_mask = ~gdf.geometry.is_valid
    if invalid_mask.any():
        gdf.loc[invalid_mask, gdf.geometry.name] = gdf.loc[invalid_mask, gdf.geometry.name].make_valid()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(output_path, driver="GPKG")
    return output_path, ""


def discover_gtk_geophysics(timeout: int) -> dict[str, Any]:
    discovery: dict[str, Any] = {
        "catalog_url": f"{GTK_ROOT}/MDaE?f=pjson",
        "selected_service": "",
        "selected_service_url": "",
        "layers": [],
        "errors": [],
    }
    catalog, catalog_error = safe_json_get(f"{GTK_ROOT}/MDaE", {"f": "pjson"}, timeout)
    if catalog_error:
        discovery["errors"].append(catalog_error)
        return discovery

    service_names = [
        service.get("name")
        for service in safe_list(catalog.get("services"))
        if isinstance(service, dict) and service.get("type") == "MapServer"
    ]
    dated_geophysics = sorted(
        name for name in service_names
        if isinstance(name, str) and re.search(r"/\d{8}_Geophysics$", name)
    )
    selected_service = dated_geophysics[-1] if dated_geophysics else "MDaE/Geophysics"
    if selected_service not in service_names and "MDaE/Geophysics" in service_names:
        selected_service = "MDaE/Geophysics"

    selected_url = arcgis_layer_url(selected_service)
    discovery["selected_service"] = selected_service
    discovery["selected_service_url"] = selected_url

    service_payload, service_error = safe_json_get(selected_url, {"f": "pjson"}, timeout)
    if service_error:
        discovery["errors"].append(service_error)
        return discovery

    for layer in safe_list(service_payload.get("layers")):
        if not isinstance(layer, dict):
            continue
        sublayers = safe_list(layer.get("subLayerIds"))
        discovery["layers"].append(
            {
                "id": layer.get("id"),
                "name": layer.get("name"),
                "parentLayerId": layer.get("parentLayerId"),
                "sublayer_count": len(sublayers),
                "subLayerIds": sublayers,
            }
        )
    return discovery


def validate_file(
    path: Path | None,
    aoi_geometry: Any,
    validation_cache: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    empty_result = {column: "" for column in VALIDATION_COLUMNS}
    if path is None:
        return empty_result

    cache_key = str(path)
    if cache_key in validation_cache:
        return validation_cache[cache_key].copy()

    result = empty_result.copy()
    result["validation_file_exists"] = "yes" if path.exists() else "no"
    if not path.exists():
        result["validation_notes"] = "File path configured but file does not exist."
        validation_cache[cache_key] = result.copy()
        return result

    suffix = path.suffix.lower()
    try:
        if suffix in VECTOR_SUFFIXES:
            gdf = gpd.read_file(path)
            result["validation_feature_count"] = int(len(gdf))
            result["validation_crs"] = gdf.crs.to_string() if gdf.crs else ""
            if len(gdf) > 0 and "geometry" in gdf:
                check_gdf = gdf
                if check_gdf.crs and check_gdf.crs.to_string() != PROJECT_CRS:
                    check_gdf = check_gdf.to_crs(PROJECT_CRS)
                spatial_gdf = check_gdf[check_gdf.geometry.notna() & ~check_gdf.geometry.is_empty]
                if len(spatial_gdf) > 0:
                    bounds = spatial_gdf.total_bounds
                    result["validation_bounds"] = ",".join(f"{value:.2f}" for value in bounds)
                    result["validation_intersects_aoi"] = (
                        "yes" if bool(spatial_gdf.intersects(aoi_geometry).any()) else "no"
                    )
                else:
                    result["validation_intersects_aoi"] = "no"
                    result["validation_notes"] = "No non-empty geometries."
        elif suffix in RASTER_SUFFIXES:
            with rasterio.open(path) as raster:
                result["validation_crs"] = raster.crs.to_string() if raster.crs else ""
                result["validation_raster_dimensions"] = f"{raster.width}x{raster.height}"
                raster_bounds = raster.bounds
                bounds_tuple = (raster_bounds.left, raster_bounds.bottom, raster_bounds.right, raster_bounds.top)
                if raster.crs and raster.crs.to_string() != PROJECT_CRS:
                    bounds_tuple = transform_bounds(raster.crs, PROJECT_CRS, *bounds_tuple)
                result["validation_bounds"] = ",".join(f"{value:.2f}" for value in bounds_tuple)
                result["validation_intersects_aoi"] = "yes" if box(*bounds_tuple).intersects(aoi_geometry) else "no"
        else:
            result["validation_notes"] = "File exists; non-spatial format not CRS/AOI validated."
    except Exception as exc:  # noqa: BLE001
        result["validation_notes"] = f"Validation failed: {type(exc).__name__}: {exc}"

    validation_cache[cache_key] = result.copy()
    return result


def status_for_dataset(
    item: dict[str, Any],
    existing_path: Path | None,
    downloaded_paths: set[str],
    download_errors: dict[str, str],
) -> tuple[str, str, str]:
    candidate_paths = item["candidate_paths"]
    downloaded_candidate = next(
        (resolve_path(candidate) for candidate in candidate_paths if str(resolve_path(candidate)) in downloaded_paths),
        None,
    )
    if downloaded_candidate is not None:
        return "downloaded", "", item["next_action"]
    if existing_path is not None:
        return "already_exists", "", item["next_action"]

    auto_download = item.get("auto_download")
    if auto_download:
        output_path = resolve_path(auto_download["output_path"])
        error = download_errors.get(str(output_path))
        if error:
            return "failed", error, item["next_action"] or "Retry official REST download or acquire manually."

    if item["access_method"] in {"manual", "WMS", "WCS", "unknown", "paid"}:
        failure_reason = item["failure_reason"] or "Automatic source-data download is not configured or not available."
        return "manual_required", failure_reason, item["next_action"] or "Acquire manually from official source."

    failure_reason = item["failure_reason"] or "No local file and no successful automatic download."
    return "not_found", failure_reason, item["next_action"] or "Locate official source and rerun audit."


def build_rows(
    aoi_geometry: Any,
    aoi_bounds: tuple[float, float, float, float],
    timeout: int,
    page_size: int,
) -> tuple[list[dict[str, Any]], set[str], dict[str, str]]:
    downloaded_paths: set[str] = set()
    attempted_downloads: set[str] = set()
    download_errors: dict[str, str] = {}

    for item in DATASETS:
        auto_download = item.get("auto_download")
        if not auto_download:
            continue
        output_path = resolve_path(auto_download["output_path"])
        if output_path.exists() or str(output_path) in attempted_downloads:
            continue
        attempted_downloads.add(str(output_path))
        downloaded_path, error = download_arcgis_feature_layer(auto_download, aoi_bounds, timeout, page_size)
        if downloaded_path is not None:
            downloaded_paths.add(str(downloaded_path))
        else:
            download_errors[str(output_path)] = error

    rows: list[dict[str, Any]] = []
    validation_cache: dict[str, dict[str, Any]] = {}
    for item in DATASETS:
        existing_path = first_existing_path(item["candidate_paths"])
        status, failure_reason, next_action = status_for_dataset(
            item, existing_path, downloaded_paths, download_errors
        )
        selected_path = existing_path
        if selected_path is None and item["candidate_paths"]:
            first_candidate = resolve_path(item["candidate_paths"][0])
            if str(first_candidate) in downloaded_paths:
                selected_path = first_candidate

        row = {
            "dataset_name": item["dataset_name"],
            "category": item["category"],
            "why_needed": item["why_needed"],
            "official_source": item["official_source"],
            "source_url": item["source_url"],
            "access_method": item["access_method"],
            "can_claude_download": item["can_claude_download"],
            "license": item["license"],
            "CRS": item["CRS"],
            "expected_format": item["expected_format"],
            "downloaded_file_path": rel_path(selected_path) if selected_path else "",
            "status": status,
            "failure_reason": failure_reason,
            "next_action": next_action,
        }
        row.update(validate_file(selected_path, aoi_geometry, validation_cache))
        rows.append(row)

    return rows, downloaded_paths, download_errors


def write_geophysics_discovery(discovery: dict[str, Any]) -> Path:
    output_path = OUT_DIR / "GTK_GEOPHYSICS_LAYER_DISCOVERY.json"
    output_path.write_text(json.dumps(discovery, indent=2, ensure_ascii=False), encoding="utf-8")
    return output_path


def unique_paths(rows: list[dict[str, Any]], status: str) -> list[str]:
    paths = sorted(
        {
            row["downloaded_file_path"]
            for row in rows
            if row["status"] == status and row.get("downloaded_file_path")
        }
    )
    return paths


def write_report(
    rows: list[dict[str, Any]],
    discovery: dict[str, Any],
    discovery_path: Path,
    aoi_source: str,
) -> None:
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    status_counts = pd.Series([row["status"] for row in rows]).value_counts().to_dict()
    downloaded = unique_paths(rows, "downloaded")
    already_present = unique_paths(rows, "already_exists")
    manual_rows = [
        row for row in rows
        if row["status"] in {"manual_required", "failed", "not_found"}
    ]
    blockers = sorted(
        (
            row for row in rows
            if row["status"] in {"manual_required", "failed", "not_found"}
        ),
        key=lambda row: next(
            (
                item.get("blocker_rank") or 99
                for item in DATASETS
                if item["dataset_name"] == row["dataset_name"]
            ),
            99,
        ),
    )[:5]

    lines = [
        "# GEOARB Finland Data Acquisition Audit",
        "",
        f"Generated: {generated_at}",
        f"AOI source: `{aoi_source}`",
        "",
        "This audit finds official public sources, downloads selected queryable GTK WFS/REST source layers, and validates local files. It does not run ML and does not create probability surfaces.",
        "",
        "## Register Summary",
        "",
        f"- Total dataset rows: {len(rows)}",
        f"- Status counts: {json.dumps(status_counts, sort_keys=True)}",
        f"- GTK geophysics discovery: `{rel_path(discovery_path)}`",
        f"- Selected GTK geophysics service: `{discovery.get('selected_service') or 'not discovered'}`",
    ]
    if discovery.get("errors"):
        lines.append(f"- GTK geophysics discovery errors: {'; '.join(discovery['errors'])}")
    else:
        layer_count = len(discovery.get("layers") or [])
        lines.append(f"- GTK geophysics layers parsed safely: {layer_count}")
    lines.extend(
        [
            "",
            "## Validation Checks",
            "",
            "- File existence checked for every configured local path.",
            "- Vector CRS, feature count, bounds, and AOI intersection checked with GeoPandas.",
            "- Raster CRS, dimensions, bounds, and AOI intersection checked with Rasterio when raster files exist.",
            "- Missing WMS-only geophysical render layers remain manual because rendered map images are not source grids for modelling.",
            "",
            "## Data Codex downloaded",
        ]
    )
    if downloaded:
        lines.extend(f"- `{path}`" for path in downloaded)
    else:
        lines.append("- None in this run.")

    lines.extend(["", "## Data already present"])
    if already_present:
        lines.extend(f"- `{path}`" for path in already_present)
    else:
        lines.append("- None.")

    lines.extend(["", "## Data user must manually obtain"])
    if manual_rows:
        for row in manual_rows:
            lines.append(
                f"- **{row['dataset_name']}** ({row['category']}): {row['failure_reason']} "
                f"Next: {row['next_action']} Source: {row['source_url']}"
            )
    else:
        lines.append("- None.")

    lines.extend(["", "## Top 5 missing blockers before probability modelling"])
    if blockers:
        for index, row in enumerate(blockers, start=1):
            lines.append(f"{index}. {row['dataset_name']} - {row['next_action']}")
    else:
        lines.append("1. None identified by this audit.")

    lines.extend(
        [
            "",
            "## Can we build a probability surface now?",
            "",
            "**No.** The audit now has several official GTK till/regolith source layers and the existing legal/geology/label layers, but source geophysical grids, DEM/slope, surface-water/wetland masks, and drillhole/report QA are still missing or manual. A probability-first prospectivity surface would still be underconstrained and would risk presenting availability/geology proxies as mineral probability.",
            "",
        ]
    )
    (OUT_DIR / "DATA_ACQUISITION_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def write_missing_manual(rows: list[dict[str, Any]]) -> None:
    lines = [
        "# Manual Data Acquisition Checklist",
        "",
        "Only rows with status `manual_required`, `failed`, or `not_found` are listed here.",
        "",
    ]
    current_category = ""
    for row in rows:
        if row["status"] not in {"manual_required", "failed", "not_found"}:
            continue
        if row["category"] != current_category:
            current_category = row["category"]
            lines.extend(["", f"## {current_category}", ""])
        lines.append(f"- [ ] **{row['dataset_name']}**")
        lines.append(f"  - Status: `{row['status']}`")
        lines.append(f"  - Source: {row['source_url']}")
        lines.append(f"  - Reason: {row['failure_reason']}")
        lines.append(f"  - Next action: {row['next_action']}")
    (OUT_DIR / "MISSING_MANUAL_DATA.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    config = load_config()
    timeout = int(config.get("gtk", {}).get("request_timeout_s", 60))
    page_size = int(config.get("gtk", {}).get("page_size", 1000))
    aoi_geometry, aoi_bounds, aoi_source = load_aoi()

    discovery = discover_gtk_geophysics(timeout)
    discovery_path = write_geophysics_discovery(discovery)

    rows, downloaded_paths, download_errors = build_rows(
        aoi_geometry,
        aoi_bounds,
        timeout,
        page_size,
    )
    register = pd.DataFrame(rows)
    register = register.reindex(columns=ALL_COLUMNS)
    register.to_csv(OUT_DIR / "DATA_SOURCE_REGISTER.csv", index=False)
    write_report(rows, discovery, discovery_path, aoi_source)
    write_missing_manual(rows)

    print(f"Audit completed: {rel_path(OUT_DIR / 'DATA_SOURCE_REGISTER.csv')}")
    print(f"Report written: {rel_path(OUT_DIR / 'DATA_ACQUISITION_REPORT.md')}")
    print(f"Manual checklist written: {rel_path(OUT_DIR / 'MISSING_MANUAL_DATA.md')}")
    print(f"GTK geophysics discovery written: {rel_path(discovery_path)}")
    if downloaded_paths:
        print("Downloaded source layers:")
        for downloaded_path in sorted(downloaded_paths):
            print(f"  {rel_path(downloaded_path)}")
    if download_errors:
        print("Download errors:")
        for output_path, error in sorted(download_errors.items()):
            print(f"  {rel_path(output_path)}: {error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
