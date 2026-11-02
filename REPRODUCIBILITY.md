# Reproducibility

## Supported demonstration

Tested with Python 3.12 on macOS arm64. Exact Python package versions are in `requirements-lock.txt`. XGBoost needs the system OpenMP runtime: `brew install libomp` on macOS; on Debian/Ubuntu, install `libgomp1` if absent. These system packages are separate from pip. Linux CI runs the same tests and demonstration when enabled on the private branch or a later approved public repository.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-lock.txt
python -m pytest -q
python scripts/demo.py --output runs/demo --iterations 500
python scripts/check_release.py
```

The demo is offline, deterministic under the lock, uses seed 42, and takes seconds to minutes depending on hardware. It produces CSV tables, JSON metrics and explicit fold membership. See [example data dictionary](data/example/README.md). Synthetic labels depend on invented features by construction; demo metrics must never be quoted as Finnish field performance.

To regenerate the distributed example and figures intentionally:

```bash
python scripts/demo.py --output data/example --iterations 500
python scripts/make_figures.py
python scripts/build_manifest.py
python scripts/check_release.py
```

The figures are static PNG and SVG for GitHub Markdown. The region map uses included public-domain Natural Earth outlines; other spatial panels are explicitly synthetic. Historical performance figures read the preserved aggregate reports. No map tiles or network requests are made.

## What is, and is not, reproduced

- **Executed:** original geometry/status tests, expanded regressions; grid/feature/overlay demonstration; fold-local XGBoost; baselines and predeclared ablations; synthetic Monte Carlo; figure rendering; release checks.
- **Consistency checked:** historical counts and reported AUC/capture agree between committed summary artifacts; their original bytes remain preserved.
- **Not independently reproduced:** 0.798 historical AUC, Finnish candidate ranking, original geophysics/till extraction, v2 experiments, TerraMind inference, any mineral discovery or economic result.

Original evaluation inputs missing from Git include `feature_stack_minimal_2km.parquet`, `cell_labels_2km.parquet`, `cell_role_2km.parquet`, `cell_block_2km.parquet`, `baseline_scores_2km.parquet` and `model_scores_2km.parquet`. Historic environment versions and private/raw spatial files are also incomplete. The 63 candidate rows are a selected subset and cannot reconstruct the 3,649 evaluation rows. They are deliberately not released.

## Real-data acquisition and research entrypoints

Review [each source's terms](DATA_SOURCES_AND_LICENSES.md) before acquisition. Supply files locally under ignored `data/raw/`; do not add them to Git. Record source URL, product/version, download date, licence, checksum, CRS, units, resolution and transformations in a private acquisition log. Do not mistake a cached service image for a numeric raster.

Copy `configs/config.yaml` to an ignored local location if changing inputs, and set `GEOARB_CONFIG` to that path. The default is repository-relative; `.env.example` is a variable-name template only and is not automatically loaded. All paths in the release are portable. Scripts accept original research filenames; failure due to missing inputs is expected until those inputs are acquired.

1. Tukes: inspect the official map-file page and ATOM feed, confirm rights, then use `00_download_tukes_map_files.py`. Acquisition is not part of CI.
2. Geometry/status: scripts 01, 02, 02c and 04b/04c build grids and overlaps. Set source CRS explicitly; missing restriction coverage remains unknown.
3. GTK: script 05 downloads configured service layers. Check layer IDs/CRS/product metadata against the live service; endpoints can change. Populate bedrock/structures and labels before feature/model stages.
4. Gravity/magnetics/till: follow scripts 06c, 06d and 19, acquiring exact numeric products and assay metadata. Missing/display-only magnetics stay missing. Step 19 requires the appropriate till/glacial inputs.
5. Run scripts 06, 07, 08, 09, 10, 11 and 11b in dependency order; script 22 performs exploratory ablations. Output filenames are documented in each module. The corrected model may change metrics; save new results under a new experiment version.

This is a partial research pipeline, not a one-command promise of full historical reproduction. Previous all-in-one launchers with dependencies on private maps/prototypes are not distributed. Live acquisition, all third-party inputs and external GIS applications are outside the offline support boundary.

## Scientific safeguards

The release fails on degenerate training folds and incomplete OOF coverage. Medians/class weights are training-only. Capture uses cell counts and exposes ties. Historical results are not overwritten by tests. Monte Carlo sensitivity does not validate a probability model. Retain negative findings and compare the same evaluation population across methods.
