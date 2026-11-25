"""Backup kb.db + text library into data/backup as a zip, keeping the last 30 days."""
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB = ROOT / "data" / "kb.db"
LIB = ROOT / "data" / "library"
OUT = ROOT / "data" / "backup"
KEEP = 30


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    target = OUT / f"kb-{stamp}.zip"
    tmp = OUT / "_kb_snapshot.db"

    src = sqlite3.connect(DB)
    dst = sqlite3.connect(tmp)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()

    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(tmp, "kb.db")
        if LIB.exists():
            for p in LIB.rglob("*"):
                if p.is_file():
                    z.write(p, p.relative_to(ROOT / "data"))
    tmp.unlink(missing_ok=True)

    backups = sorted(OUT.glob("kb-*.zip"))
    for old in backups[:-KEEP]:
        old.unlink(missing_ok=True)

    print(f"backup -> {target} ({target.stat().st_size / 1e6:.1f} MB), kept {min(len(backups), KEEP)}")


if __name__ == "__main__":
    main()
