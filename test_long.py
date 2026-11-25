"""Long-form check: tile the sample audio to ~27 minutes and time GPU inference."""
import time

import numpy as np
from faster_whisper import BatchedInferencePipeline, decode_audio

import asr_runtime  # sets DLL paths on import

SRC = r"D:\知识库问答系统\视屏数据\e182316fa47e562613d45ab0f419b5c9.mp4"
MODEL = r"D:\知识库问答系统\models\faster-whisper-medium"

audio = decode_audio(SRC, sampling_rate=16000)
long_audio = np.tile(audio, 20)
minutes = len(long_audio) / 16000 / 60
print(f"audio minutes: {minutes:.1f}", flush=True)

model, dev, compute = asr_runtime.load_model(MODEL, "auto")
print("device", dev, compute, flush=True)

pipe = BatchedInferencePipeline(model=model)
t0 = time.time()
segments, info = pipe.transcribe(long_audio, language="zh", batch_size=8,
                                 without_timestamps=False, word_timestamps=False,
                                 vad_filter=True, condition_on_previous_text=False)
n, chars = 0, 0
for seg in segments:
    n += 1
    chars += len(seg.text)
dur = time.time() - t0
print(f"segments={n} chars={chars} elapsed={dur:.1f}s speed={minutes * 60 / dur:.1f}x "
      f"per_hour={dur / (minutes / 60) / 60:.1f} min")
