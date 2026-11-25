"""Install a Windows binary wheel directly (pip resolver hangs on this machine)."""
import re
import sys
import zipfile
from pathlib import Path

import requests

H = {"User-Agent": "pip/25.3"}
INDEX = "https://pypi.org/simple/{pkg}/"


def main(pkg, site, wheels):
    site, wheels = Path(site), Path(wheels)
    wheels.mkdir(parents=True, exist_ok=True)
    r = requests.get(INDEX.format(pkg=pkg), headers=H, timeout=30)
    r.raise_for_status()
    links = re.findall(r'href="([^"#]+\.whl)(?:#[^"]*)?"', r.text)
    cands = [l for l in links if "cp310-cp310-win_amd64" in l or "cp310-abi3-win_amd64" in l]
    if not cands:
        cands = [l for l in links if "py3-none-any" in l or "py2.py3-none-any" in l]
    if not cands:
        print("no suitable wheel; sample:", links[:3])
        return
    url = requests.compat.urljoin(r.url, cands[-1])
    dest = wheels / url.rsplit("/", 1)[-1]
    dest.write_bytes(requests.get(url, headers=H, timeout=180).content)
    with zipfile.ZipFile(dest) as z:
        z.extractall(site)
    print("installed", dest.name, dest.stat().st_size)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
