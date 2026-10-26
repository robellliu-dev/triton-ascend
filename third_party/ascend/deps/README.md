# Dependency BOM (Bill of Materials)

This directory is the single source of truth for the external dependencies
pinned by Triton-Ascend builds and CI. Consumers — the `setup.py` hooks,
build scripts and GitHub Actions workflows — read their pinned versions from
the files below instead of hardcoding them, mirroring how other backends
(e.g. Intel XPU) keep their dependency pins in one place.

## Files

| File | Contents | Read by |
| ---- | -------- | ------- |
| `llvm-info.json` | LLVM commit hash, `llvm_patch_*.patch` manifest, prebuilt-package checksums | `third_party/ascend/build/setup_patch.py` (`json.load` — prebuilt LLVM download), `scripts/build-llvm-project.sh` (`jq` — local LLVM builds), `.github/workflows/llvm-build.yml` (`jq` — prebuilt LLVM publishing) |
| `toolchain.json` | Bisheng compiler run packages per arch (with sha256), nlohmann-json version | Bisheng install steps in the CI workflows (`jq`) |
| `runtime.json` | Supported CANN runtimes and their matching torch / torch-npu versions | CI matrix values and container image tags |

`toolchain.json` and `runtime.json` are currently read by
`scripts/check_bom_consistency.py` only; the workflows still carry their own
copies of some of these values and are migrated to read the BOM directly in
follow-up changes. The consistency check keeps the two in sync in the
meantime.

## Relation to the `cmake/` mirrors

Two legacy single-value files under `cmake/` are still consumed by code shared
with upstream Triton and are kept as mirrors of this BOM:

- `cmake/llvm-hash.txt` mirrors `llvm-info.json` -> `llvm_hash`
- `cmake/json-version.txt` mirrors `toolchain.json` -> `json`

`scripts/check_bom_consistency.py` (run by the *BOM Consistency Check* CI
workflow) fails if a mirror drifts from the BOM, so a version bump that
forgets one of the copies is caught at PR time.

`cmake/bisheng-version.txt` is the pre-BOM location of the Bisheng pins and is
still consumed by several workflows; it will be removed once those workflows
read `toolchain.json` directly.

## Updating a dependency

1. Edit the entry in the JSON file in this directory. Never edit the `cmake/`
   mirrors by hand.
2. Update the mirrors (`cmake/llvm-hash.txt`, `cmake/json-version.txt`) and —
   until the remaining migrations land — the still-hardcoded workflow values
   to the same version.
3. Run `python scripts/check_bom_consistency.py` locally; it must pass.
4. Commit everything in one change so cache keys derived from these files
   rotate atomically.

## Known reconciliation items

The values below currently disagree across the repository. They are recorded
here (and surfaced by `scripts/check_bom_consistency.py` as warnings where
applicable) instead of being silently adjudicated by this BOM; the runtime
owners must reconcile them before the affected groups can be called verified:

- `runtime.json` maps the `default_cann=9.0.0` (main) group to
  torch `2.7.1` / torch-npu `2.7.1.post8`, which matches `requirements.txt`
  and the `docker/Dockerfile` defaults.
- `docs/en/community/release_policy.md` maps the `main` branch to CANN 9.0.0
  but PyTorch 2.10.0.
- `release_note.md` and the top-level `README.md` describe `main` as pairing
  with torch-npu 2.10.0.post7 and CANN 9.2.0 (a *planned* group in
  `runtime.json`, not the current default).
- `docker/Dockerfile` comments note that the CANN 9.1.0 (a5/Ascend 950) image
  line uses torch-npu 2.10.0.post4; no runtime group declares that pairing
  yet (the 9.1.0 entry currently declares 2.7.1.post8).

## Out of scope

- The `Triton-distributed-ascend` submodule (pinned via git like all
  submodules).
- Release-line docker images under `docker/3.x.x-*/` (frozen per release).
