"""Benchmark: transcribe a 10-minute slice to see if long files are the problem."""
import time

import numpy as np

import asr_runtime
from faster_whisper import BatchedInferencePipeline

PATH = r"F:\三把刀宋老师-AI+超级IP顶级流量闭门会2026年2月\五天视频课【无水印】\02、第二天.mp4"

import av  # noqa: E402

t0 = time.time()
with av.open(PATH) as c:
    st = c.streams.audio[0]
    res = av.AudioResampler(format="s16", layout="mono", rate=16000)
    chunks, total = [], 0
    for frame in c.decode(st):
        for f in res.resample(frame):
            arr = f.to_ndarray()
            chunks.append(arr)
            total += arr.shape[1]
        if total >= 16000 * 600:
            break
audio = np.concatenate(chunks, axis=1)[0].astype(np.float32) / 32768.0
print(f"decoded {len(audio)/16000:.0f}s in {time.time()-t0:.1f}s", flush=True)

rt = asr_runtime.make_pipeline(r"D:\知识库问答系统\models\faster-whisper-small", "cuda")
pipe = BatchedInferencePipeline(model=rt["model"])
t1 = time.time()
segments, info = pipe.transcribe(audio, language="zh", batch_size=8, vad_filter=True,
                                 without_timestamps=False, word_timestamps=False)
n = sum(1 for _ in segments)
dur = time.time() - t1
print(f"transcribed {len(audio)/16000:.0f}s in {dur:.1f}s = {len(audio)/16000/dur:.1f}x, segments={n}")
