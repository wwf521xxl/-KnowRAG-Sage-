import os

import av

base = r"F:\三把刀宋老师-AI+超级IP顶级流量闭门会2026年2月"
for name in sorted(os.listdir(base)):
    if not name.lower().endswith(".mp4"):
        continue
    p = os.path.join(base, name)
    try:
        with av.open(p) as c:
            print(name, "OK", round(c.duration / av.time_base / 60, 1), "min", file=open(os.devnull, "w"))
            print(f"{name} OK {c.duration/av.time_base/60:.1f} min")
    except Exception as e:
        print(f"{name} FAIL {type(e).__name__}: {str(e)[:80]}")
