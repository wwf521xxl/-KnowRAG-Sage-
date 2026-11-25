import os

import requests

B = "http://127.0.0.1:8010"
s = requests.Session()
s.post(B + "/api/login",
       json={"username": "boss", "password": os.environ.get("KB_PASS", "")}, timeout=10)

p = s.get(B + "/api/progress", timeout=10).json()
print("progress:", p)
for x in s.get(B + "/api/videos", timeout=10).json():
    print(f"{x['id']:>2} {x['kind']:<5} {x['state']:<9} {x['time']:<9} {x['name'][:26]}")
