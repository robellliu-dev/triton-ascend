import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

import pytest

REPO = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("valid", [True, False])
def test_container_metadata_command_rejects_bad_json_before_building(tmp_path, valid):
    text = (REPO / ".github/workflows/build/wheels.Dockerfile").read_text(encoding="utf-8")
    command = re.search(r"(?m)^RUN /opt/python/\S+/bin/python3 (/project/cmake/dependencies.py .+)$", text).group(1)
    for name in ("dependencies.py", "llvm-info.json", "json-info.json", "bisheng-info.json"):
        target = tmp_path / "cmake" / name
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(REPO / "cmake" / name, target)
    shutil.copytree(REPO / "third_party/ascend/patch", tmp_path / "third_party/ascend/patch")
    if not valid:
        (tmp_path / "cmake/json-info.json").write_text(json.dumps({"schema_version": 1, "version": "bad"}))
    args = shlex.split(command.replace("/project/", tmp_path.as_posix() + "/", 1))
    result = subprocess.run([sys.executable, *args], capture_output=True, text=True)
    assert result.returncode == (0 if valid else 1), result.stderr
    if not valid:
        assert "json-info.json" in result.stderr
