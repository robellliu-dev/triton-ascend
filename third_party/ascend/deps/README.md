# Ascend dependency catalog (source BOM)

This directory indexes Ascend-owned dependency metadata. It is not an artifact
SBOM or proof that a runtime combination has passed hardware validation.
The current PR is a migration prototype; the full profile/track model in
RFC #2739 is not implemented here.

## LLVM: one revision pin, separate metadata

| File | Authority and readers |
| --- | --- |
| `cmake/llvm-hash.txt` | The **only persisted LLVM revision pin** for this source checkout. Existing upstream-derived `setup.py` and external build/sync readers keep using it. |
| `llvm-info.json` | References that file through `llvm_hash_file` and lists Ascend LLVM patches. It does not copy the SHA. |
| `third_party/ascend/build/llvm.py` | Dependency-free reader/CLI used by Ascend packaging, the local shell wrapper, LLVM CI and the consistency check. No Triton/setuptools import or network access. |

```json
{
  "schema_version": 1,
  "llvm_hash_file": "cmake/llvm-hash.txt",
  "patches": ["llvm_patch_f6ded0b.patch"]
}
```

The reader validates the canonical full SHA, metadata fields and the exact
sorted patch set. `llvm_hash` exists only in its resolved in-memory result.
Patch filenames must come from the manifest, never from a SHA prefix: the
current filename uses seven characters, whereas the package name uses eight.
Patch-content hashing and existing LLVM artifact names are unchanged.

Run from any working directory with the checkout path:

```bash
python3 /path/to/triton-ascend/third_party/ascend/build/llvm.py --hash
python3 /path/to/triton-ascend/third_party/ascend/build/llvm.py --patches
```

The shell build wrapper honors an explicit `LLVM_COMMIT_HASH` before invoking
the reader and uses `${PYTHON:-python3}`. Python 3 must be available when the
reader is needed. Custom/offline LLVM paths retain their existing semantics.
The existing `MANIFEST.in` grafts both `cmake` and `third_party`, including the
reader, canonical pin and metadata in source distributions.

Keeping these files is reasonable because their responsibilities differ.
Moving the sole SHA into JSON and removing the text file is possible only
after migrating all build/sync consumers, including external tools and
release branches. This PR avoids that broader compatibility change. No
manual or generated second LLVM SHA is needed in the meantime.

## Other files and current limits

- `toolchain.json` holds Bisheng run files/checksums and a `json_version_file`
  reference to `cmake/json-version.txt`. The text file is the only persisted
  nlohmann-json version; `setup.py` reads it to construct the download URL.
  Updating metadata alone used to leave the hardcoded download unchanged.
- `runtime.json` records observed CANN groups and current literal consumers.
  `requirements.txt` is explicitly assigned to its legacy 8.5.0 group; Docker
  defaults are checked against their own CANN base and torch/torch-npu pins.
  Missing/duplicate groups and active planned selections fail. These checks
  are an interim constraint, **not** the RFC's complete chip/arch/Python/track
  profile validator or a compatibility certification.
  CANN 9.2.0 is now observed in the upstream-added nightly image workflow,
  so it is recorded as experimental and unverified, rather than planned.
  Experimental groups cannot become the default container/requirements stack
  or Docker default through these selectors.
- `reconciliation.release_policy.main` records the exact existing
  CANN9.0.0/documented-torch2.10.0/profile-torch2.7.1 contradiction. Only that
  tuple is a warning with tracking/owner/exit information. A new mismatch
  fails; runtime/release owner reconciliation is still required.

The default group's and A5's conflicting compatibility statements remain
unverified; this metadata migration does not select a new supported stack.
Nullable LLVM checksum slots and an unused build number were removed rather
than implying artifact verification. RFC P3 defines a separate producer/
consumer integrity migration.

## Updating inputs

1. Change the LLVM revision only in `cmake/llvm-hash.txt`; update actual
   patches and their manifest together when necessary.
2. Update the relevant toolchain/runtime metadata and explicit consumers.
   Do not change another consumer implicitly by retargeting a global default.
3. Run `python scripts/check_bom_consistency.py` and
   `python -m pytest -q third_party/ascend/build_tests`.
4. Ensure aggregate dependency cache keys include `cmake/llvm-hash.txt`,
   `cmake/json-version.txt` and actual patch contents, plus metadata and recipe/platform inputs
   appropriate to that cache. Runtime/README-only changes are not LLVM inputs.

Catalog files belong to the same source checkout as their consumers. Release
builds must not silently read a different branch's latest metadata. Track
selection, NPU-IR locking and the full cross-branch rollout remain RFC work,
not behavior claimed as implemented by these prototype PRs.

The consistency checker rejects malformed or duplicate JSON keys, invalid
toolchain file names/checksums and runtime selections before emitting a legacy
container tag with `--default-cann`. Its temporary beta exceptions are scoped
to the observed workflow files. This is not a complete environment validator.

## Workflow adoption prototype

Bisheng installation steps read `toolchain.json` with jq. The current container
resolver jobs still select the legacy `default_cann` value; this preserves
current literals and is not the RFC's named profile/track implementation.
The deleted `cmake/bisheng-version.txt` had no remaining in-scope readers.
LLVM aggregate cache keys must include the canonical text pin and patch bytes;
none may rely on the JSON reference alone.
