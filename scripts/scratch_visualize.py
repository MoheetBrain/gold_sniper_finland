import numpy as np
import matplotlib.pyplot as plt
import rioxarray as rxr
from pathlib import Path
import sys

def visualize():
    output_dir = Path("data/outputs/terramind_embeddings")
    cell_id = "g2k_01385"
    
    # Paths
    sar_path = output_dir / cell_id / f"S1RTC_{cell_id}.tif"
    dem_path = output_dir / cell_id / f"DEM_{cell_id}.tif"
    embed_path = output_dir / f"embeddings_{cell_id}.npz"
    
    fig, axes = plt.subplots(2, 2, figsize=(12, 12))
    axes = axes.flatten()
    
    # 1. SAR Image (VV channel)
    try:
        sar = rxr.open_rasterio(sar_path)
        # S1 has VV and VH. We plot VV (band 1)
        axes[0].imshow(sar[0].values, cmap='gray')
        axes[0].set_title(f"SAR (VV) - {cell_id}")
        axes[0].axis('off')
    except Exception as e:
        axes[0].text(0.5, 0.5, f"SAR missing\n{e}", ha='center')
        
    # 2. DEM Image
    try:
        dem = rxr.open_rasterio(dem_path)
        axes[1].imshow(dem[0].values, cmap='terrain')
        axes[1].set_title(f"Copernicus DEM - {cell_id}")
        axes[1].axis('off')
    except Exception as e:
        axes[1].text(0.5, 0.5, f"DEM missing\n{e}", ha='center')
        
    # 3. Embeddings
    try:
        data = np.load(embed_path)
        sar_tokens = data['S1RTC_tokens'][0]
        dem_tokens = data['DEM_tokens'][0]
        
        im3 = axes[2].imshow(sar_tokens, cmap='viridis')
        axes[2].set_title(f"SAR Embeddings (14x14 tokens)")
        axes[2].axis('off')
        plt.colorbar(im3, ax=axes[2], fraction=0.046, pad=0.04)
        
        im4 = axes[3].imshow(dem_tokens, cmap='plasma')
        axes[3].set_title(f"DEM Embeddings (14x14 tokens)")
        axes[3].axis('off')
        plt.colorbar(im4, ax=axes[3], fraction=0.046, pad=0.04)
        
    except Exception as e:
        axes[2].text(0.5, 0.5, f"Embeddings missing\n{e}", ha='center')
        axes[3].axis('off')
        
    plt.tight_layout()
    out_png = f"/Users/mk/.gemini/antigravity-ide/brain/ec574090-7998-4c8e-9eed-55e6cd8bf0e5/terramind_{cell_id}_vis.png"
    plt.savefig(out_png, dpi=150, bbox_inches='tight')
    print(f"Saved visualization to {out_png}")

if __name__ == "__main__":
    visualize()
