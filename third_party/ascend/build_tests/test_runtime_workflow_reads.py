import json
from pathlib import Path
import re
import subprocess
import sys
import textwrap

import pytest

REPO = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("workflow", ["llvm-build.yml", "wheels.yml", "build-docker-image.yml"])
@pytest.mark.parametrize("selection", ["9.0.0", "missing", "9.2.0", None, [], "duplicate"])
def test_real_workflow_reader_rejects_unusable_defaults(workflow, selection, tmp_path):
    text = (REPO / ".github/workflows" / workflow).read_text(encoding="utf-8")
    match = re.search(r"cann=\$\(python3 - <<'PY'\n(.*?)\n[ ]*PY\n", text, re.S)
    assert match is not None
    script = textwrap.dedent(match.group(1))
    metadata = tmp_path / "cmake"
    metadata.mkdir()
    data = json.loads((REPO / "cmake/ascend-runtime-info.json").read_text())
    if selection == "duplicate":
        data["runtimes"].append(next(group for group in data["runtimes"] if group["cann"] == data["default_cann"]))
    else:
        data["default_cann"] = selection
    (metadata / "ascend-runtime-info.json").write_text(json.dumps(data))
    result = subprocess.run([sys.executable, "-c", script], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == (0 if selection == "9.0.0" else 1), result.stderr
    assert result.stdout == ("9.0.0\n" if selection == "9.0.0" else "")
