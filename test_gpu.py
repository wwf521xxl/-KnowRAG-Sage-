"""Try CUDA inference with locally available cuBLAS (Ollama) + cuDNN redist."""
import os
import sys
import time
from pathlib import Path

DLL_DIRS = [
    Path(r"D:\知识库问答系统\cuda\cudnn\cudnn-windows-x86_64-9.9.0.52_cuda12-archive\bin"),
    Path(r"D:\模型ollama\lib\ollama\cuda_v12"),
]
for d in DLL_DIRS:
    if d.exists():
        os.add_dll_directory(str(d))
os.environ["PATH"] = ";".join(str(d) for d in DLL_DIRS) + ";" + os.environ.get("PATH", "")

from faster_whisper import WhisperModel  # noqa: E402

audio, model_dir, label = sys.argv[1], sys.argv[2], sys.argv[3]
compute = sys.argv[4] if len(sys.argv) > 4 else "float16"
batch = int(sys.argv[5]) if len(sys.argv) > 5 else 0

t0 = time.time()
model = WhisperModel(model_dir, device="cuda", compute_type=compute)
print(f"loaded on cuda ({compute}) in {time.time() - t0:.1f}s", flush=True)

t1 = time.time()
if batch:
    from faster_whisper import BatchedInferencePipeline
    pipe = BatchedInferencePipeline(model=model)
    segments, info = pipe.transcribe(audio, language="zh", batch_size=batch,
                                     without_timestamps=False, word_timestamps=True,
                                     vad_filter=True, condition_on_previous_text=False)
else:
    segments, info = model.transcribe(audio, language="zh", beam_size=5, vad_filter=True,
                                      condition_on_previous_text=False)
rows = list(segments)
dur = time.time() - t1
text = "".join(r.text for r in rows)
print(f"{label}: transcribe={dur:.1f}s segments={len(rows)} speed={82.0 / dur:.2f}x chars={len(text)}")
print("HEAD:", text[:60])
