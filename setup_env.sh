#!/usr/bin/env bash
# GeoArb_Finland — environment bootstrap.
#
# Creates the `geoarb` conda environment and the data folder skeleton so the
# Step 1 pipeline can run. Safe to re-run: it skips the env if it already exists.
#
# Usage:
#   bash setup_env.sh
#   conda activate geoarb
#   python scripts/run_step1_pipeline.py

set -euo pipefail

ENV_NAME="geoarb"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

echo "==> GeoArb_Finland environment setup"

# --- 1. Conda env ---------------------------------------------------------
if ! command -v conda >/dev/null 2>&1; then
  echo "ERROR: conda not found on PATH. Install Miniconda/Anaconda first." >&2
  exit 1
fi

if conda env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
  echo "==> Conda env '$ENV_NAME' already exists — skipping creation."
  echo "    (To rebuild: conda env remove -n $ENV_NAME && bash setup_env.sh)"
else
  echo "==> Creating conda env '$ENV_NAME' from environment.yml ..."
  conda env create -f environment.yml
fi

# --- 2. Data folder skeleton ---------------------------------------------
# These are git-ignored but the pipeline expects them to exist.
echo "==> Ensuring data folder skeleton exists ..."
mkdir -p \
  data/raw/tukes_zip \
  data/raw/tukes_extracted \
  data/raw/debug \
  data/raw/restrictions \
  data/interim \
  data/processed \
  data/outputs \
  docs

echo
echo "==> Done."
echo "    Next:"
echo "      conda activate $ENV_NAME"
echo "      python scripts/run_step1_pipeline.py"
