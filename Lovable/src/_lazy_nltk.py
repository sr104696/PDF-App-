"""Lazy NLTK punkt loader. Keeps NLTK from being a hard import-time dependency
and lets us point NLTK at a local data directory bundled in `data/nltk_data`.
First-run download is attempted only if the user has internet; otherwise we
silently fall back to the regex sentence splitter."""
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
        NLTK_DATA_DIR.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("NLTK_DATA", str(NLTK_DATA_DIR))
        import nltk  # type: ignore
        nltk.data.path.insert(0, str(NLTK_DATA_DIR))
        try:
            nltk.data.find("tokenizers/punkt")
        except LookupError:
            try:
                nltk.download("punkt", download_dir=str(NLTK_DATA_DIR), quiet=True)
            except Exception:
                # Offline first-run: we'll silently use regex fallback.
                raise
        try:
            nltk.data.find("tokenizers/punkt_tab")
        except LookupError:
            try:
                nltk.download("punkt_tab", download_dir=str(NLTK_DATA_DIR), quiet=True)
            except Exception:
                pass
        _DONE = True
