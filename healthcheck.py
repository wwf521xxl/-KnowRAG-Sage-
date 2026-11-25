"""One-command self check for the knowledge base deployment."""
import socket
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
DB = ROOT / "data" / "kb.db"
results = []


def check(name, ok, detail="", warn=False):
    results.append((name, "WARN" if (warn and not ok) else ("PASS" if ok else "FAIL"), detail))


def main():
    # 1. 服务端口
    s = socket.socket()
    s.settimeout(2)
    try:
        s.connect(("127.0.0.1", 8010))
        port_ok = True
    except OSError:
        port_ok = False
    finally:
        s.close()
    check("服务端口 8010", port_ok, "端口可连接" if port_ok else "服务没启动")

    # 2. 登录页
    try:
        r = requests.get("http://127.0.0.1:8010/login", timeout=5)
        check("登录页", r.status_code == 200, f"HTTP {r.status_code}")
    except Exception as e:
        check("登录页", False, type(e).__name__)

    # 3. 数据库
    if DB.exists():
        con = sqlite3.connect(DB)
        n = con.execute("SELECT COUNT(*) FROM videos WHERE deleted_at IS NULL").fetchone()[0]
        seg = con.execute("SELECT COUNT(*) FROM segments").fetchone()[0]
        qa = con.execute("SELECT COUNT(*) FROM qa_logs").fetchone()[0]
        con.close()
        check("数据库", True, f"{DB.stat().st_size / 1e6:.1f}MB · {n} 条内容 · {seg} 段 · {qa} 条问答")
    else:
        check("数据库", False, "kb.db 不存在")

    # 4. 模型文件
    whisper = ROOT / "models" / "faster-whisper-medium" / "model.bin"
    check("转写模型", whisper.exists(), f"{whisper.stat().st_size / 1e6:.0f}MB" if whisper.exists() else "缺失")
    bge_dir = ROOT / "models" / "bge-small-zh-onnx"
    bge_files = list(bge_dir.glob("model_quantized.onnx*"))
    bge_mb = sum(f.stat().st_size for f in bge_files) / 1e6
    check("向量模型", bool(bge_files), f"{bge_mb:.0f}MB" if bge_files else "缺失")

    # 5. 磁盘
    usage = __import__("shutil").disk_usage(str(ROOT))
    free_gb = usage.free / 1e9
    check("磁盘空间", free_gb > 5, f"剩余 {free_gb:.0f} GB", warn=True)

    # 6. 最近备份
    backups = sorted((ROOT / "data" / "backup").glob("kb-*.zip"))
    if backups:
        age_h = (datetime.now() - datetime.fromtimestamp(backups[-1].stat().st_mtime)).total_seconds() / 3600
        check("最近备份", age_h < 48, f"{backups[-1].name}（{age_h:.0f} 小时前）", warn=True)
    else:
        check("最近备份", False, "没有备份文件", warn=True)

    # 7. 监听进程（看日志是否新鲜）
    log = ROOT / "data" / "logs" / "watch.log"
    if log.exists():
        age_min = (datetime.now() - datetime.fromtimestamp(log.stat().st_mtime)).total_seconds() / 60
        check("收件箱监听", age_min < 10, f"日志 {age_min:.0f} 分钟前更新", warn=True)
    else:
        check("收件箱监听", False, "没有 watch.log", warn=True)

    print(f"\n{'检查项':<16}{'结果':<8}说明")
    print("-" * 60)
    for name, status, detail in results:
        print(f"{name:<16}{status:<8}{detail}")
    fails = [r for r in results if r[1] == "FAIL"]
    warns = [r for r in results if r[1] == "WARN"]
    print("-" * 60)
    print(f"通过 {len(results) - len(fails) - len(warns)}，警告 {len(warns)}，失败 {len(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
