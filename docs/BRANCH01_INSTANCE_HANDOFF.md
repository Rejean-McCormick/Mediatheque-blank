# Private library instance and EncyK handoff — Branch 01

**Status:** `TARGET_DESIGN` and selected local code behavior, not production qualification.

`Mediatheque-blank` is **not** another shared engine. It is a local, empty private instance template whose `01_DB`, `02_STORAGE`, `03_IMPORTS`, backup and logs remain separate. It calls the one shared sibling Médiathèque engine. This repository has no default access to existing `D:` source databases and does not migrate any real production library.

## Selected local flow

1. Before initialization, call `python tools/instance_guard.py --instance-root .` to verify the local manifest, engine version `0.5.1` and private path boundaries.
2. Initialize the instance deliberately with `Initialize.ps1`; initialization must refuse an existing database rather than overwrite it.
3. Plan a Skope/EncyK `encyk.source-evidence-handoff/2.0.0` with `Import-EncyK.ps1 -Handoff ... -EvidenceRoot ...` (no `-Accept`).
4. Inspect the source licensing and operator trust; only then use `Import-EncyK.ps1 ... -Accept`. The wrapper routes to the shared engine with explicit `--instance-root` and stores an attempt/receipt in this instance's private `03_IMPORTS/encyk_receipts` directory.
5. Verify the imported source/snapshot/representation references and on-disk bytes in the **selected** instance. Skope's `verify_mediatheque_receipt.py` can correlate a copied receipt with the producer manifest, but does not authenticate an unsigned receipt or verify storage by itself.

The shared engine importer must refuse symlinked/junction storage and database paths. A successful custody import leaves all source rights **private** and grants no semantic identity or publication permission.

## Acceptance and limits

- `python -m unittest discover -s tests -v` tests the template preflight, path isolation and Git privacy locally.
- The combined Skope→Médiathèque test lives in the shared engine and runs only when `KOA_SKOPE_REPO` is provided. It uses disposable synthetic Wikidata evidence, never a real `D:` dump.
- PowerShell entrypoints and the target Windows environment are **not** executed in this Linux snapshot validation; verify them in a controlled Windows setup.
- If a future DaaT consumer needs source identifiers, it must request an explicit, permission-bound read interface from the instance; receiving a source UUID or unsigned receipt is not enough.
