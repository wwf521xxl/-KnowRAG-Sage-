"""Download the BGE small Chinese ONNX embedding model from hf-mirror."""
import sys
import time
from pathlib import Path

import requests

BASE = "https://hf-mirror.com/onnx-community/bge-small-zh-v1.5-ONNX/resolve/main/"
DEST = Path(r"D:\知识库问答系统\models\bge-small-zh-onnx")
FILES = [
    ("config.json", "config.json"),
    ("tokenizer.json", "tokenizer.json"),
    ("tokenizer_config.json", "tokenizer_config.json"),
    ("onnx/model_quantized.onnx", "model_quantized.onnx"),
    ("onnx/model_quantized.onnx_data", "model_quantized.onnx_data"),
]


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    for remote, local in FILES:
        out = DEST / local
        if out.exists() and out.stat().st_size > 1024:
            print("skip", local)
            continue
        url = BASE + remote
        t = time.time()
        try:
            with requests.get(url, stream=True, timeout=180) as r:
                r.raise_for_status()
                with open(out, "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
            print(f"{local} {out.stat().st_size / 1e6:.1f}MB {time.time() - t:.1f}s")
        except Exception as e:
            print("FAIL", local, type(e).__name__, str(e)[:80])
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
