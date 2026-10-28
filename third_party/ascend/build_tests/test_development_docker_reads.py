import json
import os
from pathlib import Path
import re
import subprocess

import pytest

REPO = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("mode", ["default", "metadata-change", "override", "unknown", "duplicate"])
def test_development_docker_installs_its_selected_runtime(tmp_path, monkeypatch, mode):
    recipe = (REPO / "docker/Dockerfile").read_text(encoding="utf-8")
    match = re.search(r"RUN --mount=.*?python3 - <<'PY'\n(.*?)\nPY", recipe, re.DOTALL)
    assert match is not None, "Docker must read its runtime JSON before installing torch"
    data = json.loads((REPO / "cmake/ascend-runtime-info.json").read_text())
    group = next(group for group in data["runtimes"] if group["cann"] == "8.5.0")
    if mode == "metadata-change":
        group.update(torch="2.11.0", torch_npu="2.11.0.post1")
    elif mode == "duplicate":
        data["runtimes"].append(group)
    (tmp_path / "ascend-runtime-info.json").write_text(json.dumps(data))
    monkeypatch.setenv("CANN_BASE_IMAGE", "registry/cann:" + ("99.0.0" if mode == "unknown" else "8.5.0") + "-a3")
    monkeypatch.setenv("TORCH_INDEX_URL", "https://example.invalid/cpu")
    monkeypatch.setenv("TORCH_NPU_VERSION", "override-version" if mode == "override" else "")
    calls = []
    monkeypatch.setattr(subprocess, "check_call", lambda command: calls.append(command))
    script = match.group(1).replace("/opt/triton-metadata", tmp_path.as_posix())
    if mode in {"unknown", "duplicate"}:
        with pytest.raises(SystemExit):
            exec(script, {})
        assert calls == []
    else:
        exec(script, {})
        assert any("torch==" + group["torch"] + "+cpu" in command for command in calls)
        npu = os.environ["TORCH_NPU_VERSION"] or group["torch_npu"]
        assert any("torch-npu==" + npu in command for command in calls)
