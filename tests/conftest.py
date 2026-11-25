import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# CI 或新克隆环境下没有本地配置：写一个占位配置，避免导入时失败
CFG = ROOT / "config.local.json"
if not CFG.exists():
    CFG.write_text(json.dumps({
        "api_key": "sk-test",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "auth": {"username": "boss", "salt": "00" * 16, "hash": "00" * 32},
        "secret": "test-secret",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
