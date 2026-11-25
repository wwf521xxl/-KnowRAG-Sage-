"""Install a single pure-python wheel from the mirror (no dependency resolution)."""
import re
import sys
import zipfile
from pathlib import Path

import requests

H = {"User-Agent": "pip/25.3", "Referer": "https://pypi.tuna.tsinghua.edu.cn/simple/"}


def main(name, site, wheels):
    site, wheels = Path(site), Path(wheels)
    r = requests.get(f"https://pypi.tuna.tsinghua.edu.cn/simple/{name}/", headers=H, timeout=30)
    r.raise_for_status()
    links = re.findall(r'href="([^"#]+\.whl)(?:#[^"]*)?"', r.text)
    cands = [l for l in links if "py2.py3-none-any" in l or "py3-none-any" in l]
    if not cands:
        print("no pure-python wheel; links:", len(links))
        return
    url = requests.compat.urljoin(r.url, cands[-1])
    data = requests.get(url, headers=H, timeout=120).content
    dest = wheels / url.rsplit("/", 1)[-1]
    dest.write_bytes(data)
    with zipfile.ZipFile(dest) as z:
        z.extractall(site)
    print("installed", dest.name, len(data))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
