"""Read dependency JSON without importing Triton or the packaging backend."""

import argparse
import json
from pathlib import Path
import re


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate metadata key: {key}")
        result[key] = value
    return result


def load_document(base_dir, name, fields=None):
    metadata = Path(base_dir).resolve() / "cmake" / name
    with metadata.open(encoding="utf-8") as stream:
        info = json.load(stream, object_pairs_hook=_unique_keys)
    if not isinstance(info, dict) or (fields is not None and set(info) != fields):
        raise ValueError(f"{metadata} must be an object with fields {sorted(fields) if fields else 'schema_version'}")
    if type(info.get("schema_version")) is not int or info["schema_version"] != 1:
        raise ValueError(f"{metadata} requires schema_version 1")
    return info


def load_llvm_info(base_dir):
    root = Path(base_dir).resolve()
    info = load_document(root, "llvm-info.json", {"schema_version", "llvm_hash", "patches"})
    revision = info["llvm_hash"]
    if not isinstance(revision, str) or re.fullmatch(r"[0-9a-fA-F]{40}", revision) is None:
        raise ValueError("llvm_hash must contain exactly 40 hexadecimal characters")
    patches = info["patches"]
    if (not isinstance(patches, list)
            or any(not isinstance(name, str) or re.fullmatch(r"llvm_patch_[A-Za-z0-9_.-]+\.patch", name) is None
                   for name in patches)):
        raise ValueError("patches must list LLVM patch basenames")
    if patches != sorted(set(patches)):
        raise ValueError("patches must be unique and sorted to preserve the existing patch order")
    patch_dir = root / "third_party/ascend/patch"
    actual = sorted(path.name for path in patch_dir.glob("llvm_patch_*.patch") if path.is_file())
    if patches != actual:
        raise ValueError(f"LLVM patch manifest mismatch: declared {patches}, found {actual}")
    return info


def load_json_info(base_dir):
    info = load_document(base_dir, "json-info.json", {"schema_version", "version"})
    if not isinstance(info["version"], str) or re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", info["version"]) is None:
        raise ValueError("json-info.json version must be a release tag such as v3.11.3")
    return info


def load_bisheng_info(base_dir):
    info = load_document(base_dir, "bisheng-info.json", {"schema_version", "bisheng"})
    bisheng = info["bisheng"]
    if not isinstance(bisheng, dict) or set(bisheng) != {"x86_64", "aarch64"}:
        raise ValueError("bisheng must declare x86_64 and aarch64")
    for arch, entry in bisheng.items():
        if not isinstance(entry, dict) or set(entry) != {"file", "sha256"}:
            raise ValueError(f"bisheng {arch} requires file and sha256")
        filename, checksum = entry["file"], entry["sha256"]
        if not isinstance(filename, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.run", filename) is None:
            raise ValueError(f"bisheng {arch} needs a safe .run basename")
        if not isinstance(checksum, str) or re.fullmatch(r"[0-9a-fA-F]{64}", checksum) is None:
            raise ValueError(f"bisheng {arch} needs a full SHA-256")
    return info


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--hash", action="store_true", help="print the canonical LLVM commit")
    mode.add_argument("--patches", action="store_true", help="print absolute paths from the patch manifest")
    mode.add_argument("--json-version", action="store_true", help="print the nlohmann-json release tag")
    mode.add_argument("--validate", action="store_true", help="validate LLVM, JSON and Bisheng build inputs")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    try:
        if args.json_version:
            print(load_json_info(root)["version"])
            return
        if args.validate:
            load_json_info(root)
            load_bisheng_info(root)
        info = load_llvm_info(root)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Dependency metadata: {exc}\n")
    if args.validate:
        return
    if args.hash:
        print(info["llvm_hash"])
    else:
        for name in info["patches"]:
            print(root / "third_party/ascend/patch" / name)


if __name__ == "__main__":
    main()
