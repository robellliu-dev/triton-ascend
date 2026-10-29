import os
import json
from pathlib import Path
import shutil
import subprocess
import textwrap

import pytest

REPO = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("target", ["ubuntu", "almalinux"])
def test_metadata_reader_bootstraps_tools_for_each_target(target, tmp_path):
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    bash = str(git_bash) if git_bash.is_file() else shutil.which("bash")
    if bash is None or shutil.which("jq") is None:
        pytest.skip("Bash and jq are required to execute the LLVM workflow steps")
    workflow = (REPO / ".github/workflows/llvm-build.yml").read_text(encoding="utf-8")

    def step(name):
        start = workflow.index(f"    - name: {name}")
        end = workflow.index("\n    - name:", start + 1)
        block = workflow[start:end]
        if "if: matrix.config.target-os == 'ubuntu'" in block and target != "ubuntu":
            return ""
        return textwrap.dedent(block.split("      run: |\n", 1)[1]).replace("${{ matrix.config.target-os }}", target)

    # Both metadata and build tools must be installed in the actual container.
    harness = r'''
set -eu
installed=
pip_installed=
jq_installed=
sed() { :; }
apt-get() {
  case " $* " in
    *" install "*" python3 "*) installed=yes ;;
  esac
  case " $* " in
    *" install "*" python3-pip "*) pip_installed=yes ;;
  esac
  case " $* " in
    *" install "*" jq "*) jq_installed=yes ;;
  esac
}
jq() {
  [ "$jq_installed" = yes ] || return 1
  command jq "$@"
}
python3() {
  [ "$installed" = yes ]
  if [ "${1:-} ${2:-}" = "-m pip" ]; then
    [ "$pip_installed" = yes ]
    return
  fi
  echo "Metadata must be read with jq" >&2
  return 1
}
'''
    output = tmp_path / "github-env"
    script = harness + step("Config mirrors & install build tools") + "\n" + step("Fetch LLVM Commit Hash")
    script += "\n" + step("Install Prerequisites").splitlines()[0]
    subprocess.run([bash, "-c", script], cwd=REPO, env={**os.environ, "GITHUB_ENV": output.as_posix()}, check=True,
                   capture_output=True, text=True)
    pin = json.loads((REPO / "cmake/llvm-info.json").read_text())["llvm_hash"]
    assert f"llvm_commit_hash={pin}\n" in output.read_text()


@pytest.mark.parametrize("value", [None, "", "main", 123, "a" * 39])
def test_invalid_llvm_pin_does_not_publish_environment_values(tmp_path, value):
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    bash = str(git_bash) if git_bash.is_file() else shutil.which("bash")
    if bash is None or shutil.which("jq") is None:
        pytest.skip("Bash and jq are required")
    workflow = (REPO / ".github/workflows/llvm-build.yml").read_text(encoding="utf-8")
    block = workflow.split("    - name: Fetch LLVM Commit Hash\n", 1)[1].split("\n    - name:", 1)[0]
    script = textwrap.dedent(block.split("      run: |\n", 1)[1])
    (tmp_path / "cmake").mkdir()
    (tmp_path / "cmake/llvm-info.json").write_text(json.dumps({"llvm_hash": value}))
    output = tmp_path / "env"
    result = subprocess.run([bash, "-e", "-o", "pipefail", "-c", script], cwd=tmp_path,
                            env={**os.environ, "GITHUB_ENV": output.as_posix()}, capture_output=True, text=True)
    assert result.returncode != 0
    assert not output.exists()
