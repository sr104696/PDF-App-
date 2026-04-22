# PDF Intelligence — Holistic Offline Search Engine

A fully offline desktop application that searches PDF and EPUB libraries with genuine intent-awareness. No internet. No AI API. No cloud.

## Quick Start

```
pip install -r requirements.txt
python -m src.main
```

Or on Windows, double-click **launch.bat**.

---

## What Makes This Different

Search in five concentric circles of meaning:

| Circle | Method | Example: "love and loss" |
|--------|--------|--------------------------|
| Literal | FTS5 exact match | finds "love", "loss" |
| Stem | Snowball morphology | finds "loving", "losses" |
| Synonym | Curated thesaurus (300+ entries) | finds "grief", "devotion", "heartbreak" |
| Conceptual | Thematic neighbors | finds "elegy", "longing", "impermanence", "yearning" |
| Corpus | Co-occurrence in your library | finds terms that cluster near your atoms in your specific books |
| Embedding *(optional)* | bge-micro ONNX | finds passages with zero word overlap but same meaning |

Eight intent types recognized: `quote_seek`, `emotional_theme`, `definition`, `example_seek`, `comparison`, `narrative`, `person_seek`, `general`.

Eight scoring signals: BM25 on stems, BM25 on synonyms, BM25 on concepts, co-occurrence, structural intent bonus, proximity bonus, section-header match, embedding similarity.

---

## Usage

**GUI** (default):
```
python -m src.main
```

**CLI index**:
```
python -m src.main index /path/to/pdfs
python -m src.main index book1.pdf book2.epub
```

**CLI search**:
```
python -m src.main search "quotes on love and loss"
python -m src.main search "the loneliness of growing old"
```

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| Ctrl+F | Jump to search |
| Ctrl+O | Add files |
| Esc | Clear search |
| Enter | Run search |

---

## Enabling Semantic Mode (T5 — optional)

Semantic mode adds a local 22 MB ONNX embedding model for the outermost circle of meaning. No internet at runtime.

1. `pip install onnxruntime tokenizers numpy`
2. Download `model.onnx` from https://huggingface.co/BAAI/bge-micro-v2/resolve/main/onnx/model.onnx → save to `data/models/bge-micro-v2.onnx`
3. Download `tokenizer.json` from https://huggingface.co/BAAI/bge-micro-v2/resolve/main/tokenizer.json → save to `data/models/tokenizer.json`
4. Restart the app — status bar shows **Semantic mode: ON**

---

## Customizing the Thesaurus

Edit `data/synonyms.json`. Each entry has three layers:
- `direct` — immediate synonyms (weight 0.85)
- `concepts` — thematic neighbors (weight 0.60)
- `register` — domain tags (used for cross-domain expansion)

Changes are picked up on the next search session start (no restart needed).

---

## Packaging

```
pip install pyinstaller
pyinstaller pyinstaller.spec
# Output: dist/PDFIntelligence.exe  (~25-30 MB)
```

---

## Architecture Tiers

| Tier | What it adds |
|------|-------------|
| T0 | Bug-free baseline (all Qwen Coder + Codex fixes) |
| T1 | 300+ entry thesaurus, 5-layer expansion, 8-intent classifier |
| T2 | Extended schema, enriched indexer, 8-signal composite scorer |
| T3 | Corpus co-occurrence calibration |
| T4 | Coherence pass (Jaccard dedup + adjacency boost + phonetic fallback) |
| T5 | Optional bge-micro ONNX embedding model |
