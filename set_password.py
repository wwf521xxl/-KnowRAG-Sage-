"""Set the login password for the knowledge base.

Usage:
    python set_password.py                 # random password, prints it
    python set_password.py 我的密码 boss    # explicit password + username
"""
import hashlib
import json
import secrets
import sys
from pathlib import Path

CFG = Path(__file__).resolve().parent / "config.local.json"
ITER = 200_000


def main():
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    if len(sys.argv) > 1:
        password = sys.argv[1]
    else:
        password = secrets.token_urlsafe(6)
    username = sys.argv[2] if len(sys.argv) > 2 else cfg.get("auth", {}).get("username", "boss")
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITER).hex()
    cfg["auth"] = {"username": username, "salt": salt, "hash": digest}
    cfg.setdefault("secret", secrets.token_hex(32))
    CFG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"username: {username}")
    print(f"password: {password}")
    print("(已写入 config.local.json，请把密码告诉使用者)")


if __name__ == "__main__":
    main()
