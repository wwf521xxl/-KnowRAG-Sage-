import statistics
import time

import requests

B = "http://127.0.0.1:8010"
QS = ["会员权益怎么设计？", "储值活动有什么好处？", "星巴克会员分几级？",
      "顾客回头率怎么算？", "积分怎么设置才有吸引力？", "门店执行要注意什么？",
      "会员招募有哪些渠道？", "什么是私域成交？"]

s = requests.Session()
s.post(B + "/api/login", json={"username": "boss", "password": "123456"}, timeout=6)
ts = []
for q in QS:
    t = time.time()
    d = s.post(B + "/api/ask", json={"question": q, "debug": True}, timeout=120).json()
    ms = round((time.time() - t) * 1000)
    tm = d["debug"]["timings"]
    ts.append(ms)
    print(f"{ms}ms  rerank={tm['rerank_ms']}  answer={tm['answer_ms']}  load={tm['load_ms']}  | {q}")

print("median", int(statistics.median(ts)), "p95", sorted(ts)[max(0, int(len(ts) * 0.95) - 1)])
