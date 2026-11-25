import json
from pathlib import Path

EVAL = Path(r"D:\知识库问答系统\eval")
last = json.loads((EVAL / "last_run.json").read_text(encoding="utf-8"))
m = last["metrics"]
(EVAL / "baseline.json").write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(m, ensure_ascii=False, indent=2))
