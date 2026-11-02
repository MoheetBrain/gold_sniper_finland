# Historical aggregate evidence

These three experiment artifacts are copied byte-for-byte from the private source snapshot: `STEP2_VALIDATION.json`, `STEP2_2B_FEATURE_ABLATION.csv`, and `STEP2_MODEL_FEATURE_IMPORTANCE.json`. They contain aggregate methods/results, not target locations. Historic “PASS” and “enough_data” fields are original project heuristics and must be read alongside [the release limitations](../../RESULTS_AND_LIMITATIONS.md).

`source_register.csv` is a selected-column transcription of the 63-row acquisition register. Local paths, geographic bounds and diagnostic text are excluded. Its `license` and `status` fields are **historical assertions, not release clearance or current availability**. The reviewed licence decision is in [DATA_SOURCES_AND_LICENSES.md](../../DATA_SOURCES_AND_LICENSES.md).

There are no original feature/label/fold/prediction tables here, so the reported historical AUC cannot be recomputed from these files. The provenance hashes are recorded in the release manifest.
