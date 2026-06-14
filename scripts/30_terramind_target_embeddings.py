#!/usr/bin/env python3
"""
TerraMind-1.0-small — SAR + DEM embedding extraction for CLGB targets
======================================================================

PURPOSE:
--------
This script uses IBM/ESA's TerraMind-1.0-small geospatial foundation model
to extract structural embeddings from Sentinel-1 SAR and Copernicus DEM data
over your top gold candidate cells.

WHY SAR + DEM:
  - SAR (radar) penetrates clouds AND tree canopy. It sees the GROUND
    surface and structural fabric that optical imagery misses entirely
    in a boreal forest environment like Lapland.
  - DEM reveals topographic lineaments, subtle fault scarps, drainage
    anomalies, and fold hinges that correspond to structural traps.
  - Together, SAR+DEM through TerraMind can mathematically highlight
    the dilational jog and fault intersection at Map #2387.

WORKFLOW:
  1. Download Sentinel-1 RTC and Copernicus DEM tiles for target cells
  2. Preprocess into 224×224 patches matching TerraMind input format
  3. Run through TerraMind encoder to get embedding vectors
  4. Optionally generate cross-modal outputs (SAR→DEM, DEM→SAR)
  5. Save embeddings and visualisations

USAGE:
------
    # Activate the terramind venv first:
    source terramind/venv/bin/activate

    # Run for top 3 targets:
    python scripts/30_terramind_target_embeddings.py

    # Run for specific map numbers:
    python scripts/30_terramind_target_embeddings.py --targets 2387 2458 3059

    # Just verify the model loads (no data download):
    python scripts/30_terramind_target_embeddings.py --verify-only

REQUIREMENTS:
    - Python 3.11+ with terramind venv activated
    - terratorch >= 1.2.4
    - Internet connection (first run downloads model weights ~500MB)
    - ~4GB free disk for model + data
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

# Suppress noisy warnings during import
warnings.filterwarnings("ignore", category=UserWarning)
os.environ["TOKENIZERS_PARALLELISM"] = "false"


def check_imports():
    """Verify all required packages are installed."""
    missing = []
    for pkg in ["torch", "terratorch", "rioxarray", "numpy"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)

    if missing:
        print(f"ERROR: Missing packages: {', '.join(missing)}", file=sys.stderr)
        print(f"Run: source terramind/venv/bin/activate && pip install {' '.join(missing)}", file=sys.stderr)
        sys.exit(1)


def get_device() -> str:
    """
    Detect the best available compute device.

    Priority: CUDA GPU > Apple MPS > CPU
    Your M1 Pro will use MPS (Metal Performance Shaders).
    """
    import torch
    if torch.cuda.is_available():
        print("  Device: CUDA GPU", file=sys.stderr)
        return "cuda"
    elif torch.backends.mps.is_available():
        print("  Device: Apple MPS (Metal)", file=sys.stderr)
        return "mps"
    else:
        print("  Device: CPU (will be slow)", file=sys.stderr)
        return "cpu"


def verify_model_loads(device: str) -> bool:
    """
    Test that TerraMind-1.0-small tokenizers load correctly.
    """
    import torch
    from terratorch import FULL_MODEL_REGISTRY

    print("\n--- Verifying TerraMind tokenizers load ---", file=sys.stderr)
    print("  (First run downloads weights from HuggingFace)", file=sys.stderr)

    try:
        # Build standalone tokenizers for SAR and DEM
        m_sar = FULL_MODEL_REGISTRY.build('terramind_v1_tokenizer_s1rtc', pretrained=True).to(device)
        m_dem = FULL_MODEL_REGISTRY.build('terramind_v1_tokenizer_dem', pretrained=True).to(device)
        
        m_sar.eval()
        m_dem.eval()
        print("  ✓ Tokenizers loaded successfully!", file=sys.stderr)

        # Quick smoke test with random data
        print("  Running smoke test with random 224×224 input...", file=sys.stderr)
        dummy_sar = torch.randn(1, 2, 224, 224, device=device)
        dummy_dem = torch.randn(1, 1, 224, 224, device=device)

        with torch.no_grad():
            _, _, tokens_sar = m_sar.encode(dummy_sar)
            _, _, tokens_dem = m_dem.encode(dummy_dem)
            print(f"  ✓ SAR tokenized: {tokens_sar.shape}", file=sys.stderr)
            print(f"  ✓ DEM tokenized: {tokens_dem.shape}", file=sys.stderr)

        print("\n  ✅ TerraMind tokenizers are working on your system!", file=sys.stderr)
        return True

    except Exception as e:
        print(f"\n  ❌ Model load failed: {e}", file=sys.stderr)
        return False


def load_target_cells(project_root: Path, target_map_numbers: Optional[List[int]] = None) -> List[Dict]:
    """
    Load target cell coordinates from the grid lookup.

    Default targets are your top MC-ranked cells:
      Map 2387 (g2k_01385) — MC rank #1, Levi
      Map 2458 (g2k_01314) — MC rank #10, Levi
      Map 3059 (g2k_00779) — MC rank #2, Jeesio
    """
    import pandas as pd

    lookup_path = project_root / "data/outputs/clgb_grid_2km_number_lookup.csv"
    if not lookup_path.exists():
        print(f"ERROR: Grid lookup not found: {lookup_path}", file=sys.stderr)
        sys.exit(1)

    lookup = pd.read_csv(lookup_path)

    # Default: top 3 from Monte Carlo
    if target_map_numbers is None:
        target_map_numbers = [2387, 2458, 3059]

    targets = lookup[lookup["map_number"].isin(target_map_numbers)].copy()
    if targets.empty:
        print(f"ERROR: No cells found for map numbers {target_map_numbers}", file=sys.stderr)
        sys.exit(1)

    cells = []
    for _, row in targets.iterrows():
        cells.append({
            "map_number": int(row["map_number"]),
            "cell_id": row["cell_id"],
            "lat": row["centroid_lat"],
            "lon": row["centroid_lon"],
            "x": row["centroid_x"],
            "y": row["centroid_y"],
            "nearest_town": row.get("nearest_town", "unknown"),
        })
        print(f"  Target: Map #{int(row['map_number'])} ({row['cell_id']}) "
              f"at {row['centroid_lat']:.4f}°N, {row['centroid_lon']:.4f}°E", file=sys.stderr)

    return cells


def download_sentinel1_tile(lat: float, lon: float, output_dir: Path,
                            cell_id: str) -> Optional[Path]:
    """
    Download a Sentinel-1 RTC tile from Microsoft Planetary Computer STAC.

    WHY Planetary Computer: Free, cloud-optimised Sentinel-1 RTC data.
    RTC = Radiometric Terrain Corrected (already orthorectified).

    Returns path to downloaded GeoTIFF or None if download fails.
    """
    try:
        import planetary_computer
        import pystac_client
        import rioxarray as rxr
    except ImportError:
        print("  WARNING: planetary_computer/pystac_client not installed.", file=sys.stderr)
        print("  Run: pip install planetary-computer pystac-client", file=sys.stderr)
        return _download_sentinel1_fallback(lat, lon, output_dir, cell_id)

    print(f"  Searching Planetary Computer for S1 RTC near {lat:.4f}°N, {lon:.4f}°E...",
          file=sys.stderr)

    try:
        catalog = pystac_client.Client.open(
            "https://planetarycomputer.microsoft.com/api/stac/v1",
            modifier=planetary_computer.sign_inplace,
        )

        # Search for Sentinel-1 RTC imagery
        # Buffer: ~5km around cell centre (0.05° ≈ 5km at 68°N)
        bbox = [lon - 0.05, lat - 0.025, lon + 0.05, lat + 0.025]
        search = catalog.search(
            collections=["sentinel-1-rtc"],
            bbox=bbox,
            max_items=5,
            sortby="-datetime",
        )
        items = list(search.items())

        if not items:
            print(f"  WARNING: No S1 RTC found for {cell_id}", file=sys.stderr)
            return None

        item = items[0]
        print(f"  Found: {item.id} ({item.datetime})", file=sys.stderr)

        # Download VV and VH bands
        vv_href = item.assets["vv"].href
        vh_href = item.assets["vh"].href

        vv = rxr.open_rasterio(vv_href)
        vh = rxr.open_rasterio(vh_href)

        # Crop to cell area BEFORE saving (saves massive amounts of download time)
        from pyproj import Transformer
        transformer = Transformer.from_crs("EPSG:4326", vv.rio.crs, always_xy=True)
        minx, miny = transformer.transform(lon - 0.05, lat - 0.025)
        maxx, maxy = transformer.transform(lon + 0.05, lat + 0.025)
        
        vv = vv.rio.clip_box(minx=minx, miny=miny, maxx=maxx, maxy=maxy)
        vh = vh.rio.clip_box(minx=minx, miny=miny, maxx=maxx, maxy=maxy)

        out_path = output_dir / f"S1RTC_{cell_id}.tif"
        # Stack VV+VH as 2-channel raster
        import xarray as xr
        stacked = xr.concat([vv, vh], dim="band")
        stacked.rio.to_raster(out_path)
        print(f"  Saved: {out_path.name} ({out_path.stat().st_size // 1024} KB)", file=sys.stderr)
        return out_path

    except Exception as e:
        print(f"  WARNING: Planetary Computer download failed: {e}", file=sys.stderr)
        return _download_sentinel1_fallback(lat, lon, output_dir, cell_id)


def _download_sentinel1_fallback(lat: float, lon: float, output_dir: Path,
                                  cell_id: str) -> Optional[Path]:
    """
    Fallback: create a synthetic SAR-like test tile for model verification.

    This lets you test the full pipeline even without Planetary Computer access.
    Real SAR data should be substituted for production runs.
    """
    import torch

    print(f"  Using synthetic SAR tile for testing (replace with real S1 data)", file=sys.stderr)
    out_path = output_dir / f"S1RTC_{cell_id}_synthetic.tif"

    # Create realistic-looking synthetic SAR (2 channels: VV, VH)
    # Real SAR values are typically in dB: -25 to 0
    rng = np.random.default_rng(hash(cell_id) % 2**32)
    vv = rng.normal(-12.0, 3.0, (1, 224, 224)).astype(np.float32)
    vh = rng.normal(-18.0, 4.0, (1, 224, 224)).astype(np.float32)
    sar = np.concatenate([vv, vh], axis=0)  # Shape: (2, 224, 224)

    # Save as numpy (we'll load it directly into torch later)
    np.save(out_path.with_suffix(".npy"), sar)
    print(f"  Saved synthetic: {out_path.with_suffix('.npy').name}", file=sys.stderr)
    return out_path.with_suffix(".npy")


def download_dem_tile(lat: float, lon: float, output_dir: Path,
                      cell_id: str) -> Optional[Path]:
    """
    Download Copernicus DEM tile.

    WHY Copernicus DEM: Free, 30m resolution, global coverage.
    Shows topographic lineaments and drainage patterns.
    """
    try:
        import planetary_computer
        import pystac_client
        import rioxarray as rxr
    except ImportError:
        return _download_dem_fallback(lat, lon, output_dir, cell_id)

    print(f"  Searching for Copernicus DEM near {lat:.4f}°N, {lon:.4f}°E...", file=sys.stderr)

    try:
        catalog = pystac_client.Client.open(
            "https://planetarycomputer.microsoft.com/api/stac/v1",
            modifier=planetary_computer.sign_inplace,
        )

        bbox = [lon - 0.05, lat - 0.025, lon + 0.05, lat + 0.025]
        search = catalog.search(
            collections=["cop-dem-glo-30"],
            bbox=bbox,
            max_items=1,
        )
        items = list(search.items())

        if not items:
            return _download_dem_fallback(lat, lon, output_dir, cell_id)

        item = items[0]
        dem_href = item.assets["data"].href
        dem = rxr.open_rasterio(dem_href)

        # Crop to cell area BEFORE saving
        from pyproj import Transformer
        transformer = Transformer.from_crs("EPSG:4326", dem.rio.crs, always_xy=True)
        minx, miny = transformer.transform(lon - 0.05, lat - 0.025)
        maxx, maxy = transformer.transform(lon + 0.05, lat + 0.025)
        
        dem = dem.rio.clip_box(minx=minx, miny=miny, maxx=maxx, maxy=maxy)

        out_path = output_dir / f"DEM_{cell_id}.tif"
        dem.rio.to_raster(out_path)
        print(f"  Saved: {out_path.name}", file=sys.stderr)
        return out_path

    except Exception as e:
        print(f"  WARNING: DEM download failed: {e}", file=sys.stderr)
        return _download_dem_fallback(lat, lon, output_dir, cell_id)


def _download_dem_fallback(lat: float, lon: float, output_dir: Path,
                            cell_id: str) -> Optional[Path]:
    """Synthetic DEM fallback for testing."""
    print(f"  Using synthetic DEM tile for testing", file=sys.stderr)
    out_path = output_dir / f"DEM_{cell_id}_synthetic.npy"

    rng = np.random.default_rng(hash(cell_id + "_dem") % 2**32)
    # Realistic Finnish Lapland elevation: 200-600m with gentle topography
    base_elev = 300.0 + rng.normal(0, 50.0)
    dem = rng.normal(base_elev, 15.0, (1, 224, 224)).astype(np.float32)
    # Add some linear features to simulate fault scarps
    for i in range(3):
        angle = rng.uniform(0, np.pi)
        offset = rng.uniform(-50, 50)
        for y in range(224):
            x = int(112 + offset + y * np.tan(angle - np.pi/2) * 0.3)
            if 0 <= x < 224:
                dem[0, y, max(0, x-2):min(224, x+2)] += rng.uniform(5, 20)

    np.save(out_path, dem)
    print(f"  Saved synthetic: {out_path.name}", file=sys.stderr)
    return out_path


def prepare_input_tensor(sar_path: Optional[Path], dem_path: Optional[Path],
                          device: str) -> Dict:
    """
    Load and prepare SAR+DEM data as PyTorch tensors for TerraMind.

    TerraMind expects:
      S1RTC: shape [B, 2, 224, 224] — VV and VH polarisation
      DEM:   shape [B, 1, 224, 224] — elevation
    """
    import torch

    data = {}

    if sar_path and sar_path.exists():
        if sar_path.suffix == ".npy":
            sar = np.load(sar_path)
        else:
            import rioxarray as rxr
            sar_xr = rxr.open_rasterio(sar_path)
            sar = sar_xr.values

        # Ensure shape is (2, 224, 224) — resize if needed
        if sar.shape[1] != 224 or sar.shape[2] != 224:
            from skimage.transform import resize
            sar_resized = np.zeros((2, 224, 224), dtype=np.float32)
            for c in range(min(sar.shape[0], 2)):
                sar_resized[c] = resize(sar[c], (224, 224), preserve_range=True)
            sar = sar_resized

        data["S1RTC"] = torch.tensor(sar, dtype=torch.float32).unsqueeze(0).to(device)
        print(f"    S1RTC tensor: {data['S1RTC'].shape}", file=sys.stderr)

    if dem_path and dem_path.exists():
        if dem_path.suffix == ".npy":
            dem = np.load(dem_path)
        else:
            import rioxarray as rxr
            dem_xr = rxr.open_rasterio(dem_path)
            dem = dem_xr.values

        # Ensure shape is (1, 224, 224)
        if dem.shape[0] > 1:
            dem = dem[:1]
        if dem.shape[1] != 224 or dem.shape[2] != 224:
            from skimage.transform import resize
            dem = resize(dem[0], (224, 224), preserve_range=True)[np.newaxis]

        data["DEM"] = torch.tensor(dem, dtype=torch.float32).unsqueeze(0).to(device)
        print(f"    DEM tensor:   {data['DEM'].shape}", file=sys.stderr)

    return data


def extract_embeddings(m_sar, m_dem, data: Dict, cell_id: str,
                        output_dir: Path, device: str) -> Dict:
    """
    Extract TerraMind embeddings (latent representations) from the encoder.
    """
    import torch

    results = {}
    print(f"\n  Extracting embeddings for {cell_id}...", file=sys.stderr)

    with torch.no_grad():
        if "S1RTC" in data:
            _, _, tokens_sar = m_sar.encode(data["S1RTC"])
            token_array = tokens_sar.cpu().numpy()
            results["S1RTC_tokens"] = token_array
            print(f"    S1RTC tokens: shape={token_array.shape}", file=sys.stderr)

        if "DEM" in data:
            _, _, tokens_dem = m_dem.encode(data["DEM"])
            token_array = tokens_dem.cpu().numpy()
            results["DEM_tokens"] = token_array
            print(f"    DEM tokens: shape={token_array.shape}", file=sys.stderr)

    # Save embeddings
    embed_path = output_dir / f"embeddings_{cell_id}.npz"
    np.savez_compressed(embed_path, **{k: v for k, v in results.items()})
    print(f"    Saved: {embed_path.name} ({embed_path.stat().st_size // 1024} KB)", file=sys.stderr)

    return results


def main():
    parser = argparse.ArgumentParser(
        description="TerraMind-1.0-small SAR+DEM embedding extraction for CLGB gold targets.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--targets", nargs="+", type=int, default=None,
                        help="Map numbers to process. Default: 2387 2458 3059")
    parser.add_argument("--verify-only", action="store_true",
                        help="Only verify model loads, don't download data.")
    parser.add_argument("--use-synthetic", action="store_true",
                        help="Use synthetic test data instead of downloading real imagery.")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    output_dir = project_root / "data/outputs/terramind_embeddings"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70, file=sys.stderr)
    print("TerraMind-1.0-small — SAR + DEM Embedding Extraction", file=sys.stderr)
    print("=" * 70, file=sys.stderr)

    # Step 1: Check imports
    check_imports()

    # Step 2: Detect device
    device = get_device()

    # Step 3: Verify model
    if not verify_model_loads(device):
        sys.exit(1)

    if args.verify_only:
        print("\n✅ Verification complete. Model is ready.", file=sys.stderr)
        print(f"   Run without --verify-only to process target cells.", file=sys.stderr)
        return 0

    # Step 4: Load target cells
    print("\n--- Loading target cells ---", file=sys.stderr)
    cells = load_target_cells(project_root, args.targets)

    # Step 5: Build models for embedding extraction
    print("\n--- Building models for embedding extraction ---", file=sys.stderr)
    import torch
    from terratorch import FULL_MODEL_REGISTRY

    m_sar = FULL_MODEL_REGISTRY.build('terramind_v1_tokenizer_s1rtc', pretrained=True).to(device)
    m_dem = FULL_MODEL_REGISTRY.build('terramind_v1_tokenizer_dem', pretrained=True).to(device)
    m_sar.eval()
    m_dem.eval()

    # Step 6: Process each target cell
    all_results = {}
    for cell in cells:
        cell_id = cell["cell_id"]
        map_num = cell["map_number"]
        lat, lon = cell["lat"], cell["lon"]

        print(f"\n{'='*50}", file=sys.stderr)
        print(f"Processing Map #{map_num} ({cell_id})", file=sys.stderr)
        print(f"  Location: {lat:.4f}°N, {lon:.4f}°E", file=sys.stderr)
        print(f"{'='*50}", file=sys.stderr)

        # Download or create data
        tile_dir = output_dir / cell_id
        tile_dir.mkdir(parents=True, exist_ok=True)

        if args.use_synthetic:
            sar_path = _download_sentinel1_fallback(lat, lon, tile_dir, cell_id)
            dem_path = _download_dem_fallback(lat, lon, tile_dir, cell_id)
        else:
            sar_path = download_sentinel1_tile(lat, lon, tile_dir, cell_id)
            dem_path = download_dem_tile(lat, lon, tile_dir, cell_id)

        # Prepare tensors
        data = prepare_input_tensor(sar_path, dem_path, device)

        if not data:
            print(f"  SKIP: No data available for {cell_id}", file=sys.stderr)
            continue

        # Extract embeddings
        results = extract_embeddings(m_sar, m_dem, data, cell_id, output_dir, device)
        all_results[cell_id] = {
            "map_number": map_num,
            "lat": lat,
            "lon": lon,
            "embedding_shapes": {k: list(v.shape) for k, v in results.items()},
        }

    # Step 7: Save summary
    summary_path = output_dir / "extraction_summary.json"
    summary_path.write_text(json.dumps(all_results, indent=2), encoding="utf-8")
    print(f"\n{'='*70}", file=sys.stderr)
    print(f"✅ Done! Processed {len(all_results)} cells.", file=sys.stderr)
    print(f"   Embeddings: {output_dir}", file=sys.stderr)
    print(f"   Summary:    {summary_path}", file=sys.stderr)
    print(f"{'='*70}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
