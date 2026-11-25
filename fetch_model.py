"""Download a faster-whisper model from the hf-mirror endpoint."""
import sys
import time
from pathlib import Path

import requests

BASE = "https://hf-mirror.com/{repo}/resolve/main/{fname}"
HEADERS = {"User-Agent": "Mozilla/5.0"}


def fetch(repo, dest, files):
    dest.mkdir(parents=True, exist_ok=True)
    for fname in files:
        out = dest / fname
        if out.exists() and out.stat().st_size > 1024:
            print(f"[SKIP] {fname} {out.stat().st_size / 1e6:.1f}MB")
            continue
        url = BASE.format(repo=repo, fname=fname)
        t = time.time()
        try:
            with requests.get(url, headers=HEADERS, stream=True, timeout=120, allow_redirects=True) as r:
                r.raise_for_status()
                tmp = out.with_suffix(out.suffix + ".part")
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
                tmp.replace(out)
            print(f"[DL] {fname} {out.stat().st_size / 1e6:.1f}MB {time.time() - t:.1f}s")
        except Exception as e:
            print(f"[FAIL] {fname}: {type(e).__name__} {str(e)[:80]}")


if __name__ == "__main__":
    repo = sys.argv[1]
    dest = Path(sys.argv[2])
    fetch(repo, dest, ["config.json", "model.bin", "tokenizer.json", "vocabulary.txt", "vocabulary.json"])
