import ast
from pathlib import Path
import re
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("version", ["v3.11.3", "v3.12.0"])
def test_json_download_follows_the_canonical_version(version, tmp_path):
    pin = tmp_path / "cmake/json-version.txt"
    pin.parent.mkdir()
    pin.write_text(version + "\n")
    tree = ast.parse((REPO / "setup.py").read_text(encoding="utf-8"))
    function = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == "get_json_package_info")
    namespace = {
        "Path": Path, "re": re, "get_base_dir": lambda: str(tmp_path), "Package":
        lambda *args: SimpleNamespace(url=args[2])
    }
    exec(compile(ast.Module(body=[function], type_ignores=[]), "setup.py", "exec"), namespace)
    assert namespace["get_json_package_info"](
    ).url == f"https://github.com/nlohmann/json/releases/download/{version}/include.zip"
