"""Consistency checks between the dependency BOM and its consumers.

The single source of truth for pinned dependencies is ``third_party/ascend/deps/``
(see ``third_party/ascend/deps/README.md``). This script verifies that every
consumer -- the ``cmake/`` mirrors, ``requirements.txt``, ``docker/Dockerfile``
build args, CI workflow literals and the release policy -- agrees with the
BOM, so a version bump that forgets one of the copies fails loudly instead of
silently desynchronizing.

Run locally:  python scripts/check_bom_consistency.py
"""

import glob
import json
import os
import re
import runpy
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEPS_DIR = REPO_ROOT / "third_party" / "ascend" / "deps"
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

# BOM schema revision understood by this checker; every deps/*.json must
# declare exactly this version.
SCHEMA_VERSION = 1

# Checkout roots used by workflows when calling hashFiles(). A hashFiles()
# argument is resolved only after stripping one of these declared prefixes --
# never an arbitrary leading path component.
CHECKOUT_ROOTS = ("", "pr/")

# Beta CANN builder images referenced by CI before the corresponding runtime
# group is official enough to be listed in runtime.json. Per RFC #2739 §2 these
# are narrow-scope exceptions with a removal condition, not a second source of
# truth: each entry must be dropped when its consumer goes away or when a
# matching runtime group lands in runtime.json (e.g. a 9.2.0 group with the
# torch pins it actually ships with):
#   - 9.0.0-beta.2 / 9.2.0-beta.1: build-docker-image.yml beta artifact matrix
#   - 9.2.0-beta.2: manylinux builder image -- the manylinux ABI needs the
#     preinstalled CANN; also pinned by npuir-build.yml
BETA_CANN_WHITELIST = {"9.0.0-beta.2", "9.2.0-beta.1", "9.2.0-beta.2"}

# Guides that must not hardcode an LLVM checkout; they read
# cmake/llvm-hash.txt dynamically instead. Any 40-hex `git checkout` literal
# (or hardcoded llvm_patch_<hash>.patch filename) that reappears here is a
# regression and must at least agree with the BOM.
DOC_SITES = (
    "README.md",
    "README_zh.md",
    "docs/en/installation_guide.md",
    "docs/zh/installation_guide.md",
)

# Matches container tags ("cann:9.0.0-a3-ubuntu22.04-py3.12"), install paths
# ("cann-9.2.0-beta.2") and cache-key literals ("cann8.5.0").
CANN_VERSION_RE = re.compile(r"cann[:-]?(\d+(?:\.\d+)*(?:-beta\.\d+)?)")

errors = []
warnings = []


def _fail(check, message):
    errors.append(f"[{check}] {message}")


def _warn(check, message):
    warnings.append(f"[{check}] {message}")


def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _line_no(text, pos):
    return text.count("\n", 0, pos) + 1


def _load_llvm_info():
    reader = runpy.run_path(str(REPO_ROOT / "third_party/ascend/build/llvm.py"))
    return reader["load_llvm_info"](REPO_ROOT)


def check_llvm_info():
    try:
        _load_llvm_info()
    except (OSError, ValueError) as exc:
        _fail("llvm-info", str(exc))


def check_toolchain():
    toolchain = _load_json(DEPS_DIR / "toolchain.json")
    mirrored = _read(REPO_ROOT / "cmake" / "json-version.txt").strip()
    if toolchain["json"] != mirrored:
        _fail("toolchain", f"toolchain.json json={toolchain['json']} != cmake/json-version.txt={mirrored}")


def check_schema_versions():
    for name in ("llvm-info.json", "toolchain.json", "runtime.json"):
        data = _load_json(DEPS_DIR / name)
        if data.get("schema_version") != SCHEMA_VERSION:
            _fail("schema",
                  f"{name} must declare \"schema_version\": {SCHEMA_VERSION} (got {data.get('schema_version')!r})")


def _runtime_groups(runtime):
    groups = {}
    for group in runtime.get("runtimes", []):
        cann = group.get("cann")
        if not isinstance(cann, str) or cann in groups:
            _fail("runtime-schema", f"invalid or duplicate CANN group: {cann!r}")
            return {}
        if any(not isinstance(group.get(key), str) or not group[key] for key in ("torch", "torch_npu", "status")):
            _fail("runtime-schema", f"CANN {cann} needs torch, torch_npu and status strings")
            return {}
        groups[cann] = group
    selected = [runtime.get("default_cann"), runtime.get("consumers", {}).get("requirements.txt")]
    for cann in selected:
        if cann not in groups or groups[cann]["status"] == "planned":
            _fail("runtime-schema", f"active consumer selects missing or planned CANN group: {cann!r}")
            return {}
    return groups


def check_static_pins(runtime):
    runtimes_by_cann = _runtime_groups(runtime)
    if not runtimes_by_cann:
        return

    # Consumers are validated against the complete runtime group (the full
    # stack tuple), never against the union of values across groups: a value
    # that only exists in another CANN group (e.g. a planned one) must not
    # satisfy this consumer.

    pin = re.search(r"^torch-npu==(\S+)", _read(REPO_ROOT / "requirements.txt"), re.MULTILINE)
    if pin is None:
        _fail("static-pins", "requirements.txt has no 'torch-npu==<version>' pin")
    else:
        selected_cann = runtime["consumers"]["requirements.txt"]
        default_group = runtimes_by_cann[selected_cann]
        if default_group is not None and pin.group(1) != default_group["torch_npu"]:
            _fail(
                "static-pins", f"requirements.txt torch-npu=={pin.group(1)} does not match the torch_npu of the "
                f"runtime.json group assigned to requirements.txt (CANN {selected_cann}) "
                f"(expected {default_group['torch_npu']})")

    dockerfile = _read(REPO_ROOT / "docker" / "Dockerfile")
    pin = re.search(r"^ARG\s+TORCH_NPU_VERSION=(\S+)", dockerfile, re.MULTILINE)
    if pin is None:
        _fail("static-pins", "docker/Dockerfile has no 'ARG TORCH_NPU_VERSION=' default")
        torch_npu_default = None
    else:
        torch_npu_default = pin.group(1)

    pin = re.search(r"^ARG\s+CANN_BASE_IMAGE=(\S+)", dockerfile, re.MULTILINE)
    if pin is None:
        _fail("static-pins", "docker/Dockerfile has no 'ARG CANN_BASE_IMAGE=' default")
    else:
        cann = CANN_VERSION_RE.search(pin.group(1))
        if cann is None:
            _fail("static-pins", f"docker/Dockerfile CANN_BASE_IMAGE={pin.group(1)} carries no CANN version")
        elif cann.group(1) not in runtimes_by_cann:
            _fail(
                "static-pins", f"docker/Dockerfile CANN_BASE_IMAGE pins CANN {cann.group(1)}, not a cann value in "
                f"runtime.json (known: {sorted(runtimes_by_cann)})")
        elif torch_npu_default is not None and torch_npu_default != runtimes_by_cann[cann.group(1)]["torch_npu"]:
            _fail(
                "static-pins", f"docker/Dockerfile TORCH_NPU_VERSION={torch_npu_default} does not match the "
                f"torch_npu of the runtime.json group selected by CANN_BASE_IMAGE (CANN {cann.group(1)}, "
                f"expected {runtimes_by_cann[cann.group(1)]['torch_npu']})")
        if cann is not None and cann.group(1) in runtimes_by_cann:
            group = runtimes_by_cann[cann.group(1)]
            if group["status"] == "planned":
                _fail("static-pins", "docker/Dockerfile selects a planned runtime")
            torch_pin = re.search(r"(?m)^\s*torch==(\S+)", dockerfile)
            expected = group["torch"] + "+cpu"
            if torch_pin is None or torch_pin.group(1) != expected:
                _fail("static-pins", f"docker/Dockerfile must install torch=={expected} for its selected group")


def _workflow_files():
    for path in sorted(WORKFLOWS_DIR.rglob("*")):
        if path.is_file():
            yield path


def _glob_exists(relative):
    """Check a (possibly checkout-prefixed) hashFiles() argument against the repo.

    Some workflows check the PR out under a ``pr/`` directory, so arguments
    like ``pr/cmake/llvm-hash.txt`` must match after stripping the prefix.
    Only the declared :data:`CHECKOUT_ROOTS` prefixes may be stripped; an
    arbitrary leading component (a typo like ``wrng/requirements.txt``) must
    keep failing even when the remaining path exists.
    """
    for root in CHECKOUT_ROOTS:
        if not relative.startswith(root):
            continue
        candidate = relative[len(root):]
        if glob.glob(os.path.join(REPO_ROOT, candidate), recursive=True):
            return True
    return False


def check_workflows(runtime):
    groups = _runtime_groups(runtime)
    if not groups:
        return
    known_cann = {cann for cann, group in groups.items() if group["status"] != "planned"} | BETA_CANN_WHITELIST
    list_re = re.compile(r"cann_version[\"']?\s*:\s*\[([^\]]*)\]")
    scalar_re = re.compile(r"cann_version[\"']?\s*:\s*[\"']?([\w.\-]+)")
    hash_files_re = re.compile(r"hashFiles\(([^)]*)\)")

    for path in _workflow_files():
        text = _read(path)
        rel = path.relative_to(REPO_ROOT).as_posix()

        for match in CANN_VERSION_RE.finditer(text):
            version = match.group(1)
            if version not in known_cann:
                _fail(
                    "workflows-cann", f"{rel}:{_line_no(text, match.start())} references CANN {version}, which is "
                    f"not declared in runtime.json or the beta whitelist")

        for line_no, line in enumerate(text.splitlines(), start=1):
            list_match = list_re.search(line)
            if list_match is not None:
                for item in list_match.group(1).split(","):
                    item = item.strip().strip("\"'")
                    if item and item not in known_cann:
                        _fail("workflows-cann",
                              f"{rel}:{line_no} cann_version entry '{item}' not declared in runtime.json")
                continue
            scalar_match = scalar_re.search(line)
            if scalar_match is not None and scalar_match.group(1) not in known_cann:
                _fail("workflows-cann", f"{rel}:{line_no} cann_version '{scalar_match.group(1)}' not in runtime.json")

        for match in hash_files_re.finditer(text):
            for arg in match.group(1).split(","):
                arg = arg.strip().strip("\"'")
                if arg and not _glob_exists(arg):
                    _fail(
                        "workflows-hashfiles", f"{rel}:{_line_no(text, match.start())} hashFiles argument "
                        f"'{arg}' matches no file in the repo")


def check_docs_llvm_hash():
    """The install guides must follow cmake/llvm-hash.txt, not restate it.

    The guides read the pin dynamically (``LLVM_COMMIT=$(cat
    cmake/llvm-hash.txt)``), so no 40-hex checkout literal should remain. If
    one is reintroduced, it must at least match the BOM.
    """
    info = _load_llvm_info()
    llvm_hash = info["llvm_hash"]
    checkout_re = re.compile(r"git checkout ([0-9a-f]{40})\b")
    patch_re = re.compile(r"llvm_patch_([0-9a-f]{7,40})\.patch")
    for rel in DOC_SITES:
        text = _read(REPO_ROOT / rel)
        for match in checkout_re.finditer(text):
            if match.group(1) != llvm_hash:
                _fail(
                    "docs-llvm-hash",
                    f"{rel}:{_line_no(text, match.start())} hardcodes 'git checkout {match.group(1)}', "
                    f"but the BOM pins {llvm_hash}; read cmake/llvm-hash.txt instead")
        for match in patch_re.finditer(text):
            if match.group(0) not in info["patches"]:
                _fail(
                    "docs-llvm-hash",
                    f"{rel}:{_line_no(text, match.start())} references patch {match.group(0)}, which does "
                    f"not appear in the local LLVM patch manifest")


def check_release_policy(runtime):
    runtimes_by_cann = _runtime_groups(runtime)
    if not runtimes_by_cann:
        return
    lines = _read(REPO_ROOT / "docs" / "en" / "community" / "release_policy.md").splitlines()

    # The "main Branch Mapping" header uniquely contains "Triton commit hash";
    # the later compatibility matrix table does not.
    header_idx = next(
        (i for i, line in enumerate(lines) if "Triton commit hash" in line and "CANN" in line and "PyTorch" in line),
        None)
    if header_idx is None:
        _fail("release-policy",
              "cannot find the 'main Branch Mapping' table header in docs/en/community/release_policy.md")
        return
    columns = [c.strip() for c in lines[header_idx].strip().strip("|").split("|")]
    try:
        cann_col = columns.index("CANN")
        torch_col = columns.index("PyTorch")
    except ValueError:
        _fail("release-policy", "'main Branch Mapping' table header lacks a CANN or PyTorch column")
        return

    for line in lines[header_idx + 1:]:
        stripped = line.strip()
        if not stripped.startswith("|"):
            break
        if set(stripped) <= set("|-: "):
            continue
        cells = [c.strip().strip("`") for c in stripped.strip("|").split("|")]
        if not cells or cells[0] != "main":
            continue
        cann = cells[cann_col] if cann_col < len(cells) else ""
        torch = cells[torch_col] if torch_col < len(cells) else ""
        if cann != runtime["default_cann"]:
            _fail(
                "release-policy", f"release_policy.md maps 'main' to CANN {cann}, but runtime.json "
                f"default_cann={runtime['default_cann']}")
        expected_torch = runtimes_by_cann[runtime["default_cann"]]["torch"]
        if torch != expected_torch:
            conflict = runtime.get("reconciliation", {}).get("release_policy.main", {})
            recorded = (conflict.get("cann"), conflict.get("documented_torch"), conflict.get("profile_torch"))
            message = (f"release_policy.md main maps CANN {cann} to PyTorch {torch}, "
                       f"but its runtime group declares {expected_torch}")
            if (recorded == (cann, torch, expected_torch) and conflict.get("tracking") and conflict.get("owner")
                    and conflict.get("exit_condition")):
                _warn("release-policy", message + f"; recorded conflict: {conflict['tracking']}")
            else:
                _fail("release-policy", message + "; not the exact recorded reconciliation item")
        return
    _fail("release-policy", "no 'main' row found in the 'main Branch Mapping' table")


def main():
    check_schema_versions()
    check_llvm_info()
    check_toolchain()
    check_docs_llvm_hash()
    runtime = _load_json(DEPS_DIR / "runtime.json")
    check_static_pins(runtime)
    check_workflows(runtime)
    check_release_policy(runtime)

    if warnings:
        print("BOM consistency warnings (reported for reconciliation, not failing):")
        for warning in warnings:
            print(f"  - {warning}")
    if errors:
        print("BOM consistency check FAILED:")
        for error in errors:
            print(f"  - {error}")
        raise SystemExit(1)
    print("BOM consistency check passed (deps/ BOM, cmake mirrors, static pins, "
          "docs LLVM refs, workflows, release policy).")


if __name__ == "__main__":
    main()
