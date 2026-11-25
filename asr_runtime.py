"""ASR runtime: GPU-first faster-whisper with CPU fallback.

On Windows the CUDA runtime DLLs are not shipped with ctranslate2. This module
prepares DLL search paths (cuDNN from the CUDA redist, cuBLAS from the local
Ollama install by default) before importing ctranslate2.
"""
import os
import re
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
DEFAULT_DLL_DIRS = [
    _ROOT / "cuda" / "cudnn" / "cudnn-windows-x86_64-9.9.0.52_cuda12-archive" / "bin",
    _ROOT / "cuda" / "cublas",
    Path(r"D:\模型ollama\lib\ollama\cuda_v12"),
]


def setup_dlls():
    dirs = os.environ.get("KB_CUDA_DLL_DIRS")
    candidates = [Path(p) for p in dirs.split(";")] if dirs else DEFAULT_DLL_DIRS
    ready = []
    for d in candidates:
        if d.is_dir():
            try:
                os.add_dll_directory(str(d))
            except (OSError, AttributeError):
                pass
            ready.append(str(d))
    if ready:
        os.environ["PATH"] = ";".join(ready) + ";" + os.environ.get("PATH", "")
    return ready


setup_dlls()

from faster_whisper import BatchedInferencePipeline, WhisperModel  # noqa: E402

try:
    from zhconv import convert as to_simplified
except Exception:  # pragma: no cover
    def to_simplified(text, _="zh-cn"):
        return text

SENT_END = re.compile(r"[。！？!?；;]$")


def pick_device(prefer="auto"):
    if prefer == "cpu":
        return "cpu", "int8"
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda", "float16"
    except Exception:
        pass
    return "cpu", "int8"


def load_model(model_dir, device="auto", cpu_threads=16):
    dev, compute = pick_device(device)
    model = WhisperModel(str(model_dir), device=dev, compute_type=compute, cpu_threads=cpu_threads)
    return model, dev, compute


def split_sentences(words):
    sentences, buf = [], []
    for w in words:
        buf.append(w)
        if SENT_END.search(w.word.strip()):
            sentences.append(buf)
            buf = []
    if buf:
        sentences.append(buf)
    return sentences


def make_pipeline(model_dir, device="auto", cpu_threads=16):
    """Load the model once and keep it for many files (batch mode)."""
    model, dev, compute = load_model(model_dir, device, cpu_threads=cpu_threads)
    pipe = BatchedInferencePipeline(model=model) if dev == "cuda" else None
    return {"pipe": pipe, "model": model, "device": dev, "compute": compute}


def split_by_chars(text, start, end):
    """没有词级时间戳时，按字数把一段文本的时间按比例切开。"""
    parts = [p.strip() for p in re.findall(r"[^。！？!?；;]+[。！？!?；;]?", text) if p.strip()]
    if not parts:
        return []
    total = sum(len(p) for p in parts) or 1
    span = max(0.0, end - start)
    out, cur = [], start
    for p in parts:
        dur = span * len(p) / total
        out.append({"start": round(cur, 2), "end": round(cur + dur, 2), "text": to_simplified(p, "zh-cn")})
        cur += dur
    return out


def transcribe_with(runtime, video, batch_size=8, language="zh", word_timestamps=True):
    """Transcribe using a preloaded runtime from make_pipeline().

    word_timestamps=True 更准但长音频会明显变慢；批量入库建议关闭。
    """
    t1 = time.time()
    if runtime["pipe"] is not None:
        segments, info = runtime["pipe"].transcribe(
            video, language=language, batch_size=batch_size, vad_filter=True,
            without_timestamps=False, word_timestamps=word_timestamps,
            condition_on_previous_text=False)
    else:
        segments, info = runtime["model"].transcribe(
            video, language=language, beam_size=5, vad_filter=True,
            without_timestamps=False, word_timestamps=word_timestamps,
            condition_on_previous_text=False)

    rows = []
    for seg in segments:
        if word_timestamps and seg.words:
            for words in split_sentences(seg.words):
                text = re.sub(r"\s+", "", "".join(w.word for w in words)).strip()
                if len(text) < 2:
                    continue
                rows.append({
                    "start": round(words[0].start, 2),
                    "end": round(words[-1].end, 2),
                    "text": to_simplified(text, "zh-cn"),
                })
        else:
            rows.extend(split_by_chars(seg.text.strip(), seg.start, seg.end))
    meta = {
        "device": runtime["device"],
        "compute_type": runtime["compute"],
        "transcribe_seconds": round(time.time() - t1, 1),
        "segments": len(rows),
        "language": info.language,
    }
    return rows, meta


def transcribe_chunked(runtime, video, chunk_seconds=1800, batch_size=8, language="zh"):
    """Decode once, then transcribe 30-minute slices.

    A single 2-hour array makes the batched pipeline several times slower and
    memory-hungry; slicing keeps it at full speed.
    """
    from faster_whisper import decode_audio

    t0 = time.time()
    audio = decode_audio(str(video), sampling_rate=16000)
    decode_s = time.time() - t0

    step = int(chunk_seconds * 16000)
    rows = []
    t1 = time.time()
    for start in range(0, len(audio), step):
        part = audio[start:start + step]
        if len(part) < 16000:  # < 1s
            break
        base = start / 16000
        if runtime["pipe"] is not None:
            segments, info = runtime["pipe"].transcribe(
                part, language=language, batch_size=batch_size, vad_filter=True,
                without_timestamps=False, word_timestamps=False,
                condition_on_previous_text=False)
        else:
            segments, info = runtime["model"].transcribe(
                part, language=language, beam_size=5, vad_filter=True,
                without_timestamps=False, word_timestamps=False,
                condition_on_previous_text=False)
        for seg in segments:
            rows.extend(split_by_chars(seg.text.strip(), seg.start + base, seg.end + base))

    return rows, {
        "device": runtime["device"],
        "compute_type": runtime["compute"],
        "decode_seconds": round(decode_s, 1),
        "transcribe_seconds": round(time.time() - t1, 1),
        "segments": len(rows),
        "language": "zh",
    }


def transcribe(video, model_dir, device="auto", batch_size=8, language="zh"):
    """Return (rows, meta). rows: [{start, end, text}] sentence level."""
    t0 = time.time()
    runtime = make_pipeline(model_dir, device)
    load_s = round(time.time() - t0, 1)
    rows, meta = transcribe_with(runtime, video, batch_size=batch_size, language=language)
    meta["load_seconds"] = load_s
    return rows, meta
