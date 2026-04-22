"""T5 — Optional local embedding support via bge-micro-v2 ONNX.

Completely optional. If onnxruntime or the model file is absent, every
call returns empty results and the app degrades gracefully.

Model: BAAI/bge-micro-v2
  - 384-dim embeddings
  - ~22 MB ONNX file
  - ~5 ms per query on CPU
  - No internet at runtime — only one-time download

To enable:
  1. Download https://huggingface.co/BAAI/bge-micro-v2/resolve/main/onnx/model.onnx
     and save to data/models/bge-micro-v2.onnx
  2. Download tokenizer.json from same repo to data/models/tokenizer.json
  3. pip install onnxruntime tokenizers
  The app detects the files and sets EMBEDDING_ENABLED = True automatically.
"""
from __future__ import annotations

import logging
import math
import struct
from functools import lru_cache
from typing import List, Optional

log = logging.getLogger(__name__)

MODEL_VERSION = "bge-micro-v2"
_MAX_LEN = 128  # bge-micro sequence length


@lru_cache(maxsize=1)
def _load_session():
    """Load ONNX session. Cached so it's loaded once."""
    from ..utils.constants import EMBED_MODEL_PATH
    import onnxruntime as ort  # type: ignore
    if not EMBED_MODEL_PATH.exists():
        raise FileNotFoundError(f"Model not found: {EMBED_MODEL_PATH}")
    sess = ort.InferenceSession(
        str(EMBED_MODEL_PATH),
        providers=["CPUExecutionProvider"],
    )
    return sess


@lru_cache(maxsize=1)
def _load_tokenizer():
    from ..utils.constants import EMBED_TOKENIZER_PATH
    from tokenizers import Tokenizer  # type: ignore
    if not EMBED_TOKENIZER_PATH.exists():
        raise FileNotFoundError(f"Tokenizer not found: {EMBED_TOKENIZER_PATH}")
    return Tokenizer.from_file(str(EMBED_TOKENIZER_PATH))


def _mean_pool(token_embeddings, attention_mask) -> List[float]:
    """Mean pool token embeddings, ignoring padding."""
    # token_embeddings: (1, seq_len, hidden)
    # attention_mask:   (1, seq_len)
    total = [0.0] * len(token_embeddings[0][0])
    count = 0
    for j, mask in enumerate(attention_mask[0]):
        if mask:
            for k, v in enumerate(token_embeddings[0][j]):
                total[k] += v
            count += 1
    if count == 0:
        return total
    return [x / count for x in total]


def _normalize(vec: List[float]) -> List[float]:
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Embed a list of texts. Returns list of 384-dim normalized float vectors."""
    try:
        import numpy as np  # type: ignore
        sess = _load_session()
        tok = _load_tokenizer()
        tok.enable_truncation(max_length=_MAX_LEN)
        tok.enable_padding(length=_MAX_LEN)

        encodings = tok.encode_batch(texts)
        input_ids      = np.array([e.ids for e in encodings], dtype=np.int64)
        attention_mask = np.array([e.attention_mask for e in encodings], dtype=np.int64)
        token_type_ids = np.zeros_like(input_ids)

        outputs = sess.run(None, {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "token_type_ids": token_type_ids,
        })
        # outputs[0]: (batch, seq_len, hidden)
        results = []
        for i in range(len(texts)):
            pooled = _mean_pool(outputs[0][i:i+1], attention_mask[i:i+1])
            results.append(_normalize(pooled))
        return results

    except Exception as e:
        log.debug("Embedding failed: %s", e)
        return [[] for _ in texts]


def is_available() -> bool:
    """Return True if the embedding model and runtime are ready."""
    try:
        from ..utils.constants import EMBED_MODEL_PATH, EMBED_TOKENIZER_PATH
        if not EMBED_MODEL_PATH.exists() or not EMBED_TOKENIZER_PATH.exists():
            return False
        import onnxruntime  # type: ignore  # noqa
        from tokenizers import Tokenizer  # type: ignore  # noqa
        return True
    except ImportError:
        return False


def download_instructions() -> str:
    from ..utils.constants import EMBED_MODEL_DIR
    return (
        f"To enable semantic mode:\n"
        f"1. pip install onnxruntime tokenizers\n"
        f"2. Download model.onnx from https://huggingface.co/BAAI/bge-micro-v2/resolve/main/onnx/model.onnx\n"
        f"   → save to: {EMBED_MODEL_DIR / 'bge-micro-v2.onnx'}\n"
        f"3. Download tokenizer.json from https://huggingface.co/BAAI/bge-micro-v2/resolve/main/tokenizer.json\n"
        f"   → save to: {EMBED_MODEL_DIR / 'tokenizer.json'}\n"
        f"4. Restart the app."
    )
