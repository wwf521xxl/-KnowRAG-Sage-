"""知识库 · 桌面控制面板

双击启动后：自动拉起服务、显示状态，可最小化到托盘。
用 pythonw.exe 运行不弹黑窗。
"""
import os
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

import tkinter as tk
from tkinter import messagebox

ROOT = Path(__file__).resolve().parent
PY = ROOT / ".venv" / "Scripts" / "python.exe"
PYW = ROOT / ".venv" / "Scripts" / "pythonw.exe"
DB = ROOT / "data" / "kb.db"
URL = "http://127.0.0.1:8010"
CREATE_NO_WINDOW = 0x08000000

children = {}
TRAY = None


def port_up(host="127.0.0.1", port=8010):
    s = socket.socket()
    s.settimeout(1)
    try:
        s.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def spawn(name, args, exe=None):
    # 子进程用 python.exe + CREATE_NO_WINDOW：pythonw 没有 stdout，服务里的 print 会崩
    exe = str(exe or PY)
    flags = CREATE_NO_WINDOW
    p = subprocess.Popen([exe, *args], cwd=str(ROOT), creationflags=flags,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    children[name] = p
    return p


def start_all():
    if not port_up():
        spawn("server", [str(ROOT / "kb_server.py"), "8010"])
    ensure_watch()


def ensure_watch():
    if not port_up(port=8011):
        spawn("watch", [str(ROOT / "watch.py"), "--interval", "60"])


def stop_all():
    for p in children.values():
        try:
            p.terminate()
        except Exception:
            pass
    children.clear()


def stats():
    try:
        con = sqlite3.connect(DB)
        n = con.execute("SELECT COUNT(1) FROM videos WHERE deleted_at IS NULL").fetchone()[0]
        seg = con.execute("SELECT COUNT(1) FROM segments").fetchone()[0]
        con.close()
        return n, seg
    except Exception:
        return 0, 0


class App:
    def __init__(self, root):
        self.root = root
        root.title("知识库")
        root.geometry("360x220")
        root.resizable(False, False)
        try:
            root.iconbitmap(str(ROOT / "app.ico"))
        except Exception:
            pass
        root.protocol("WM_DELETE_WINDOW", self.hide)

        self.status = tk.Label(root, text="正在启动…", font=("Microsoft YaHei UI", 12, "bold"))
        self.status.pack(pady=(18, 4))
        self.detail = tk.Label(root, text="", fg="#5b6b7c", font=("Microsoft YaHei UI", 9))
        self.detail.pack()

        bar = tk.Frame(root)
        bar.pack(pady=14)
        tk.Button(bar, text="打开知识库", width=12, command=self.open, height=1).pack(side="left", padx=4)
        tk.Button(bar, text="备份", width=6, command=self.backup).pack(side="left", padx=4)
        tk.Button(bar, text="重启", width=6, command=self.restart).pack(side="left", padx=4)

        tk.Button(root, text="隐藏到托盘（服务继续运行）", relief="flat", fg="#5b6b7c",
                  command=self.hide).pack(side="bottom", pady=8)

        threading.Thread(target=self.supervise, daemon=True).start()

    def refresh(self, up):
        n, seg = stats()
        self.status.config(text="● 服务运行中" if up else "○ 服务未启动",
                           fg="#2f7d4f" if up else "#b03060")
        self.detail.config(text=f"{n} 条内容 · {seg} 段可检索")

    def supervise(self):
        while True:
            up = port_up()
            if not up:
                start_all()
                time.sleep(4)
                up = port_up()
            ensure_watch()  # 监听进程掉了也拉起来
            self.root.after(0, self.refresh, up)
            time.sleep(8)

    def open(self):
        if not port_up():
            start_all()
            time.sleep(3)
        webbrowser.open(URL)

    def backup(self):
        subprocess.Popen([str(PY), str(ROOT / "backup.py")], cwd=str(ROOT),
                         creationflags=CREATE_NO_WINDOW,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        messagebox.showinfo("备份", "已在后台备份，完成后可在 data\\backup 查看。")

    def restart(self):
        stop_all()
        time.sleep(1)
        start_all()
        time.sleep(3)
        self.refresh(port_up())

    def hide(self):
        self.root.withdraw()
        if TRAY:
            TRAY.notify("知识库仍在后台运行", "知识库")


def tray_icon(app):
    global TRAY
    try:
        import pystray
        from PIL import Image
    except Exception:
        return None
    try:
        img = Image.open(ROOT / "app.ico")
    except Exception:
        img = Image.new("RGB", (64, 64), (31, 78, 121))

    def show(icon, item):
        app.root.deiconify()
        app.root.lift()

    def quit_(icon, item):
        icon.stop()
        stop_all()
        app.root.after(0, app.root.destroy)

    menu = pystray.Menu(
        pystray.MenuItem("打开知识库", lambda i, it: app.open()),
        pystray.MenuItem("显示面板", show, default=True),
        pystray.MenuItem("退出", quit_),
    )
    TRAY = pystray.Icon("kb", img, "知识库", menu)

    def run_tray():
        try:
            TRAY.run()
        except Exception:
            # 托盘初始化失败（权限/资源管理器异常）时，退回普通窗口
            app.root.after(0, app.root.deiconify)

    threading.Thread(target=run_tray, daemon=True).start()
    return TRAY


def main():
    # 单实例：面板只允许开一个，避免两套托盘/重复拉起
    lock = socket.socket()
    try:
        lock.bind(("127.0.0.1", 8012))
        lock.listen(1)
    except OSError:
        return

    if "--minimized" in sys.argv:
        start_all()
    else:
        ensure_watch()
    root = tk.Tk()
    app = App(root)
    tray_icon(app)
    if "--minimized" in sys.argv:
        root.withdraw()
    if "--smoke" in sys.argv:
        root.after(6000, root.destroy)
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        log = ROOT / "data" / "logs" / "app.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(traceback.format_exc(), encoding="utf-8")
        raise
