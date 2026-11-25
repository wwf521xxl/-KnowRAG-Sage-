import os
import secrets

import requests

B = "http://127.0.0.1:8010"
s = requests.Session()
s.post(B + "/api/login", json={"username": "boss", "password": "123456"}, timeout=6)

uid = secrets.token_hex(16)
data = os.urandom(10 * 1024 * 1024)  # 10 MB
CH = 4 * 1024 * 1024
total = (len(data) + CH - 1) // CH

for i in range(total):
    part = data[i * CH:(i + 1) * CH]
    r = s.post(B + f"/api/upload_chunk?upload_id={uid}&index={i}", data=part, timeout=60)
    print("chunk", i, r.status_code, r.json())

r = s.post(B + "/api/upload_finish", params={"upload_id": uid, "name": "chunk_test.bin",
                                            "total": total, "course": ""}, timeout=60)
print("finish:", r.status_code, r.json())

p = r"D:\知识库问答系统\data\inbox\chunk_test.bin"
print("exists:", os.path.exists(p), "size:", os.path.getsize(p) if os.path.exists(p) else 0)
if os.path.exists(p):
    print("content match:", open(p, "rb").read() == data)
    os.remove(p)
