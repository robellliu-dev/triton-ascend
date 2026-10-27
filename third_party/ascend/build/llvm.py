"""Resolve Ascend LLVM metadata without importing the build backend or Triton."""

import argparse
import json
from pathlib import Path
import re


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate LLVM metadata key: {key}")
        result[key] = value
    return result


def load_llvm_info(base_dir):
    root = Path(base_dir).resolve()
    metadata = root / "third_party/ascend/deps/llvm-info.json"
    with metadata.open(encoding="utf-8") as stream:
        info = json.load(stream, object_pairs_hook=_unique_keys)
    fields = {"schema_version", "llvm_hash_file", "patches"}
    if not isinstance(info, dict) or set(info) != fields:
        raise ValueError(f"{metadata} must contain exactly {sorted(fields)}; do not duplicate llvm_hash")
    if type(info["schema_version"]) is not int or info["schema_version"] != 1:
        raise ValueError(f"{metadata} requires schema_version 1")
    if info["llvm_hash_file"] != "cmake/llvm-hash.txt":
        raise ValueError("llvm_hash_file must reference cmake/llvm-hash.txt")
    revision = (root / info["llvm_hash_file"]).read_text(encoding="utf-8").strip()
    if re.fullmatch(r"[0-9a-fA-F]{40}", revision) is None:
        raise ValueError("cmake/llvm-hash.txt must contain exactly 40 hexadecimal characters")
    patches = info["patches"]
    if (not isinstance(patches, list) or any(not isinstance(name, str) or not name.startswith("llvm_patch_")
                                             or not name.endswith(".patch") or "/" in name or "\\" in name
                                             for name in patches)):
        raise ValueError("patches must list LLVM patch basenames")
    if patches != sorted(set(patches)):
        raise ValueError("patches must be unique and sorted to preserve the existing patch order")
    patch_dir = root / "third_party/ascend/patch"
    actual = sorted(path.name for path in patch_dir.glob("llvm_patch_*.patch") if path.is_file())
    if patches != actual:
        raise ValueError(f"LLVM patch manifest mismatch: declared {patches}, found {actual}")
    # Derived in memory, never copied into another hand-maintained pin file.
    return {**info, "llvm_hash": revision}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--hash", action="store_true", help="print the canonical LLVM commit")
    mode.add_argument("--patches", action="store_true", help="print absolute paths from the patch manifest")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    try:
        info = load_llvm_info(root)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"LLVM dependency metadata: {exc}\n")
    if args.hash:
        print(info["llvm_hash"])
    else:
        for name in info["patches"]:
            print(root / "third_party/ascend/patch" / name)


if __name__ == "__main__":
    main()
