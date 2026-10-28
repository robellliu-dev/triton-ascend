import importlib.util
import json
import shutil
from pathlib import Path
import subprocess
import sys
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[3]
BUILD = REPO / "third_party" / "ascend" / "build"


@pytest.fixture
def load_info(monkeypatch):
    package = ModuleType("ascend_llvm_test")
    package.__path__ = [str(BUILD)]
    monkeypatch.setitem(sys.modules, package.__name__, package)
    spec = importlib.util.spec_from_file_location(f"{package.__name__}.setup_patch", BUILD / "setup_patch.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._load_llvm_bom


@pytest.fixture
def inputs(tmp_path):
    metadata = tmp_path / "cmake" / "llvm-info.json"
    metadata.parent.mkdir(parents=True)
    metadata.write_bytes((REPO / "cmake/llvm-info.json").read_bytes())
    shutil.copyfile(REPO / "cmake/dependencies.py", tmp_path / "cmake/dependencies.py")
    data = json.loads(metadata.read_text())
    data["llvm_hash"] = "a" * 40
    metadata.write_text(json.dumps(data))
    patches = tmp_path / "third_party" / "ascend" / "patch"
    patches.mkdir(parents=True)
    for name in data["patches"]:
        (patches / name).write_text("fixture patch")
    return tmp_path, metadata, metadata


def test_llvm_revision_has_one_authority(load_info, inputs):
    root, metadata, pin = inputs
    assert "llvm_hash_file" not in json.loads(metadata.read_text())
    assert load_info(root)["llvm_hash"] == "a" * 40
    data = json.loads(pin.read_text())
    data["llvm_hash"] = "b" * 40
    pin.write_text(json.dumps(data))
    assert load_info(root)["llvm_hash"] == "b" * 40


@pytest.mark.parametrize("value", ["", "main", "a" * 8, "x" * 40])
def test_invalid_canonical_revision_is_rejected(load_info, inputs, value):
    root, _, pin = inputs
    data = json.loads(pin.read_text())
    data["llvm_hash"] = value
    pin.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="40 hexadecimal"):
        load_info(root)


@pytest.mark.parametrize("change",
                         ["missing", "traversal", "duplicate", "extra", "schema", "copied-pin", "newline-name"])
def test_invalid_metadata_is_rejected(load_info, inputs, change):
    root, metadata, _ = inputs
    data = json.loads(metadata.read_text())
    if change == "missing":
        data.pop("llvm_hash", None)
    elif change == "traversal":
        data["llvm_hash_file"] = "../llvm-hash.txt"
    elif change == "duplicate":
        data["patches"] += data["patches"]
    elif change == "extra":
        (root / "third_party/ascend/patch/llvm_patch_extra.patch").touch()
    elif change == "schema":
        data["schema_version"] = True
    elif change == "newline-name":
        data["patches"] = ["llvm_patch_bad\nname.patch"]
    else:
        data["llvm_hash_file"] = "legacy-pin.txt"
    metadata.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load_info(root)


def test_duplicate_json_keys_are_rejected(load_info, inputs):
    root, metadata, _ = inputs
    metadata.write_text('{"schema_version": 1, "schema_version": 1}')
    with pytest.raises(ValueError, match="duplicate"):
        load_info(root)


def test_cli_reports_the_same_pin_and_real_patch_paths():
    helper = REPO / "cmake/dependencies.py"
    pin = subprocess.run([sys.executable, str(helper), "--hash"], capture_output=True, text=True, check=True)
    assert pin.stdout.strip() == json.loads((REPO / "cmake/llvm-info.json").read_text())["llvm_hash"]
    patches = subprocess.run([sys.executable, str(helper), "--patches"], capture_output=True, text=True, check=True)
    assert patches.stdout.splitlines()
    assert all(Path(path).is_file() for path in patches.stdout.splitlines())
