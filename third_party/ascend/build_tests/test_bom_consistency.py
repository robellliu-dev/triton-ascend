import importlib.util
import json
from pathlib import Path
import shutil

import pytest

REPO = Path(__file__).resolve().parents[3]


@pytest.fixture
def checker(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("bom_checker_test", REPO / "scripts/check_bom_consistency.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for relative in ["requirements.txt", "docker/Dockerfile", "docs/en/community/release_policy.md"]:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / relative, target)
    shutil.copytree(REPO / "third_party/ascend/deps", tmp_path / "third_party/ascend/deps")
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(module, "DEPS_DIR", tmp_path / "third_party/ascend/deps")
    return module


@pytest.mark.parametrize("mutation", ["missing-default", "duplicate", "planned", "docker-torch"])
def test_runtime_selection_fails_closed(checker, mutation):
    runtime = json.loads((checker.DEPS_DIR / "runtime.json").read_text(encoding="utf-8"))
    if mutation == "missing-default":
        runtime["default_cann"] = "42.0.0"
    elif mutation == "duplicate":
        runtime["runtimes"].append(dict(runtime["runtimes"][0]))
    elif mutation == "planned":
        runtime["default_cann"] = "9.2.0"
        requirements = checker.REPO_ROOT / "requirements.txt"
        requirements.write_text("torch-npu==2.10.0.post7\n", encoding="utf-8")
    else:
        docker = checker.REPO_ROOT / "docker/Dockerfile"
        docker.write_text(
            docker.read_text(encoding="utf-8").replace("torch==2.7.1+cpu", "torch==2.10.0+cpu"), encoding="utf-8")
    checker.check_static_pins(runtime)
    assert checker.errors


def test_requirements_bind_to_their_own_group(checker):
    runtime = json.loads((checker.DEPS_DIR / "runtime.json").read_text(encoding="utf-8"))
    runtime["runtimes"][0]["torch_npu"] = "unrelated-default-version"
    checker.check_static_pins(runtime)
    assert not checker.errors


def test_new_release_policy_drift_is_an_error(checker):
    runtime = json.loads((checker.DEPS_DIR / "runtime.json").read_text(encoding="utf-8"))
    policy = checker.REPO_ROOT / "docs/en/community/release_policy.md"
    policy.write_text(policy.read_text(encoding="utf-8").replace("`2.10.0`", "`2.11.0`"), encoding="utf-8")
    checker.check_release_policy(runtime)
    assert checker.errors


def test_only_the_recorded_reconciliation_is_a_warning(checker):
    runtime = json.loads((checker.DEPS_DIR / "runtime.json").read_text(encoding="utf-8"))
    checker.check_release_policy(runtime)
    assert not checker.errors
    assert checker.warnings


def test_unknown_checkout_prefix_stays_invalid(checker):
    assert not checker._glob_exists("wrong/requirements.txt")
    assert checker._glob_exists("pr/requirements.txt")
