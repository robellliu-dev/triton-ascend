import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import textwrap

import pytest

REPO = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("event,ref", [("push", "release/3.6.0"), ("workflow_dispatch", "release/3.2.2"),
                                       ("schedule", "main"), ("pull_request", "123/merge")])
def test_wheel_matrix_tracks_the_requested_source(tmp_path, event, ref):
    text = (REPO / ".github/workflows/wheels.yml").read_text(encoding="utf-8")
    match = re.search(r"(?m)^        shell: python\n        run: \|\n((?:          .*\n|\n)+)", text)
    script = textwrap.dedent(match.group(1))
    (tmp_path / "cmake").mkdir()
    shutil.copyfile(REPO / "cmake/ascend-runtime-info.json", tmp_path / "cmake/ascend-runtime-info.json")
    output = tmp_path / "output"
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=tmp_path,
        env={**os.environ, "GITHUB_EVENT_NAME": event, "GITHUB_REF_NAME": ref, "GITHUB_OUTPUT":
             str(output)}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    values = dict(line.split("=", 1) for line in output.read_text().splitlines())
    assert "branch" in values, "Release triggers must not silently build main"
    branch = json.loads(values["branch"])[0]
    expected = "main" if event in {"schedule", "pull_request"} else ref
    assert branch["ref"] == expected
    assert branch["tag"] == expected.replace("/", "-")
    assert text.count('branch: ${{ fromJSON(needs.deps.outputs.branch) }}') == 2


@pytest.mark.parametrize("mode", ["metadata", "override", "invalid-json"])
def test_npuir_resolution_uses_metadata_without_changing_the_destination(tmp_path, mode):
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    bash = str(git_bash) if git_bash.is_file() else shutil.which("bash")
    if bash is None:
        pytest.skip("Bash is required")
    script = tmp_path / ".github/workflows/build/fetch-npuir-stable.sh"
    script.parent.mkdir(parents=True)
    shutil.copyfile(REPO / ".github/workflows/build/fetch-npuir-stable.sh", script)
    metadata = tmp_path / "cmake/npuir-info.json"
    metadata.parent.mkdir()
    metadata.write_text("{bad" if mode == "invalid-json" else json.dumps(
        {"schema_version": 1, "repository": "https://example.invalid/npuir.git", "branch": "candidate"}))
    sentinel = tmp_path / "third_party/ascend/AscendNPU-IR/keep"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_text("existing source")
    env = {**os.environ, "NPUIR_PYTHON": Path(sys.executable).as_posix()}
    env.pop("NPUIR_REPO_URL", None)
    env.pop("NPUIR_REPO_BRANCH", None)
    if mode == "override":
        env.update(NPUIR_REPO_URL="https://override.invalid/npuir.git", NPUIR_REPO_BRANCH="release")
    wrapper = 'git() { printf "%s\\n" "$*" >&2; printf "%s\\tref\\n" ' + "a" * 40 + '; }; export -f git; '
    result = subprocess.run([bash, "-c", wrapper + 'bash "$1" --resolve-only', "test",
                             script.as_posix()], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=10)
    assert sentinel.read_text() == "existing source"
    if mode == "invalid-json":
        assert result.returncode != 0
        assert "ls-remote" not in result.stderr
    else:
        assert result.returncode == 0, result.stderr
        assert result.stdout == "a" * 40 + "\n"
        remote, branch = ("override.invalid", "release") if mode == "override" else ("example.invalid", "candidate")
        assert f"ls-remote https://{remote}/npuir.git refs/heads/{branch}" in result.stderr


@pytest.mark.parametrize("branch", ["main", "release/3.6.0"])
def test_runner_query_uses_the_current_branch_and_workflow_file(tmp_path, branch):
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    bash = str(git_bash) if git_bash.is_file() else shutil.which("bash")
    if bash is None:
        pytest.skip("Bash is required")
    text = (REPO / ".github/workflows/runner-preparation.yml").read_text(encoding="utf-8")
    step = text.split("      - name: Detect if enough time has passed since last post-submit run", 1)[1]
    match = re.search(r"        run: \|\n((?:          .*\n|\n)+)", step)
    script = textwrap.dedent(match.group(1))
    # Supply stand-ins only for the transport/parser; execute the actual query construction.
    prefix = 'curl() { printf "%s\\n" "$@" >&2; }; jq() { printf null; }; '
    result = subprocess.run(
        [bash, "-c", prefix + script], cwd=tmp_path, env={
            **os.environ, "GITHUB_TOKEN": "test-token", "GITHUB_REPOSITORY": "example/triton", "GITHUB_REF_NAME":
            branch, "GITHUB_API_URL": "https://api.github.com", "GITHUB_ENV": (tmp_path / "env").as_posix()
        }, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "/actions/workflows/ci.yml/runs" in result.stderr
    assert "branch=" + branch in result.stderr
