"""
Lightweight unit tests for Step 1 building blocks.

These test pure logic (grid construction, cell classification) WITHOUT needing the
pipeline to have run or any network access, so they are safe for CI. For end-to-end
output validation, run scripts/99_sanity_check_outputs.py after the pipeline.

Run:  pytest -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import importlib.util


def _load(module_file: str, name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / module_file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


grid_mod = _load("01_make_aoi_grid.py", "grid_mod")


def test_grid_cell_count_and_crs():
    """A 10km x 10km box at 5km cells -> 4 cells, all in EPSG:3067."""
    g = grid_mod.build_grid([0, 0, 10000, 10000], 5000, "EPSG:3067")
    assert len(g) == 4
    assert str(g.crs).upper().endswith("3067")
    # Each full 5km cell = 25 km^2.
    assert g["area_km2"].sum() == pytest.approx(100.0)
    assert {"cell_id", "area_km2", "centroid_x", "centroid_y"}.issubset(g.columns)


def test_grid_clips_edges():
    """A 7km-wide box at 5km cells clips the last column to 2km width."""
    g = grid_mod.build_grid([0, 0, 7000, 5000], 5000, "EPSG:3067")
    assert len(g) == 2  # one 5km cell + one clipped 2km cell
    # Total area must equal the box area exactly (7km x 5km = 35 km^2).
    assert g["area_km2"].sum() == pytest.approx(35.0)


def test_grid_rejects_bad_bounds():
    with pytest.raises(ValueError):
        grid_mod.build_grid([10, 10, 0, 0], 5000, "EPSG:3067")


def test_classification_thresholds():
    """Open/partly/taken boundaries match the documented thresholds."""
    import importlib
    mask_mod = _load("02_mask_taken_areas.py", "mask_mod")
    cfg = {"legal_status": {"open_max_pct": 1.0, "partly_taken_max_pct": 10.0}}

    import geopandas as gpd
    from shapely.geometry import box

    # One 1km x 1km cell = 1,000,000 m^2.
    grid = gpd.GeoDataFrame(
        {"cell_id": ["c0"], "area_km2": [1.0],
         "centroid_x": [500.0], "centroid_y": [500.0]},
        geometry=[box(0, 0, 1000, 1000)], crs="EPSG:3067",
    )
    # A right covering 5% of the cell -> partly_taken.
    right = gpd.GeoDataFrame(
        {"source_layer": ["x"]},
        geometry=[box(0, 0, 1000, 50)], crs="EPSG:3067",  # 1000 x 50 = 50,000 m^2 = 5%
    )
    out = mask_mod.compute_cell_status(grid, right, cfg)
    assert out.loc[0, "taken_overlap_pct"] == pytest.approx(5.0, abs=1e-6)
    assert out.loc[0, "legal_status"] == "partly_taken"
    assert not bool(out.loc[0, "is_clean_open"])


def test_classification_clean_open_when_no_rights():
    mask_mod = _load("02_mask_taken_areas.py", "mask_mod2")
    cfg = {"legal_status": {"open_max_pct": 1.0, "partly_taken_max_pct": 10.0}}
    import geopandas as gpd
    from shapely.geometry import box
    grid = gpd.GeoDataFrame(
        {"cell_id": ["c0"], "area_km2": [1.0],
         "centroid_x": [500.0], "centroid_y": [500.0]},
        geometry=[box(0, 0, 1000, 1000)], crs="EPSG:3067",
    )
    empty = gpd.GeoDataFrame({"source_layer": []}, geometry=[], crs="EPSG:3067")
    out = mask_mod.compute_cell_status(grid, empty, cfg)
    assert out.loc[0, "legal_status"] == "open"
    assert bool(out.loc[0, "is_clean_open"])
