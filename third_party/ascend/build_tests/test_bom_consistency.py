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
    shutil.copytree(REPO / "cmake", tmp_path / "cmake")
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(module, "DEPS_DIR", tmp_path / "cmake")
    return module


@pytest.mark.parametrize("mutation", ["missing-default", "duplicate", "planned"])
def test_runtime_selection_fails_closed(checker, mutation):
    runtime = json.loads((checker.DEPS_DIR / "ascend-runtime-info.json").read_text(encoding="utf-8"))
    if mutation == "missing-default":
        runtime["default_cann"] = "42.0.0"
    elif mutation == "duplicate":
        runtime["runtimes"].append(dict(runtime["runtimes"][0]))
    elif mutation == "planned":
        runtime["runtimes"][-1]["status"] = "planned"
        runtime["default_cann"] = "9.2.0"
        requirements = checker.REPO_ROOT / "requirements.txt"
        requirements.write_text("torch-npu==2.10.0.post7\n", encoding="utf-8")
    checker.check_static_pins(runtime)
    assert checker.errors


def test_requirements_bind_to_their_own_group(checker):
    runtime = json.loads((checker.DEPS_DIR / "ascend-runtime-info.json").read_text(encoding="utf-8"))
    runtime["runtimes"][0]["torch_npu"] = "unrelated-default-version"
    checker.check_static_pins(runtime)
    assert not checker.errors


def test_new_release_policy_drift_is_an_error(checker):
    runtime = json.loads((checker.DEPS_DIR / "ascend-runtime-info.json").read_text(encoding="utf-8"))
    policy = checker.REPO_ROOT / "docs/en/community/release_policy.md"
    policy.write_text(policy.read_text(encoding="utf-8").replace("`2.10.0`", "`2.11.0`"), encoding="utf-8")
    checker.check_release_policy(runtime)
    assert checker.errors


def test_only_the_recorded_reconciliation_is_a_warning(checker):
    runtime = json.loads((checker.DEPS_DIR / "ascend-runtime-info.json").read_text(encoding="utf-8"))
    checker.check_release_policy(runtime)
    assert not checker.errors
    assert checker.warnings


def test_unknown_checkout_prefix_stays_invalid(checker):
    assert not checker._glob_exists("wrong/requirements.txt")
    assert checker._glob_exists("pr/requirements.txt")


@pytest.mark.parametrize("mutation", ["copied-json", "invalid-checksum", "unsafe-file", "missing-arch"])
def test_toolchain_rejects_invalid_inputs(checker, mutation):
    path = checker.DEPS_DIR / "bisheng-info.json"
    data = json.loads(path.read_text())
    if mutation == "copied-json":
        data["json"] = "v3.11.3"
    elif mutation == "invalid-checksum":
        data["bisheng"]["x86_64"]["sha256"] = "bad"
    elif mutation == "unsafe-file":
        data["bisheng"]["x86_64"]["file"] = "../outside.run"
    else:
        del data["bisheng"]["aarch64"]
    path.write_text(json.dumps(data))
    checker.check_toolchain()
    assert checker.errors


@pytest.mark.parametrize("version", ["v3.11.3", "main", "v3.11.3\nv3.12.0"])
def test_audit_validates_the_upstream_json_text_pin(checker, version):
    (checker.DEPS_DIR / "json-version.txt").write_text(version)
    checker.check_toolchain()
    assert bool(checker.errors) is (version != "v3.11.3")


@pytest.mark.parametrize("mutation",
                         ["unknown-field", "unknown-status", "not-a-list", "not-a-group", "missing-consumers"])
def test_malformed_runtime_is_reported_without_a_traceback(checker, mutation):
    data = json.loads((checker.DEPS_DIR / "ascend-runtime-info.json").read_text())
    if mutation == "unknown-field":
        data["default_can"] = data["default_cann"]
    elif mutation == "unknown-status":
        data["runtimes"][0]["status"] = "typo"
    elif mutation == "not-a-list":
        data["runtimes"] = {}
    elif mutation == "not-a-group":
        data["runtimes"] = [None]
    else:
        del data["consumers"]
    assert not checker._runtime_groups(data)
    assert checker.errors


@pytest.mark.parametrize("contents", ['{"schema_version":true}', '{"schema_version":1,"schema_version":1}', '[]'])
def test_json_loader_rejects_bad_envelopes(checker, contents):
    path = checker.DEPS_DIR / "ascend-runtime-info.json"
    path.write_text(contents)
    with pytest.raises(ValueError):
        checker._load_json(path)


@pytest.mark.parametrize("selection", ["9.0.0", "missing", "9.2.0", None, []])
def test_audit_accepts_only_a_valid_active_default(checker, selection):
    path = checker.DEPS_DIR / "ascend-runtime-info.json"
    data = json.loads(path.read_text())
    data["default_cann"] = selection
    path.write_text(json.dumps(data))
    if selection == "9.0.0":
        assert checker._runtime_groups(data)
        assert not checker.errors
    else:
        assert not checker._runtime_groups(data)
        assert checker.errors


def test_beta_exception_does_not_allow_an_unrelated_container(checker, monkeypatch):
    workflows = checker.REPO_ROOT / ".github/workflows"
    workflows.mkdir(parents=True)
    (workflows / "unrelated.yml").write_text("image: registry/triton:9.2.0-beta.2-a3\n")
    monkeypatch.setattr(checker, "WORKFLOWS_DIR", workflows)
    runtime = json.loads((checker.DEPS_DIR / "ascend-runtime-info.json").read_text())
    checker.check_workflows(runtime)
    assert checker.errors


def test_uppercase_workflow_pin_cannot_select_a_planned_runtime(checker, monkeypatch):
    workflows = checker.REPO_ROOT / ".github/workflows"
    workflows.mkdir(parents=True)
    (workflows / "release.yml").write_text('env:\n  CANN_VERSION: "9.2.0"\n')
    monkeypatch.setattr(checker, "WORKFLOWS_DIR", workflows)
    runtime = json.loads((checker.DEPS_DIR / "ascend-runtime-info.json").read_text())
    runtime["runtimes"][-1]["status"] = "planned"
    checker.check_workflows(runtime)
    assert checker.errors


def test_observed_nightly_stack_is_recorded_without_becoming_the_default(checker):
    info = json.loads((checker.DEPS_DIR / "release-image-info.json").read_text())
    runtime = json.loads((checker.DEPS_DIR / "ascend-runtime-info.json").read_text())
    group = next(group for group in runtime["runtimes"] if group["cann"] == "9.2.0")
    assert group["status"] == "experimental"
    assert group["cann"] == info["cann"]
    assert runtime["default_cann"] != group["cann"]


@pytest.mark.parametrize("mutation",
                         ["valid", "bad-source", "bad-llvm", "unsafe-patch", "bad-checksum", "unknown-runtime"])
def test_release_image_manifest_is_a_separate_immutable_release_binding(checker, mutation):
    path = checker.DEPS_DIR / "release-image-info.json"
    info = json.loads(path.read_text())
    if mutation == "bad-source":
        info["source_hash"] = "main"
    elif mutation == "bad-llvm":
        info["llvm_hash"] = "short"
    elif mutation == "unsafe-patch":
        info["patches"][0]["file"] = "../outside.patch"
    elif mutation == "bad-checksum":
        info["patches"][0]["sha256"] = "not-a-digest"
    elif mutation == "unknown-runtime":
        info["cann"] = "99.0.0"
    path.write_text(json.dumps(info))
    runtime = json.loads((checker.DEPS_DIR / "ascend-runtime-info.json").read_text())
    checker.check_release_image(runtime)
    assert bool(checker.errors) == (mutation != "valid")


@pytest.mark.parametrize("field", ["llvm", "patch"])
def test_release_policy_cannot_silently_drift_llvm_or_patch(checker, field):
    path = checker.REPO_ROOT / "docs/en/community/release_policy.md"
    text = path.read_text(encoding="utf-8")
    text = text.replace("f6ded0b", "abcdef0") if field == "llvm" else text.replace("llvm_patch_f6ded0b.patch",
                                                                                   "llvm_patch_bad.patch")
    path.write_text(text, encoding="utf-8")
    runtime = json.loads((checker.DEPS_DIR / "ascend-runtime-info.json").read_text())
    checker.check_release_policy(runtime)
    assert checker.errors
