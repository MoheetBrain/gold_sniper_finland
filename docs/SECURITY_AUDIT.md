# Security, privacy and publication-exposure audit

Date: 2 November 2026. Original repository remains **private**. Scope: all advertised branches/tags and reachable objects; no PR-head refs, releases or Actions artifacts were present at initial inspection. One branch, no tags; 12 commits, 41 trees, 122 blobs. The complete local mirror and verified Git bundle preserve the original history. Ignored files existing only on another machine are outside this audit and were not recovered.

Gitleaks 8.30.1 scanned all reachable history with full redaction: **zero alerts**. A supplementary pass decoded all blobs/commit metadata, all ZIP members and text cells in historical SQLite/GeoPackage objects. It checked key/token/private-key patterns, personal paths, email metadata and selected-cell identifiers without printing values. No credentials were confirmed. Pattern scanning cannot prove arbitrary secrets are absent.

Historical personal author email metadata, machine paths, selected-cell identifiers and target geometry were found. Natural Earth source-attribution contact details are public attribution, not credentials. The target CSV/GeoPackage, target narratives, map lookup references and selection-bearing prototype scripts are omitted from the release tree. All original material remains recoverable privately.

**The original repository must not be made public.** Deleting files on this release branch does not remove their ancestors or confidential commit messages. The required publication route is a fresh repository containing only the reviewed candidate tree, with a new root commit and public noreply author identity. No history rewrite, force push or branch deletion was performed. No publication was performed by this release workflow.

The prepared clean-history local candidate has no remote; its root commit contains the reviewed files only. Its complete reachable history is scanned separately before handoff. Do not push original refs, private bundles, backups, audit exports, pull-request discussions or unreviewed artifacts to a public destination.

## Coordinate inventory and exclusions

- Private original `data/outputs/review_candidates_audited.csv` and matching GeoPackage: 63 rows containing selected cells and geographic coordinates/geometry; excluded entirely.
- Original review narrative, candidate diagnostics, target maps and atlas/lookup code: may link identifiers to priority targets; excluded where selections are embedded.
- v2 and TerraMind scripts: hard-coded selected-cell/map identifiers and/or private paths; excluded.
- Public candidate: fictional `synthetic_*` cells; general regional configuration; public country outlines. No original selected-cell lookup or exact unpublished target geometry is distributed.
- Historical aggregate JSON/CSV: no location-level rows or target identifiers; retained unchanged.

A private file-level inventory with hashes and exclusion decisions accompanies the owner handoff. No target coordinates are printed here. General AOI bounds and country geometry are not confidential exploration-target disclosures.

## Data rights and confidentiality

Restricted/uncertain raw geodata, GISCO boundaries, original tile-backed maps, source caches, imagery and prototypes are excluded. Natural Earth provides the only third-party geometry. Open-source code licensing remains proposed, awaiting the owner; no data is relicensed by implication. See `DATA_SOURCES_AND_LICENSES.md`.

## Limits

This covers fetched reachable Git material and accessible repository artifacts, not unreachable server objects, independent backups, forks or previously downloaded copies. The clean-history route avoids carrying the inspected private ancestors into the proposed public repository; it does not erase private originals. No personal correspondence, identity documents or confirmed service credentials were identified in the fetched snapshot.

## Unexpected visibility incident — owner attention required

GitHub reported the repository private at initial inspection, but a pre-push check later reported it public. This workflow had issued no command to make it public. Following the instruction to keep it private, visibility was restored to private and independently verified through the GitHub API at **2026-11-02 20:17:33 UTC**. No candidate branch had been pushed before containment.

The cause and exact exposure interval are unknown. The existing private-source history includes original targets and personal metadata, so any public interval may have exposed them. No credential was found, but privacy/confidentiality cannot be retroactively guaranteed. Review account/repository activity and any unintended public copies before launching. Restoring private visibility cannot recall clones or caches. No historical rewrite or deletion was attempted.
