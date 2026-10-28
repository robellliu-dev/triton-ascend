import json
import os
import platform
from dataclasses import dataclass
from typing import Optional
import sysconfig
import sys
from pathlib import Path


def get_base_dir():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))


def _get_cmake_dir():
    plat_name = sysconfig.get_platform()
    python_version = sysconfig.get_python_version()
    dir_name = f"cmake.{plat_name}-{sys.implementation.name}-{python_version}"
    return Path(get_base_dir()) / "build" / dir_name


def get_cmake_dir():
    cmake_dir = os.getenv("TRITON_BUILD_DIR", default=_get_cmake_dir())
    cmake_dir = Path(cmake_dir)
    cmake_dir.mkdir(parents=True, exist_ok=True)
    return cmake_dir


# Keep common build helpers here, following Triton and Intel. Ascend-specific
# artifact selection stays in third_party/ascend/build/setup_patch.py.
def check_env_flag(name: str, default: str = "") -> bool:
    return os.getenv(name, default).upper() in ["ON", "1", "YES", "TRUE", "Y"]


@dataclass
class Package:
    package: str
    name: str
    url: str
    include_flag: str
    lib_flag: str
    syspath_var_name: str
    sym_name: Optional[str] = None


def get_json_package_info():
    json_version_path = os.path.join(get_base_dir(), "cmake", "json-version.txt")
    with open(json_version_path, "r") as json_version_file:
        version = json_version_file.read().strip()
    url = f"https://github.com/nlohmann/json/releases/download/{version}/include.zip"
    return Package("json", "", url, "JSON_INCLUDE_DIR", "", "JSON_SYSPATH")


def is_linux_os(id):
    if os.path.exists("/etc/os-release"):
        with open("/etc/os-release", "r") as f:
            os_release_content = f.read()
            return f'ID="{id}"' in os_release_content
    return False


def get_llvm_system_suffix():
    system = platform.system()
    try:
        arch = {"x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}[platform.machine()]
    except KeyError:
        arch = platform.machine()
    if (env_system_suffix := os.environ.get("TRITON_LLVM_SYSTEM_SUFFIX", None)):
        system_suffix = env_system_suffix
    elif system == "Darwin":
        system_suffix = f"macos-{arch}"
    elif system == "Linux":
        if arch == 'arm64' and is_linux_os('almalinux'):
            system_suffix = 'almalinux-arm64'
        elif arch == 'arm64':
            system_suffix = 'ubuntu-arm64'
        elif arch == 'x64':
            vglibc = tuple(map(int, platform.libc_ver()[1].split('.')))
            vglibc = vglibc[0] * 100 + vglibc[1]
            if vglibc > 228:
                # Ubuntu 24 LTS (v2.39)
                # Ubuntu 22 LTS (v2.35)
                # Ubuntu 20 LTS (v2.31)
                system_suffix = "ubuntu-x64"
            else:
                # Manylinux_2.28 (v2.28)
                # AlmaLinux 8 (v2.28)
                system_suffix = "almalinux-x64"
        else:
            print(
                f"LLVM pre-compiled image is not available for {system}-{arch}. Proceeding with user-configured LLVM from source build."
            )
            return None
    else:
        print(
            f"LLVM pre-compiled image is not available for {system}-{arch}. Proceeding with user-configured LLVM from source build."
        )
        return None
    return system_suffix


def get_llvm_package_info():
    system_suffix = get_llvm_system_suffix()
    if system_suffix is None:
        return Package("llvm", "LLVM-C.lib", "", "LLVM_INCLUDE_DIRS", "LLVM_LIBRARY_DIR", "LLVM_SYSPATH")
    # use_assert_enabled_llvm = check_env_flag("TRITON_USE_ASSERT_ENABLED_LLVM", "False")
    # release_suffix = "assert" if use_assert_enabled_llvm else "release"
    llvm_info_path = os.path.join(get_base_dir(), "cmake", "llvm-info.json")
    with open(llvm_info_path, "r") as llvm_info_file:
        llvm_info = json.load(llvm_info_file)
    rev = llvm_info["llvm_hash"][:8]
    name = f"llvm-{rev}-{system_suffix}"
    # Create a stable symlink that doesn't include revision
    sym_name = f"llvm-{system_suffix}"
    url = f"https://oaitriton.blob.core.windows.net/public/llvm-builds/{name}.tar.gz"
    return Package("llvm", name, url, "LLVM_INCLUDE_DIRS", "LLVM_LIBRARY_DIR", "LLVM_SYSPATH", sym_name=sym_name)
