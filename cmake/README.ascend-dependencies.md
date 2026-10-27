# Dependency JSON in cmake

Following Intel's `cmake/llvm-info.json` layout and `llvm_hash` field, this
prototype puts dependency pins directly in JSON in the existing cmake directory.
The old Ascend deps directory and LLVM/JSON/Bisheng text pin files are removed.
There are no generated text mirrors, path-reference pins or silent text fallbacks.

| File | Authority and consumers |
| --- | --- |
| `llvm-info.json` | Full LLVM commit plus the exact sorted Ascend patch manifest. Python packaging, shell, LLVM CI, CMake and installation examples consume it. |
| `json-info.json` | nlohmann-json release tag. Python constructs the real download URL from it; CMake reads the same tag. |
| `bisheng-info.json` | Bisheng run files and SHA-256 per supported architecture. CI installation steps read and verify these inputs. |
| `ascend-runtime-info.json` | Observed CANN groups, explicit requirements binding and the exact existing release-policy reconciliation. It is an interim constraint, not full environment profiles. |
| `dependencies.py` | Standard-library-only reader and CLI shared by Python packaging, shell, CI and container validation. It does not import Triton or setuptools and does not access the network. |
| `TritonDependencies.cmake` | Native CMake `file(READ)` / `string(JSON)` reader, included by the root project. It records configure dependencies and source provenance; installed LLVM discovery still uses MLIR/LLVMConfig and explicit user paths. |

```json
{
  "schema_version": 1,
  "llvm_hash": "f6ded0be897e2878612dd903f7e8bb85448269e5",
  "patches": ["llvm_patch_f6ded0b.patch"]
}
```

The LLVM pin is stored only in this JSON. Patch names come from the manifest,
never a SHA prefix: the current patch filename uses seven characters, while
the existing package name uses eight. Patch-content hashing, artifact names
and download identity checks remain unchanged. Intel also maintains artifact
build numbers/checksums; copying those fields without a producer/consumer
integrity implementation would be misleading, so that remains RFC 2739 P3.
Intel still uses a JSON-library text pin; migrating it to `json-info.json` is
an explicit extension of its layout for this repository.

Run from any working directory with the source checkout path:

```bash
python3 /path/to/triton-ascend/cmake/dependencies.py --hash
python3 /path/to/triton-ascend/cmake/dependencies.py --patches
python3 /path/to/triton-ascend/cmake/dependencies.py --json-version
python3 /path/to/triton-ascend/cmake/dependencies.py --validate
```

Python validates schema versions/types, duplicate/unknown keys, full SHA values,
safe filenames and the exact sorted patch set. CMake validates its own JSON
schema/field types and LLVM revision/JSON tag syntax. JSON metadata does not
prove that a user-supplied LLVM binary matches the selected source revision.
The shell wrapper honors explicit `LLVM_COMMIT_HASH` first and otherwise uses
`${PYTHON:-python3}`. Parser failures stop before downloads. Its generic source
build behavior is unchanged; it is not a new Ascend patch-application entry point.

## Runtime limits and compatibility

Requirements keep their explicit 8.5.0 group; Docker defaults are checked against
their own CANN, torch-npu and CPU torch tuple. Missing, duplicate or planned
selections fail. The upstream-added nightly's 9.2.0 group is observed experimental
and unverified; it cannot become a default through the current selectors.
Only the recorded CANN9.0.0/documented-torch2.10.0/profile-torch2.7.1 conflict
is a warning with tracking, requested owner and exit information. Other drift
fails; that record does not resolve the incompatibility or certify support.
Beta builder exceptions are scoped to the observed files.

This prototype does not implement full chip/arch/Python/track profiles,
release ref resolution, NPU-IR locking, artifact integrity or compatibility
certification. Existing requirements/version files retain their packaging
roles; they are not the retired dependency pin interfaces.

## Updating dependencies

1. Change the relevant JSON directly, with actual patches and their manifest
   updated atomically. Do not recreate text copies or cross-branch fallbacks.
2. Update and review the explicitly assigned consumers without redirecting
   unrelated environments through a global default.
3. Run `python scripts/check_bom_consistency.py` and
   `python -m pytest -q third_party/ascend/build_tests`.
4. Aggregate build caches include LLVM/JSON/Bisheng JSON, actual patch contents,
   NVIDIA metadata and their relevant platform/recipe inputs. Runtime/docs-only
   changes do not rotate the LLVM dependency portion.

The existing source-distribution manifest grafts cmake and third_party, including
the reader, metadata, native CMake module and patches. This static inclusion
does not replace an actual source-distribution build/install check.
Migration removes the old text interfaces on this branch; external scripts
and future upstream merges must be migrated explicitly. Frozen release branches
use their own metadata/entry points and are not silently redirected to main.
