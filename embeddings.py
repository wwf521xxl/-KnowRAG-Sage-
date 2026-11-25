"""Local text embeddings: BGE small zh (ONNX, quantized). No torch needed."""
from pathlib import Path

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

MODEL_DIR = Path(__file__).resolve().parent / "models" / "bge-small-zh-onnx"


class Embedder:
    def __init__(self, model_dir=MODEL_DIR):
        model_dir = Path(model_dir)
        self.tok = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
        self.tok.enable_truncation(max_length=512)
        self.tok.enable_padding(pad_id=0, pad_token="[PAD]")
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 8
        self.sess = ort.InferenceSession(str(model_dir / "model_quantized.onnx"),
                                         sess_options=opts, providers=["CPUExecutionProvider"])
        self.names = {i.name for i in self.sess.get_inputs()}

    def encode(self, texts, batch_size=16):
        if isinstance(texts, str):
            texts = [texts]
        out = []
        for i in range(0, len(texts), batch_size):
            part = texts[i:i + batch_size]
            encs = self.tok.encode_batch(part)
            ids = np.array([e.ids for e in encs], dtype=np.int64)
            mask = np.array([e.attention_mask for e in encs], dtype=np.int64)
            feeds = {"input_ids": ids, "attention_mask": mask}
            if "token_type_ids" in self.names:
                feeds["token_type_ids"] = np.zeros_like(ids)
            hidden = self.sess.run(None, feeds)[0]
            vec = hidden[:, 0, :].astype(np.float32)  # CLS pooling (BGE)
            norm = np.linalg.norm(vec, axis=1, keepdims=True)
            out.append(vec / np.clip(norm, 1e-8, None))
        return np.vstack(out) if out else np.zeros((0, 512), dtype=np.float32)


if __name__ == "__main__":
    import time
    e = Embedder()
    t = time.time()
    v = e.encode(["私域成交的三步法", "如何让客户信任我", "完全无关的天气预报"])
    print("shape", v.shape, "time", round(time.time() - t, 2), "s")
    print("sim1", float(v[0] @ v[1]), "sim2", float(v[0] @ v[2]))
