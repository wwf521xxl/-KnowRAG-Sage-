"""Transcribe one local video with faster-whisper and save timestamped segments."""
import json
import sys
import time
from pathlib import Path

from faster_whisper import WhisperModel


def fmt(ms):
    s = int(ms // 1000)
    return f"{s // 60:02d}:{s % 60:02d}"


def main(video, model_dir, out_dir, lang=None, prompt=None):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    model = WhisperModel(model_dir, device="cpu", compute_type="int8", cpu_threads=8)
    print(f"model loaded in {time.time() - t0:.1f}s", flush=True)

    t1 = time.time()
    segments, info = model.transcribe(
        video,
        language=lang,
        beam_size=5,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
        condition_on_previous_text=False,
        initial_prompt=prompt,
    )
    rows = []
    for seg in segments:
        rows.append({
            "start": round(seg.start, 2),
            "end": round(seg.end, 2),
            "text": seg.text.strip(),
        })
        print(f"[{fmt(seg.start * 1000)}] {seg.text.strip()}", flush=True)
    print(f"detected language={info.language} prob={info.language_probability:.2f}", flush=True)
    print(f"transcribed in {time.time() - t1:.1f}s, {len(rows)} segments", flush=True)

    (out / "segments.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    md = [f"# {Path(video).stem}", ""]
    for r in rows:
        md.append(f"[{fmt(r['start'] * 1000)}] {r['text']}")
    (out / "transcript.md").write_text("\n".join(md), encoding="utf-8")


if __name__ == "__main__":
    main(*sys.argv[1:])
