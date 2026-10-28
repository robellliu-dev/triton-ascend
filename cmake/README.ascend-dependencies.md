# Build dependency pins in cmake

Keep the existing upstream layout: LLVM metadata is JSON, while the
nlohmann-json version stays in `json-version.txt`. One dependency has one
authoritative pin; using a single file format is not required.

| File | Authority and consumers |
| --- | --- |
| `llvm-info.json` | Full LLVM commit and the sorted Ascend patch manifest. Packaging, the LLVM source-build workflow and installation examples read the same checkout. |
| `json-version.txt` | nlohmann-json release tag, read directly by `get_json_package_info()` in `python/build_helpers.py`, following upstream and Intel. No JSON mirror. |
| `bisheng-info.json` | Bisheng installer filenames and SHA-256 per architecture. CI installation steps read and verify these inputs. |
| `ascend-runtime-info.json` | Observed CANN groups, explicit requirements binding and the exact release-policy reconciliation. This is not a complete environment profile. |

## Reading versus checking

Common packaging helpers live in the existing `python/build_helpers.py`:
`Package`, `check_env_flag()`, `get_json_package_info()` and
`get_llvm_package_info()`. They use the standard library without importing
Triton, setuptools or Ascend preparation hooks. `setup.py` imports these helpers;
Ascend-specific LLVM URLs, patch-content hashes and platform overrides stay in
`third_party/ascend/build/setup_patch.py`.

JSON-library download URLs follow `json-version.txt` with `read().strip()`.
LLVM download identities read `llvm_hash` with `json.load()`. No generic reader,
dynamic `runpy` loader, generated pin mirrors or cross-branch fallback is needed.
Shell and YAML use Python's JSON parser directly. Installation examples also
read the explicit patch manifest rather than deriving filenames from SHA prefixes.
Consumers report missing or malformed inputs through their normal read failures;
repository-wide strict validation belongs to `scripts/check_bom_consistency.py`.
The checker is not a packaging API.

The previous metadata-only CMake module has been removed: its revision variables
had no build consumers. Installed dependencies continue to use the existing
MLIR/LLVMConfig and JSON include discovery. A source commit cannot prove that an
arbitrary user-supplied LLVM binary matches it.

## Upstream comparison

The 2026-10-28 review used these immutable sources:

- [Triton build helpers](https://github.com/triton-lang/triton/blob/96ffafdd35cbd70f0a12a81ba2b3d1acb43888a2/python/build_helpers.py)
- [Intel build helpers](https://github.com/intel/intel-xpu-backend-for-triton/blob/fd8da9768986fe03457af09b23a167399af6892f/python/build_helpers.py)

Adopt the helper location, package description, environment-flag semantics,
direct text/JSON reads and separation from packaging entry-point side effects.
Both references currently pin the JSON library to `v3.11.3` in the text file.
Ascend keeps its existing versions, public artifact origins, patch hashing,
offline behavior and user path overrides.

Do not transplant the entire newer build-helper implementation: its
`BuildHelperArgs`, generated CMake variables, archive cache and mirror routing
require coordinated changes to the corresponding CMake and packaging callers.
Its LLVM `build_number` and platform `sha256sum` require an Ascend artifact
producer and verification contract; adding fields without that implementation
would not establish integrity. These remain follow-up work in RFC 2739.

## Runtime limits and compatibility

Requirements keep their explicit 8.5.0 group; Docker defaults are checked against
their own CANN, torch-npu and CPU torch tuple. Missing, duplicate, experimental
or planned default selections fail. The observed 9.2.0 nightly group remains
experimental and unverified. Beta builder exceptions are file-scoped.
Only the recorded CANN9.0.0/documented-torch2.10.0/profile-torch2.7.1 conflict
is a warning with tracking, requested owner and exit information. Other drift
fails; this record does not resolve the conflict or certify support.

This prototype does not implement full chip/arch/Python/track profiles,
release-ref resolution, NPU-IR locking, artifact integrity or compatibility
certification. Requirements, release version files and plugin names retain their
existing packaging roles.

## Updating dependencies

1. Change the authoritative file directly. Update LLVM patches and their
   manifest atomically. Never recreate `llvm-hash.txt` or `json-info.json` mirrors.
2. Review each affected consumer without redirecting unrelated environments
   through a global default.
3. Run `python scripts/check_bom_consistency.py` and
   `python -m pytest -q third_party/ascend/build_tests`.
4. Aggregate compiler caches cover `llvm-info.json`, `json-version.txt`,
   `bisheng-info.json`, actual patch contents and NVIDIA metadata. Runtime/docs
   changes do not rotate that dependency portion.

The source-distribution manifest already includes `python/build_helpers.py` and
grafts cmake/third_party. Static inclusion does not replace a real sdist
build/install check. External scripts must migrate the retired LLVM/Bisheng text
interfaces; historical release checkouts remain a separate migration concern.
