# Contributing

Start with an issue describing a reproducible software defect or a falsifiable methodological question. Useful contributions include block-size sensitivity, fold-boundary buffering, fold-safe background sampling, tie-aware/area-weighted capture, missing-data diagnostics and more representative labels.

Run `python -m pytest -q` and the synthetic demo before proposing changes. Keep historical aggregate files unchanged; add clearly versioned experiments with input hashes, software versions and seeds. Never improve a reported metric by weakening validation or silently changing the evaluated population.

Do not upload exploration-target coordinates, private reports, credentials or third-party data without clearance. Use synthetic fixtures for regressions. Follow the licensing and publication gates. Disclose AI assistance and verify generated code, references and claims.
