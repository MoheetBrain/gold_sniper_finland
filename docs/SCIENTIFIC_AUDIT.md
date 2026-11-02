# Scientific audit and correction record

Source snapshot: `c272a4b9ffe56c56243a9fde4610d324513d80c4`, inspected 2 November 2026. All original files and 12 commits remain in the private backup. The release preserves the historical aggregate JSON/CSV bytes; it does not relabel them as new validated results.

| Finding | Evidence | Release treatment |
|---|---|---|
| Global preprocessing before folds | Original script 11 and 22 fitted median and class weight on all labelled rows | Shared `_evaluation.fit_grouped` learns both from training rows only; regression test inspects actual fitting inputs. |
| Empty extra-cell set caused missing-column selection | Original script 11 assigned score/flag only when extra rows existed | Empty result columns now always exist; regression test trains on an all-evaluation fixture. |
| Partial folds could silently disappear | Original code skipped no-positive training folds and evaluation filtered NaNs | Refuse class-degenerate training folds and incomplete OOF coverage; keep denominator explicit. |
| Ambiguous capture ties | Original unstable sorting | Stable ordering plus exact boundary-tie minimum/maximum; no rewrite of historic scores. |
| Claimed area capture was actually cell count | `ceil(n*k/100)` on rows | Correct terminology; clipped cells require a separate area-weighted analysis. |
| Missing CRS was guessed | Bedrock, rights and restriction loaders assigned project CRS without metadata | Fail with an actionable error. |
| All-null MC columns appeared available | Existing columns were default-filled without missing-group flag | Mark all-null columns missing before default fill; partial missingness remains a limitation. |
| Dynamic import failed for dataclasses | Helper did not register imported modules | Register in `sys.modules`, tested through retained MC engine. |
| Potential archive traversal | Unchecked `extractall` on downloaded ZIPs | Validate every member stays inside extraction directory. |
| GNN not present | All 52 original Python files inventoried; no graph learning implementation found | No GNN claim or dependency. |
| TerraMind fusion fabricated output | `31_terramind_xgboost_fusion.py` described its score as simulated, used a hand-set multiplier and cap, and never called XGBoost | Excluded entirely; private original preserved. Not a scientific result. |
| Foundation-model extraction unverified | Script 30 includes token loading/download code but no committed validation outputs | Excluded prototype, no pretrained model weights or satellite chips distributed. |
| v2 gate changed meaning | Script v2_03 used >= at top-1/top-5 and different all-cell inputs | Do not treat its “PASS” as equivalent to Step 2 gate; outputs missing. |
| Monte Carlo probability overstatement | Hand-set prior and likelihood-ratio bounds | Retain mathematical engine, strip unsupported narrative; public demo reports score/rank sensitivity only. |

The scientific audit is a code/provenance review, not an independent geological review. No failed real-data analysis was tuned or rerun to manufacture a favourable metric.
