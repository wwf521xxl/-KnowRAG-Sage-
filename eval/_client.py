import os

import requests

B = "http://127.0.0.1:8010"
PASS = os.environ.get("KB_PASS", "")
s = requests.Session()
s.post(B + "/api/login", json={"username": "boss", "password": PASS}, timeout=6)


def ask(q):
    return s.post(B + "/api/ask", json={"question": q}, timeout=120).json()
