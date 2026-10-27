from pathlib import Path
import json
import shutil
import subprocess

import pytest

REPO = Path(__file__).resolve().parents[3]


def test_dependency_metadata_lives_in_cmake_without_text_mirrors():
    assert not (REPO / "third_party/ascend/deps").exists()
    for name in ("llvm-info.json", "json-info.json", "bisheng-info.json", "ascend-runtime-info.json"):
        assert (REPO / "cmake" / name).is_file()
    for name in ("llvm-hash.txt", "json-version.txt", "bisheng-version.txt"):
        assert not (REPO / "cmake" / name).exists()


@pytest.mark.parametrize("revision", ["a" * 40, "wrong"])
def test_native_cmake_reader_uses_json_and_rejects_bad_revisions(tmp_path, revision):
    cmake = shutil.which("cmake")
    if cmake is None:
        pytest.skip("CMake is required for the native JSON reader test")
    for name in ("TritonDependencies.cmake", "json-info.json"):
        shutil.copyfile(REPO / "cmake" / name, tmp_path / name)
    (tmp_path / "llvm-info.json").write_text(json.dumps({"schema_version": 1, "llvm_hash": revision, "patches": []}))
    script = tmp_path / "check.cmake"
    script.write_text(
        'include("${CMAKE_CURRENT_LIST_DIR}/TritonDependencies.cmake")\n'
        'file(WRITE "${CMAKE_CURRENT_LIST_DIR}/resolved.txt" "${TRITON_LLVM_REVISION};${TRITON_JSON_VERSION}")\n')
    result = subprocess.run([cmake, "-P", str(script)], capture_output=True, text=True)
    if revision == "wrong":
        assert result.returncode != 0
        assert "llvm_hash" in result.stderr
    else:
        assert result.returncode == 0, result.stderr
        assert (tmp_path / "resolved.txt").read_text() == revision + ";v3.11.3"
