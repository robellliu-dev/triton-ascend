import os
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap

import pytest

REPO = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("target", ["ubuntu", "almalinux"])
def test_metadata_reader_bootstraps_python_for_each_target(target, tmp_path):
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    bash = str(git_bash) if git_bash.is_file() else shutil.which("bash")
    if bash is None:
        pytest.skip("Bash is required to execute the LLVM workflow steps")
    workflow = (REPO / ".github/workflows/llvm-build.yml").read_text(encoding="utf-8")

    def step(name):
        start = workflow.index(f"    - name: {name}")
        end = workflow.index("\n    - name:", start + 1)
        block = workflow[start:end]
        if "if: matrix.config.target-os == 'ubuntu'" in block and target != "ubuntu":
            return ""
        return textwrap.dedent(block.split("      run: |\n", 1)[1]).replace("${{ matrix.config.target-os }}", target)

    # Simulate the observed container: Python becomes available only after the
    # package manager installs it. Execute the actual bootstrap and reader blocks.
    harness = r'''
set -eu
installed=
pip_installed=
sed() { :; }
apt-get() {
  case " $* " in
    *" install "*" python3 "*) installed=yes ;;
  esac
  case " $* " in
    *" install "*" python3-pip "*) pip_installed=yes ;;
  esac
}
command() {
  if [ "$*" = "-v python3" ]; then
    [ "$installed" = yes ]
  else
    builtin command "$@"
  fi
}
python3() {
  [ "$installed" = yes ]
  if [ "${1:-} ${2:-}" = "-m pip" ]; then
    [ "$pip_installed" = yes ]
    return
  fi
  "$TEST_PYTHON" "$@"
}
'''
    output = tmp_path / "github-env"
    script = harness + step("Config mirrors & install build tools") + "\n" + step("Fetch LLVM Commit Hash")
    script += "\n" + step("Install Prerequisites").splitlines()[0]
    subprocess.run([bash, "-c", script], cwd=REPO,
                   env={**os.environ, "TEST_PYTHON": Path(sys.executable).as_posix(), "GITHUB_ENV":
                        output.as_posix()}, check=True, capture_output=True, text=True)
    pin = (REPO / "cmake/llvm-hash.txt").read_text().strip()
    assert f"llvm_commit_hash={pin}\n" in output.read_text()
