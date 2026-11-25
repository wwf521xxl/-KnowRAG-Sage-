"""Benchmark faster-whisper configs on one short clip."""
import sys
import time

from faster_whisper import WhisperModel

AUDIO = sys.argv[1]
MODEL_DIR = sys.argv[2]
LABEL = sys.argv[3]
THREADS = int(sys.argv[4]) if len(sys.argv) > 4 else 16
BATCH = int(sys.argv[5]) if len(sys.argv) > 5 else 0

t0 = time.time()
model = WhisperModel(MODEL_DIR, device="cpu", compute_type="int8", cpu_threads=THREADS)
load = time.time() - t0

t1 = time.time()
if BATCH:
    from faster_whisper import BatchedInferencePipeline
    pipe = BatchedInferencePipeline(model=model)
    segments, info = pipe.transcribe(AUDIO, language="zh", batch_size=BATCH,
                                     vad_filter=True, condition_on_previous_text=False)
else:
    segments, info = model.transcribe(AUDIO, language="zh", beam_size=5,
                                      vad_filter=True, condition_on_previous_text=False)
rows = list(segments)
dur = time.time() - t1

text = "".join(r.text for r in rows)
print(f"{LABEL}: load={load:.1f}s transcribe={dur:.1f}s segments={len(rows)} "
      f"speed={82.0 / dur:.2f}x chars={len(text)}")
print("HEAD:", text[:60])
