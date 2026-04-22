# src/_lazy_nltk.py
# Changes: Fixed offline first-run bug -- exceptions are now silently swallowed
# instead of re-raised, so the app falls back to regex sentence splitting gracefully.
"""Lazy NLTK punkt loader. Keeps NLTK from being a hard import-time dependency
and lets us point NLTK at a local data directory bundled in data/nltk_data.
First-run download is attempted only if the user has internet; on failure we
silently fall back to the regex sentence splitter in tokenizer.py."""
from __future__ import annotations

import os
import threading

from .utils.constants import NLTK_DATA_DIR

_LOCK = threading.Lock()
_DONE = False


def ensure_punkt() -> None:
    global _DONE
    if _DONE:
        return
    with _LOCK:
        if _DONE:
            return
        try:
            NLTK_DATA_DIR.mkdir(parents=True, exist_ok=True)
            os.environ.setdefault("NLTK_DATA", str(NLTK_DATA_DIR))
            import nltk  # type: ignore
            nltk.data.path.insert(0, str(NLTK_DATA_DIR))
            try:
                nltk.data.find("tokenizers/punkt_tab")
            except LookupError:
                try:
                    nltk.download("punkt_tab", download_dir=str(NLTK_DATA_DIR), quiet=True)
                except Exception:
                    pass  # offline -- regex fallback will be used
            try:
                nltk.data.find("tokenizers/punkt")
            except LookupError:
                try:
                    nltk.download("punkt", download_dir=str(NLTK_DATA_DIR), quiet=True)
                except Exception:
                    pass  # offline -- regex fallback will be used
        except Exception:
            pass  # NLTK not installed or any other error -- silently degrade
        finally:
            _DONE = True
