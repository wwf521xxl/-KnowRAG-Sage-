"""Find and download the Windows cuBLAS + cuDNN redistributables."""
import json
import re
import sys
import zipfile
from pathlib import Path

import requests

DEST = Path(r"D:\知识库问答系统\cuda")
H = {"User-Agent": "Mozilla/5.0"}


def cublas_windows(version="12.9.2"):
    base = "https://developer.download.nvidia.com/compute/cublas/redist/"
    meta = json.loads(requests.get(f"{base}redistrib_{version}.json", timeout=30).text)
    for item in meta.get("cublas", []):
        if "windows" in item.get("platform", ""):
            return item["relative_path"]
    return None


def cudnn_windows():
    idx = requests.get(
        "https://developer.download.nvidia.com/compute/cudnn/redist/cudnn/windows-x86_64/",
        timeout=30,
    ).text
    zips = sorted(set(re.findall(r'(cudnn-windows-x86_64-9\.[0-9.]+_cuda12-archive\.zip)', idx)))
    return "https://developer.download.nvidia.com/compute/cudnn/redist/cudnn/windows-x86_64/" + zips[-1]


def download(url, out):
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and out.stat().st_size > 1_000_000:
        print("skip", out.name)
        return
    with requests.get(url, headers=H, stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(out, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    print("downloaded", out.name, round(out.stat().st_size / 1e6, 1), "MB")


if __name__ == "__main__":
    DEST.mkdir(parents=True, exist_ok=True)
    cu = cublas_windows()
    print("cublas:", cu)
    if cu:
        url = "https://developer.download.nvidia.com/compute/cublas/redist/" + cu
        out = DEST / Path(cu).name
        download(url, out)
        with zipfile.ZipFile(out) as z:
            z.extractall(DEST / "cublas")
    cd = cudnn_windows()
    print("cudnn:", cd)
    out = DEST / Path(cd).name
    download(cd, out)
    with zipfile.ZipFile(out) as z:
        z.extractall(DEST / "cudnn")
    print("done")
