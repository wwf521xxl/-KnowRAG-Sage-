import requests

H = {"User-Agent": "Mozilla/5.0"}
urls = [
    "https://www.modelscope.cn/api/v1/models/BAAI/bge-small-zh-v1.5/repo/files?Revision=master",
    "https://modelscope.cn/api/v1/models/AI-ModelScope/bge-small-zh-v1.5/repo/files?Revision=master",
]
for u in urls:
    try:
        r = requests.get(u, headers=H, timeout=20)
        print(u, r.status_code, len(r.text))
        if r.status_code == 200:
            data = r.json()
            files = data.get("Data", {}).get("Files", [])
            for f in files[:20]:
                print("  ", f.get("Path"), f.get("Size"))
    except Exception as e:
        print(u, "FAIL", type(e).__name__, str(e)[:80])
