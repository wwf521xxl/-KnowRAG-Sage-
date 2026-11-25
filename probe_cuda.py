"""List NVIDIA redist index entries for cuBLAS / cuDNN on Windows."""
import re

import requests

for url in [
    "https://developer.download.nvidia.com/compute/cublas/redist/",
    "https://developer.download.nvidia.com/compute/cuda/redist/",
]:
    r = requests.get(url, timeout=20)
    links = re.findall(r'href=["\']([^"\']+)["\']', r.text)
    rel = [l for l in links if not l.startswith("/") and "style" not in l]
    print(url)
    for l in rel[:30]:
        print("  ", l)
    print()
