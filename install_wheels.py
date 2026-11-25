"""Download wheels from the Tsinghua mirror and unzip them into the venv's site-packages.

Bypasses pip's resolver/install stalls by fetching wheels directly.
"""
import re
import sys
import time
import zipfile
from pathlib import Path

import requests

INDEX = "https://pypi.tuna.tsinghua.edu.cn/simple/{name}/"
HEADERS = {
    "User-Agent": "pip/25.3 (python 3.10)",
    "Referer": "https://pypi.tuna.tsinghua.edu.cn/simple/",
}
SITE = Path(sys.argv[1]).resolve()
WHEELS = Path(sys.argv[2]).resolve()
WHEELS.mkdir(parents=True, exist_ok=True)

PKGS = [
    ("faster-whisper", "1.1.1"),
    ("ctranslate2", "4.9.0"),
    ("tokenizers", "0.23.3"),
    ("numpy", "2.2.6"),
    ("av", "17.1.0"),
    ("tqdm", "4.70.1"),
    ("PyYAML", "6.0.3"),
    ("onnxruntime", "1.23.2"),
    ("coloredlogs", "15.0.1"),
    ("flatbuffers", "25.12.19"),
    ("protobuf", "6.33.2"),
    ("sympy", "1.14.0"),
    ("mpmath", "1.3.0"),
    ("packaging", "25.0"),
    ("filelock", "3.20.1"),
    ("fsspec", "2025.12.0"),
    ("typing-extensions", "4.15.0"),
    ("httpx", "0.28.1"),
    ("httpcore", "1.0.9"),
    ("h11", "0.16.0"),
    ("anyio", "4.12.0"),
    ("sniffio", "1.3.1"),
    ("idna", "3.11"),
    ("certifi", "2025.11.12"),
    ("requests", "2.32.5"),
    ("urllib3", "2.6.2"),
    ("charset-normalizer", "3.4.4"),
    ("humanfriendly", "10.0"),
    ("pyreadline3", "3.5.4"),
    ("huggingface-hub", "0.36.0"),
]


def pick(html, version):
    links = re.findall(r'href="([^"#]+\.whl)(?:#[^"]*)?"', html)
    cands = [
        l for l in links
        if f"-{version}-" in l.rsplit("/", 1)[-1] or f"-{version}." in l.rsplit("/", 1)[-1]
    ]
    prefs = ["cp310-cp310-win_amd64", "cp310-abi3-win_amd64", "py3-none-any", "py2.py3-none-any"]
    for p in prefs:
        for l in cands:
            if p in l:
                return l
    return cands[0] if cands else None


def main():
    total = 0
    for name, version in PKGS:
        r = requests.get(INDEX.format(name=name), timeout=30, headers=HEADERS)
        r.raise_for_status()
        url = pick(r.text, version)
        if not url:
            print(f"[MISS] {name}=={version}")
            continue
        url = requests.compat.urljoin(r.url, url)
        fname = url.rsplit("/", 1)[-1]
        dest = WHEELS / fname
        if not dest.exists() or dest.stat().st_size < 1000:
            t = time.time()
            with requests.get(url, timeout=300, stream=True, headers=HEADERS) as resp:
                resp.raise_for_status()
                with open(dest, "wb") as f:
                    for chunk in resp.iter_content(1 << 20):
                        f.write(chunk)
            print(f"[DL] {fname} {dest.stat().st_size / 1e6:.1f}MB {time.time() - t:.1f}s")
        else:
            print(f"[SKIP] {fname}")
        with zipfile.ZipFile(dest) as z:
            z.extractall(SITE)
        total += dest.stat().st_size
    print(f"done, total {total / 1e6:.0f}MB")


if __name__ == "__main__":
    main()
