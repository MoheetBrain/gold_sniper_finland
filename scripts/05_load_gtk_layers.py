"""
05 — Load GTK open-data layers (AOI-clipped) + Step 2 data audit.

WHAT IT DOES
    Pulls the GTK layers we need from GTK's public ArcGIS REST server (free, CC BY
    4.0), clipped to the AOI bbox, reprojected to EPSG:3067, into data/raw/. Then
    audits which Step 2 datasets exist vs are missing and writes STEP2_DATA_AUDIT.md.

    It does NOT invent data. Datasets that GTK does not serve as queryable features
    (airborne magnetics, gravity, till geochemistry — these are rasters/other) are
    reported as missing with a download checklist; downstream they become null
    feature columns, never fabricated values.

QUERIES
    Each layer is queried in its own native CRS bbox (so cross-projection filtering
    works) with the server returning EPSG:3067 geometry. Paginated via resultOffset.

OUTPUTS
    data/raw/gtk/*.gpkg                 (deposits, structures, bedrock)
    data/raw/restrictions/*/*.gpkg      (Natura 2000, protected areas, groundwater)
    data/outputs/STEP2_DATA_AUDIT.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import requests
from pyproj import Transformer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import get_logger, get_path, load_config, resolve_path  # noqa: E402

log = get_logger("05_load_gtk")


def aoi_bbox_in(native_wkid: int, aoi_3067: list[float]) -> dict:
    """Transform the AOI 3067 bbox into the layer's native CRS, return an esri envelope."""
    if native_wkid == 3067:
        xmin, ymin, xmax, ymax = aoi_3067
    else:
        t = Transformer.from_crs("EPSG:3067", f"EPSG:{native_wkid}", always_xy=True)
        xs, ys = [], []
        for x, y in [(aoi_3067[0], aoi_3067[1]), (aoi_3067[2], aoi_3067[1]),
                     (aoi_3067[0], aoi_3067[3]), (aoi_3067[2], aoi_3067[3])]:
            X, Y = t.transform(x, y); xs.append(X); ys.append(Y)
        xmin, ymin, xmax, ymax = min(xs), min(ys), max(xs), max(ys)
    return {"xmin": xmin, "ymin": ymin, "xmax": xmax, "ymax": ymax,
            "spatialReference": {"wkid": native_wkid}}


def query_layer(root: str, service: str, layer: int, native_wkid: int,
                aoi_3067: list[float], timeout: int, page_size: int) -> gpd.GeoDataFrame | None:
    """
    Query an ArcGIS REST MapServer layer, AOI-clipped, returning EPSG:3067 features.

    Robust to services that (a) don't support pagination and (b) occasionally return
    a non-JSON error: we fetch without an offset first, retry transient parse errors,
    and only paginate when the first page is exactly page_size AND pagination works.
    """
    import json as _json
    url = f"{root}/{service}/MapServer/{layer}/query"
    env = aoi_bbox_in(native_wkid, aoi_3067)
    base = {
        "where": "1=1",
        "geometry": _json.dumps(env),
        "geometryType": "esriGeometryEnvelope",
        "inSR": str(native_wkid),
        "outSR": "3067",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "returnGeometry": "true",
        "f": "geojson",
    }

    def fetch(extra: dict):
        """Return parsed JSON dict, or None on parse/HTML failure."""
        r = requests.get(url, params={**base, **extra}, timeout=timeout)
        r.raise_for_status()
        try:
            return r.json()
        except ValueError:
            return None

    def ok(gj) -> bool:
        return gj is not None and "error" not in gj and "features" in gj

    # Escalating strategies: some layers reject pagination, 500 on heavy geometry, or
    # only succeed with simplified geometry (maxAllowableOffset) / minimal fields.
    strategies = [
        {"resultRecordCount": page_size},     # normal
        {},                                   # no record-count (pagination-less services)
        {"maxAllowableOffset": 50},           # simplify heavy polygons (fixes 500s)
        {"maxAllowableOffset": 50, "outFields": "OBJECTID"},  # last resort: geometry only
    ]
    gj = None
    for strat in strategies:
        cand = fetch(strat)
        if ok(cand):
            gj = cand
            if "outFields" in strat:
                log.warning("%s/%s: recovered with simplified geometry/minimal fields.",
                            service, layer)
            break
    if gj is None:
        log.error("All query strategies failed for %s/%s.", service, layer)
        return None

    feats = gj.get("features", [])
    # Paginate only if it looks truncated and the service allows it.
    if len(feats) == page_size:
        offset = page_size
        while True:
            nxt = fetch({"resultRecordCount": page_size, "resultOffset": offset})
            if not nxt or "error" in nxt:
                log.warning("%s/%s: pagination unsupported/failed — result may be "
                            "capped at %d features.", service, layer, len(feats))
                break
            chunk = nxt.get("features", [])
            feats.extend(chunk)
            if len(chunk) < page_size:
                break
            offset += page_size
            if offset > 100000:
                break

    if not feats:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:3067")
    return gpd.GeoDataFrame.from_features(feats, crs="EPSG:3067")


def main() -> int:
    cfg = load_config()
    gtk = cfg["gtk"]
    aoi = gtk["query_aoi_3067"]
    timeout = int(gtk.get("request_timeout_s", 60))
    page = int(gtk.get("page_size", 1000))
    raw = get_path(cfg, "raw", create=True)

    results = []
    for spec in gtk["layers"]:
        out_path = (raw / spec["out"])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            gdf = query_layer(gtk["arcgis_root"], spec["service"], spec["layer"],
                             spec["native_wkid"], aoi, timeout, page)
        except Exception as exc:  # noqa: BLE001
            log.error("Failed %s: %s", spec["name"], exc)
            results.append({**spec, "n": None, "error": str(exc)})
            continue
        n = 0 if gdf is None else len(gdf)
        if gdf is not None and n > 0:
            # Clean geometry, keep CRS.
            gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]
            inv = ~gdf.geometry.is_valid
            if inv.any():
                gdf.loc[inv, gdf.geometry.name] = gdf.loc[inv, gdf.geometry.name].make_valid()
            gdf.to_file(out_path, driver="GPKG")
            log.info("%-22s %4d features -> %s", spec["name"], n, out_path.relative_to(raw.parent))
        else:
            log.warning("%-22s 0 features (nothing in AOI or query empty)", spec["name"])
        results.append({**spec, "n": n, "path": str(out_path)})

    # --- Audit report ---
    audit = get_path(cfg, "outputs", create=True) / "STEP2_DATA_AUDIT.md"
    by_kind = {}
    for r in results:
        by_kind.setdefault(r["kind"], []).append(r)

    L = ["# Step 2 Data Audit", "",
         "GTK open data (CC BY 4.0) pulled AOI-clipped from the public ArcGIS REST server.",
         "All saved layers are EPSG:3067.", "",
         "## Pulled layers", "",
         "| dataset | kind | features in AOI | saved to |",
         "|---------|------|-----------------|----------|"]
    for r in results:
        status = "ERROR" if r.get("error") else (r["n"] if r["n"] is not None else "—")
        L.append(f"| {r['name']} | {r['kind']} | {status} | `data/raw/{r['out']}` |")

    # Presence checklist against the user's required Step 2 datasets.
    def present(kind, namekey=None):
        for r in results:
            if r["kind"] == kind and (namekey is None or namekey in r["name"]) and r.get("n"):
                return True
        return False
    checklist = [
        ("bedrock geology", present("bedrock")),
        ("known deposits / FINGOLD (FODD)", present("deposits", "fodd")),
        ("gold mines (MDaE)", present("deposits", "gold_mines")),
        ("faults / shears / structures", present("structures")),
        ("restriction: Natura 2000", present("restriction", "natura")),
        ("restriction: protected/conservation", present("restriction", "protected")),
    ]
    L += ["", "## Required-dataset presence", ""]
    for name, ok in checklist:
        L.append(f"- {'✅' if ok else '❌'} {name}")

    L += ["", "## MISSING (not served as queryable features — NOT invented)", "",
          "These become **null feature columns** in the stack + a download checklist:", ""]
    for m in gtk.get("missing_expected", []):
        L.append(f"- ❌ **{m['feature']}** ← {m['dataset']} — get from: {m['source']}")
    L += ["",
          "### How to add the missing rasters later",
          "1. Download from GTK Hakku (https://hakku.gtk.fi) clipped to the CLGB.",
          "2. Save under `data/raw/gtk/` (e.g. `magnetics_tmi.tif`, `gravity.tif`,",
          "   `till_geochem.gpkg`).",
          "3. Re-run `scripts/06_build_minimal_feature_stack.py` — it will fill the",
          "   currently-null columns automatically.", "",
          "## Limitations (read loudly)",
          "- GTK 1GE bedrock/structure layers are **1:1,000,000-scale** — fine for *major*",
          "  shear distance, too coarse for detailed contacts. Replace with DigiKP 1:200k",
          "  before target-memo stage.",
          "- Magnetics, gravity and till geochemistry are **absent** → 6 of the 10 features",
          "  are null this run. The model cannot show real multi-layer convergence yet.", ""]
    audit.write_text("\n".join(L), encoding="utf-8")
    log.info("Wrote %s", audit)

    ok = [r for r in results if r.get("n")]
    log.info("Done: %d/%d layers returned data.", len(ok), len(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
