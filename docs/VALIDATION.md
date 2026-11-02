# Validation record

Release-candidate validation on 2 November 2026, Python 3.12 on macOS arm64 with `requirements-lock.txt` and OpenMP runtime installed. The original snapshot is `c272a4b9ffe56c56243a9fde4610d324513d80c4`.

| Check | Observed result | Boundary |
|---|---|---|
| Original test baseline | 5 passed | Grid geometry and overlap/status logic |
| Expanded suite | **28 passed, 0 failed, 0 skipped** | Original tests plus evaluation, CRS, gravity units, glacial direction, ties, missingness, archive traversal and MC regressions |
| Synthetic pipeline | 900 cells; 864 evaluated; 9 positives; 5 grouped folds; complete finite OOF coverage | Fictional data only; no Finnish predictive-validity claim |
| Repeated synthetic run | All **six** generated CSV/JSON outputs byte-identical under the locked environment | 500 MC iterations, seed 42; not cross-platform bitwise guarantee |
| Historical aggregate consistency | 3,649 cells, eight positives, 0.798 rounded AUC and 1/8 top-5% capture agree across summaries | No original prediction/feature tables, so no independent real-data recomputation |
| Original Gitleaks history scan | 0 alerts across all reachable refs | Supplemented by decoded object/privacy inspection |
| Current release integrity/privacy | `scripts/check_release.py` checks every manifest hash, local links, target/key/path patterns and fold coverage | Automated pattern checks supplement manual review; do not certify original history safe |
| Figures | Six PNG and six SVG exports generated; rendered figures inspected and footer overlap repaired | Context map uses Natural Earth; feature/MC/CV panels synthetic; performance panel historical aggregates |
| Python source | All retained modules compile | Compile success is not proof of external-data execution |
| CI | Workflow supplied; private-branch execution recorded in the owner handoff when available | No public deployment or publication step |

The first XGBoost import failed because macOS lacked `libomp`; installing the documented OpenMP runtime resolved it. The original model's global imputation/class weighting, missing-column crash on an empty extra-cell set, and other corrections are described in `SCIENTIFIC_AUDIT.md`. No historical metric was modified to make it pass a benchmark.

The legal/privacy review excludes original targets and unclear third-party inputs. The private release branch still has confidential ancestors and must not itself be exposed publicly. The clean-history handoff is separately scanned before delivery.
