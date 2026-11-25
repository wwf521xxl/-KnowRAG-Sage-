import os
import time

import requests

B = "http://127.0.0.1:8010"
s = requests.Session()
s.post(B + "/api/login", json={"username": "boss", "password": os.environ.get("KB_PASS", "")}, timeout=10)

# 生成一个 1 页的测试 PDF
import pymupdf

doc = pymupdf.open()
page = doc.new_page()
page.insert_text((72, 100), "Test upload for course grouping. 这是一段测试文字。", fontsize=14)
pdf = doc.tobytes()
doc.close()

r = s.post(B + "/api/upload", params={"name": "上传测试.pdf", "course": "测试课程"}, data=pdf,
           headers={"Content-Type": "application/pdf"}, timeout=30)
print("upload:", r.status_code, r.text[:80])

for i in range(12):
    time.sleep(2)
    vids = s.get(B + "/api/videos", timeout=10).json()
    hit = [v for v in vids if v["name"] == "上传测试"]
    if hit and hit[0]["state"] != "processing":
        print("processed:", hit[0]["id"], hit[0]["course"], hit[0]["state"], hit[0].get("error"))
        break
else:
    print("still processing")
