"""Inbox watcher: scan a folder every N seconds and process whatever is new.

Usage:
    python watch.py                 # watch data/inbox every 60s
    python watch.py --dir D:\inbox --interval 30
    python watch.py --once          # single pass (for testing)
"""
import argparse
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = ROOT / ".venv" / "Scripts" / "python.exe"
LOG = ROOT / "data" / "logs" / "watch.log"

if sys.stdout is None:  # running under pythonw
    LOG.parent.mkdir(parents=True, exist_ok=True)
    sys.stdout = open(LOG, "a", encoding="utf-8")
    sys.stderr = sys.stdout


def log(msg):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line, flush=True)


def run(args):
    p = subprocess.run([str(PY)] + args, cwd=str(ROOT), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    out = (p.stdout or "").strip()
    err = (p.stderr or "").strip()
    if out:
        log(out.replace("\n", " | ")[:1500])
    if p.returncode != 0:
        log(f"ERROR exit={p.returncode} {err[:800]}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(ROOT / "data" / "inbox"))
    ap.add_argument("--interval", type=int, default=60)
    ap.add_argument("--limit", type=int, default=3)
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()

    inbox = Path(args.dir)
    inbox.mkdir(parents=True, exist_ok=True)

    guard = socket.socket()
    try:
        guard.bind(("127.0.0.1", 8011))  # 单实例：已有监听就退出
        guard.listen(1)
    except OSError:
        log("another watcher is already running, exit")
        return

    log(f"watch start dir={inbox} interval={args.interval}s limit={args.limit}")

    last_backup = None
    while True:
        run(["batch.py", "scan", str(inbox)])
        run(["batch.py", "run", "--dir", str(inbox), "--limit", str(args.limit)])

        today = datetime.now().date().isoformat()
        if datetime.now().hour >= 3 and last_backup != today:
            run(["backup.py"])
            last_backup = today

        if args.once:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
