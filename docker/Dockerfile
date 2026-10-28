# syntax=docker/dockerfile:1
ARG CANN_BASE_IMAGE=swr.cn-southwest-2.myhuaweicloud.com/base_image/ascend-ci/cann:8.5.0-a3-ubuntu22.04-py3.10
FROM ${CANN_BASE_IMAGE}
ARG CANN_BASE_IMAGE

# Select torch/torch-npu from the CANN group in cmake/ascend-runtime-info.json.
# Keep an explicit torch-npu override for custom development environments.
ARG TORCH_NPU_VERSION

ARG APTMIRROR=http://mirrors.huaweicloud.com
ARG PIP_INDEX_URL=https://repo.huaweicloud.com/repository/pypi/simple
ARG PIP_TRUSTED_HOST=repo.huaweicloud.com
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu

SHELL ["/bin/bash", "-c"]
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ="Asia/shanghai"

RUN sed -i "s|http://archive.ubuntu.com|${APTMIRROR}|g" /etc/apt/sources.list 2>/dev/null || true && \
    sed -i "s|http://security.ubuntu.com|${APTMIRROR}|g" /etc/apt/sources.list 2>/dev/null || true && \
    echo 'Acquire::Retries "5";' > /etc/apt/apt.conf.d/80-retries && \
    echo 'Acquire::http::Timeout "60";' >> /etc/apt/apt.conf.d/80-retries && \
    for i in 1 2 3; do \
      apt update && apt install --yes --no-install-recommends --no-install-suggests \
      bash \
      ca-certificates \
      clang-15 \
      clang-format \
      cmake \
      ccache \
      curl \
      git \
      gnupg \
      lld-15 \
      make \
      ninja-build \
      sudo \
      unzip \
      vim \
      wget \
      libzstd-dev \
      zlib1g-dev \
      && break \
      || { echo "apt attempt $i failed, retrying..."; sleep 10; [ $i -eq 3 ] && exit 1; }; \
    done && \
    apt clean && rm -rf /var/lib/apt/lists/* && \
    update-alternatives --install /usr/bin/clang clang /usr/bin/clang-15 100 && \
    update-alternatives --install /usr/bin/clang++ clang++ /usr/bin/clang++-15 100 && \
    update-alternatives --install /usr/bin/lld lld /usr/bin/lld-15 100 && \
    update-ca-certificates

RUN mkdir -p /root/.config/pip && \
    echo -e "[global]\nindex-url = ${PIP_INDEX_URL}\ntrusted-host = ${PIP_TRUSTED_HOST}" > /root/.config/pip/pip.conf

COPY requirements.txt requirements_dev.txt ./
COPY cmake/ascend-runtime-info.json /opt/triton-metadata/

# Install CPU torch first to avoid scanning the CPU index for every dependency.
RUN --mount=type=cache,target=/root/.cache/pip python3 - <<'PY'
import json
import os
from pathlib import Path
import re
import subprocess
import sys

runtime = json.loads(Path("/opt/triton-metadata/ascend-runtime-info.json").read_text())
cann = re.search(r"cann:(\d+\.\d+\.\d+)(?:-|$)", os.environ["CANN_BASE_IMAGE"])
groups = [group for group in runtime["runtimes"] if cann and group["cann"] == cann.group(1)]
if len(groups) != 1 or groups[0]["status"] in {"experimental", "planned"}:
    raise SystemExit("Development image must select one active CANN runtime group")
group = groups[0]
pip = [sys.executable, "-m", "pip", "install"]
subprocess.check_call(pip + ["--timeout", "600", "--find-links", os.environ["TORCH_INDEX_URL"] + "/torch/",
                            "torch==" + group["torch"] + "+cpu"])
subprocess.check_call(pip + ["--timeout", "300", "-r", "requirements_dev.txt"])
subprocess.check_call(pip + ["--timeout", "300", "-r", "requirements.txt"])
subprocess.check_call(pip + ["torch-npu==" + (os.environ.get("TORCH_NPU_VERSION") or group["torch_npu"])])
PY

WORKDIR /home/triton
