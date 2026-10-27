import ast
import json
import os
from pathlib import Path
import platform
import runpy
import shutil
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("revision", ["a" * 40, "b" * 40])
def test_upstream_package_url_reads_llvm_json(tmp_path, monkeypatch, revision):
    metadata = tmp_path / "cmake"
    metadata.mkdir()
    shutil.copyfile(REPO / "cmake/dependencies.py", metadata / "dependencies.py")
    (metadata / "llvm-info.json").write_text(json.dumps({"schema_version": 1, "llvm_hash": revision, "patches": []}))
    monkeypatch.setenv("TRITON_LLVM_SYSTEM_SUFFIX", "fixture-x64")
    tree = ast.parse((REPO / "setup.py").read_text(encoding="utf-8"))
    function = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == "get_llvm_package_info")
    namespace = {
        "Path": Path, "platform": platform, "os": os, "runpy": runpy, "get_base_dir": lambda: str(tmp_path), "Package":
        lambda *args, **kwargs: SimpleNamespace(name=args[1], url=args[2])
    }
    exec(compile(ast.Module(body=[function], type_ignores=[]), "setup.py", "exec"), namespace)
    package = namespace["get_llvm_package_info"]()
    assert package.name == f"llvm-{revision[:8]}-fixture-x64"
    assert package.url.endswith(f"/{package.name}.tar.gz")
