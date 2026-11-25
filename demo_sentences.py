"""Transcribe one video into sentence-level segments (GPU first, CPU fallback)."""
import json
import sys
import time
from pathlib import Path

from asr_runtime import transcribe


def fmt(sec):
    s = int(sec)
    return f"{s // 60:02d}:{s % 60:02d}"


def main(video, model_dir, out_dir, device="auto"):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows, meta = transcribe(video, model_dir, device=device)
    print(json.dumps(meta, ensure_ascii=False), flush=True)
    for r in rows:
        print(f"[{fmt(r['start'])}] {r['text']}", flush=True)

    (out / "segments.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    md = ["# " + Path(video).stem, ""] + [f"[{fmt(r['start'])}] {r['text']}" for r in rows]
    (out / "transcript.md").write_text("\n".join(md), encoding="utf-8")
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main(*sys.argv[1:])
