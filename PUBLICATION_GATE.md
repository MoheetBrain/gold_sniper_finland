# Publication gate

**Status: PRIVATE RELEASE CANDIDATE — NOT APPROVED FOR PUBLICATION.**

The current private repository must remain private. An isolated release branch holds the curated candidate; a separate clean-history local repository is prepared for review. No remote public repository, public release or social-media post has been created.

## Included

Generic original ingestion/GIS/feature/model/Monte Carlo code; corrected evaluation helpers; original and new tests; an offline synthetic demonstration; historical aggregate reports; dataset/rights register; scientific audit; six reproducible figures; CV and X drafts; a dependency lock and CI workflow. The README is scoped to these implemented capabilities. It makes no GNN, discovery, calibrated probability or independently reproduced historical-AUC claim.

## Excluded and preserved privately

Unpublished selected-cell coordinates, candidate CSV/GeoPackage and narrative selections; target maps/lookup references; personal paths/author metadata in original history; GISCO and other unneeded source boundaries; raw/uncleared source datasets; imagery/tiles; TerraMind prototypes and contrived fusion score; unverified target-specific v2 outputs/scripts. Original research and all history are preserved in a verified local mirror and bundle.

## Gate decisions

| Gate | Outcome |
|---|---|
| Original preservation | Verified local mirror and complete bundle; no history rewrite/deletion |
| Current-tree credentials/privacy | Scanned; no confirmed credentials; selected targets excluded |
| Unexpected visibility incident | **OWNER ATTENTION REQUIRED**: source repo was observed public during work, then restored private; cause/exposure interval unknown |
| Original-history publication | **BLOCKED**: private metadata/targets persist in ancestors and messages |
| Clean-history candidate | Prepared locally with a new root commit, no remote; separately scanned |
| Data redistribution | Only Natural Earth public-domain geometry plus project aggregates/synthetic data; notices retained |
| Raw source licences | Some product-specific terms unresolved; raw source data remains excluded |
| Scientific reproduction | Synthetic pipeline executed; historical summaries consistent, original real-data metrics not reproduced |
| Tests and figures | See exact evidence in [VALIDATION.md](docs/VALIDATION.md) |
| Code licence | **OWNER APPROVAL REQUIRED**: recommend MIT; proposed text supplied, not activated |
| Public visibility / launch | **OWNER APPROVAL REQUIRED**; no publication authorised yet |

No material limitation is hidden behind a “ready” label. The code-only/synthetic release can be considered for publication after owner approval of its exact contents, licence and disclosed scientific boundaries. Restoring real-data reproduction is a separate research task, not a prerequisite to making a truthfully scoped demonstration available.

## Owner review

Review the exclusions/coordinate inventory and the rendered README. Decide whether to approve (1) publication of this curated tree, (2) MIT for owned code/docs/synthetic fixtures, and (3) the general regional map/configuration. Exact unpublished target coordinates remain excluded unless separately approved after inventory review.

## Publication steps — ONLY after explicit approval

Use the prepared **clean-history local repository**, never the original clone or private release branch. Before changing anything, verify `git rev-list --all --count` is 1 and `git remote -v` is empty; inspect the sole root commit and `git ls-files`. Do not import branches/tags from the original.

If MIT is approved:

```bash
cp LICENSE.proposed LICENSE
# Update README and this gate to record approval, keeping scientific limits.
python scripts/build_manifest.py
python scripts/check_release.py
python -m pytest -q
# Review the changed files, then commit the approval and licence activation.
git add LICENSE README.md PUBLICATION_GATE.md RELEASE_MANIFEST.json
git commit -m "Approve curated public release and activate MIT licence"
```

Create a **new private** GitHub repository first, with no initial README/licence/gitignore. Choose an available name such as `geoarb-finland`; do not assume it exists or overwrite a repository. In the prepared clean checkout:

```bash
git remote add origin https://github.com/MoheetBrain/geoarb-finland.git
git push -u origin main
```

Check GitHub's file list, Actions results and contributor metadata while still private. Re-run the complete-history secret scan and verify no target files/identifiers or original ancestors are present. After the owner explicitly approves the final reviewed contents and visibility change, use **Settings → General → Danger Zone → Change repository visibility → Public** on the **new** repository. Leave `gold_sniper` private.

Tag/release only that approved tree, attach its manifest, and then replace the placeholder in the X draft. Do not automatically post. If any file is added after review, recheck its rights, identifiers and history before publication.
