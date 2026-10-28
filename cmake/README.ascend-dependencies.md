# Build dependency pins in cmake

Keep the existing upstream layout: LLVM metadata is JSON, while the
nlohmann-json version stays in `json-version.txt`. For the migrated source-build
consumers below, each dependency has one authoritative pin; using a single file
format is not required. Frozen release images have their own source binding;
they must not silently consume main's current LLVM.

| File | Authority and consumers |
| --- | --- |
| `llvm-info.json` | Full LLVM commit and the sorted Ascend patch manifest. Packaging, the LLVM source-build workflow and installation examples read the same checkout. |
| `json-version.txt` | nlohmann-json release tag, read directly by `get_json_package_info()` in `python/build_helpers.py`, following upstream and Intel. No JSON mirror. |
| `bisheng-info.json` | Bisheng installer filenames and SHA-256 per architecture. CI installation steps read and verify these inputs. |
| `ascend-runtime-info.json` | Observed CANN groups, explicit requirements binding and the exact release-policy reconciliation. This is not a complete environment profile. |
| `release-image-info.json` | Selected release wheel version, immutable source SHA, LLVM/patch snapshot, CANN selector and Python version for the generic release image. Torch versions come from the selected runtime group. |
| `triton-distributed-info.json` | Optional Triton-Distributed repository and exact source revision, read by the Ascend preparation hook. |
| `npuir-info.json` | NPU-IR repository and watch branch, read by the fetch script and its resolve-only mode. A moving branch is not a release lock. |

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

Requirements keep their explicit 8.5.0 group. Development Docker reads its torch
stack from the JSON group selected by CANN_BASE_IMAGE; TORCH_NPU_VERSION remains
an explicit override. Missing, duplicate, experimental
or planned default selections fail. The observed 9.2.0 nightly group remains
experimental in this prototype's default-selection policy. That label does not
replace the project's published support matrix in the release notes. Beta
builder exceptions are file-scoped. Requirements retain their package-manager
pin and are checked against their selected group.
Only the recorded CANN9.0.0/documented-torch2.10.0/profile-torch2.7.1 conflict
is a warning with tracking, requested owner and exit information. Other drift
fails; this record does not resolve the conflict or certify support.

Wheel build, test and publication now share the requested push/manual source
ref and an artifact-safe tag. Post-submit CI queries the current branch by
workflow filename rather than a repository-specific numeric workflow ID.
This prototype does not implement full chip/arch/Python/track profiles,
upstream main/release baseline tracking, NPU-IR release locking, complete artifact integrity or compatibility
certification. Requirements, release version files and plugin names retain their
existing packaging roles.

## Hardcoded inputs outside the migrated path

The checker passing does not establish that all dependency literals have been
removed. Its document checks cover four installation sources; its release-policy
check covers the main row's CANN, PyTorch, LLVM and patch columns, but not
the separate release-note matrices. Workflow checks cover CANN declarations and
cache paths, not complete SoC/OS/Python/ABI tuples or release refs.

| Remaining input | Boundary and follow-up |
| --- | --- |
| Generic release image | The workflow reads release-image-info.json and passes its resolved inputs to the existing Dockerfile. Docker checks those arguments against the same metadata, reads the release's LLVM SHA, and downloads patches from its immutable source SHA with SHA-256 verification before applying them. No independent LLVM_COMMIT argument remains. |
| Frozen release snapshot | The initial snapshot was extracted from v3.6.0 source commit 97e8a2be1e46817c359f55c0e6464e49480d0b1f. Its LLVM f6ded0b and patch digest describe that release, not a mirror of main. Updating main's LLVM must not update this snapshot. This source binding does not authenticate the downloaded wheel binary. |
| Historical release Dockerfiles | Eighteen 3.2.1/3.2.2 recipes retain their LLVM commit. Preserve frozen release inputs rather than rewriting them to main's LLVM. |
| NPU-IR and Triton-Distributed | Their source settings now live in their respective cmake JSON files. NPU-IR still resolves a watch branch, with explicit environment overrides preserved. Triton-Distributed checks out and verifies its exact revision even when preparing an sdist outside a Git checkout. |
| CI fixtures and infrastructure | Mojo's source SHA and pytest/einops pins are intentional test inputs. Workflow IDs, registries, image tags and download origins have separate roles; they are not all compiler dependency pins. |

Upstream reverted the legacy PO translation mechanism in 87cd8f424 and restored
direct English-source builds. Do not restore those catalogs; both installation
source documents retain their local JSON/patch reads. Rendered-doc validation
remains separate from checking the installation sources.

## Updating dependencies

1. Change the authoritative file directly. Update LLVM patches and their
   manifest atomically. Never recreate `llvm-hash.txt` or `json-info.json` mirrors.
2. Review each affected consumer without redirecting unrelated environments
   through a global default.
   The release-image snapshot is a separate release-scoped authority: resolve
   the selected immutable release source, extract its LLVM revision and patch
   digests, and review that binding together. Do not copy main's current pin.
3. Run `python scripts/check_bom_consistency.py` and
   `python -m pytest -q third_party/ascend/build_tests`.
4. Aggregate compiler caches cover `llvm-info.json`, `json-version.txt`,
   `bisheng-info.json`, actual patch contents and NVIDIA metadata. Runtime/docs
   changes do not rotate that dependency portion.

The source-distribution manifest already includes `python/build_helpers.py` and
grafts cmake/third_party. Static inclusion does not replace a real sdist
build/install check. External scripts must migrate the retired LLVM/Bisheng text
interfaces; historical release checkouts remain a separate migration concern.
