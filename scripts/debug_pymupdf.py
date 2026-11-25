import re

import requests

H = {"User-Agent": "pip/25.3"}
for base in ["https://pypi.org/simple/pymupdf/", "https://pypi.tuna.tsinghua.edu.cn/simple/pymupdf/"]:
    try:
        r = requests.get(base, headers=H, timeout=20)
        links = re.findall(r'href="([^"#]+\.whl)(?:#[^"]*)?"', r.text)
        cands = [l for l in links if "cp310" in l and "win_amd64" in l]
        print(base, r.status_code, "links", len(links), "cands", len(cands))
        if cands:
            u = requests.compat.urljoin(r.url, cands[-1])
            rr = requests.get(u, headers=H, timeout=120, stream=True)
            print("  ", u[:100])
            print("  ", rr.status_code, rr.headers.get("Content-Type"), rr.headers.get("Content-Length"))
            print("  first bytes", next(rr.iter_content(8))[:8])
    except Exception as e:
        print(base, "FAIL", type(e).__name__, str(e)[:80])
