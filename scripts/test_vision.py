"""Check whether the configured model accepts image input and can read Chinese text."""
import base64
import json
from pathlib import Path

import requests

CFG = json.loads(Path(r"D:\知识库问答系统\config.local.json").read_text(encoding="utf-8"))
img = Path(r"D:\知识库问答系统\data\samples\test_note.png").read_bytes()
b64 = base64.b64encode(img).decode()

payload = {
    "model": CFG.get("model", "deepseek-chat"),
    "messages": [{
        "role": "user",
        "content": [
            {"type": "text", "text": "读出这张图里的全部文字，原样输出，不要解释。"},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ],
    }],
    "temperature": 0,
    "max_tokens": 300,
}
r = requests.post(CFG["base_url"].rstrip("/") + "/chat/completions",
                  headers={"Authorization": f"Bearer {CFG['api_key']}",
                           "Content-Type": "application/json"},
                  json=payload, timeout=90)
print("status", r.status_code)
if r.status_code == 200:
    data = r.json()
    print(data["choices"][0]["message"]["content"])
    print("usage", data.get("usage"))
else:
    print(r.text[:500])
