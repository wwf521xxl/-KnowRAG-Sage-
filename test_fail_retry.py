import os
import time

import pymupdf
import requests

B = "http://127.0.0.1:8010"
s = requests.Session()
s.post(B + "/api/login", json={"username": "boss", "password": os.environ.get("KB_PASS", "")}, timeout=10)

doc = pymupdf.open()
doc.new_page()  # 空白页：没有文字，应该处理失败
blank = doc.tobytes()
doc.close()

r = s.post(B + "/api/upload", params={"name": "空白测试.pdf", "course": "测试课程"}, data=blank,
           timeout=30)
print("upload:", r.status_code)

vid = None
for _ in range(20):
    time.sleep(2)
    vids = s.get(B + "/api/videos", timeout=10).json()
    hit = [v for v in vids if v["name"] == "空白测试"]
    if hit and hit[0]["state"] != "processing":
        vid = hit[0]
        break

if not vid:
    print("still processing")
    raise SystemExit(0)

print("state:", vid["state"], "| error:", vid["error"][:80])
if vid["error"]:
    r = s.post(B + f"/api/retry/{vid['id']}", timeout=10)
    print("retry:", r.status_code, r.text)
    time.sleep(2)
    again = [v for v in s.get(B + "/api/videos", timeout=10).json() if v["id"] == vid["id"]]
    print("after retry:", again[0]["status"] if again else "?")
