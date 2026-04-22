<!-- BEGIN FILE 1: julius\_suggested\_plan.md -->

# Julius' Suggested Plan

## Purpose

This plan consolidates the strongest architectural, product, and implementation ideas across the uploaded PDF app/codebase variants into one integrated roadmap. The goal is not to take the easiest path or simply choose one folder as the winner. The goal is to **weave together the best working concepts from the entire codebase into one optimized core** for uploading, parsing, indexing, and querying the text of PDF files as comprehensively and holistically as possible.

The right outcome is a single product core that preserves the value already present across the repository while removing duplication, drift, and competing implementations.

\---

## Core Product Vision

The unified app should revolve around one clean end-to-end flow:

**Upload PDFs and other supported documents -> extract text robustly -> normalize and enrich metadata -> chunk text intelligently -> index documents and chunks -> query with high-quality lexical retrieval -> present grounded page-aware results with explanations and navigation.**

That means the consolidated architecture should optimize for:

1. **Reliable ingestion** of messy PDFs and scanned documents
2. **High-quality retrieval** that feels intelligent without becoming opaque
3. **Fast iteration** so reindexing and experimentation stay practical
4. **Traceability** so users can see where answers came from
5. **Extensibility** so the app can absorb future features without another rewrite
6. **Reuse of existing code** so the strongest parts of the current repo are preserved rather than discarded

\---

## What the Uploaded Codebase Appears to Contain

The uploaded export appears to include multiple parallel or successive implementations of the same app family, including variants under folders such as Claude and Vibestral, and multiple repeated modules for:

* `pdf\_parser.py`
* `epub\_parser.py`
* `chunker.py`
* `tokenizer.py`
* `schema.py`
* `indexer.py`
* `query\_parser.py`
* `bm25.py`
* `searcher.py`
* `stemmer.py`
* `synonyms.py`
* desktop launchers, packaging files, and app shells

There are also repeated `README.md`, `ARCHITECTURE.md`, `requirements.txt`, `setup.py`, `pyinstaller.spec`, and launch scripts. That usually means the codebase contains not just implementation duplication, but **competing assumptions** about what the app is supposed to be.

This is actually an advantage if handled correctly. It means the repository already contains a rich feature inventory. The task is to turn that inventory into one coherent platform.

\---

## Strategic Recommendation

Do **not** consolidate by selecting one folder and deleting the rest.

Instead, consolidate by creating one official core package and treating the other folders as **feature donors**.

The target architecture should center on a single package such as:

```text
pdf\_intelligence\_core/
```

Everything else should either:

* feed into this core as migrated functionality,
* become a thin adapter around the core,
* or be archived as deprecated once its best ideas are absorbed.

This approach preserves the most value while eliminating fragmentation.

\---

## The Integrated Architecture I Would Build

### 1\. Ingestion Layer

This layer should unify all document entry paths and normalize them into one canonical internal representation.

Responsibilities:

* accept uploaded PDFs and other supported files
* identify file type
* fingerprint files using hash, size, and modified time
* detect whether the file is new, changed, or already indexed
* route to the proper parser
* capture document-level metadata early

Use the strongest ideas already present around:

* file hashing
* incremental reindex logic
* parser routing
* launch/UI upload flows

The output of this layer should be a standard `ParsedDocument` object regardless of source format.

\---

### 2\. Parsing Layer

The parser system should be one of the most important pieces of the unified product because PDF extraction quality determines everything downstream.

The app should adopt a parser cascade rather than a single parser dependency.

Recommended parsing strategy:

1. primary text extraction using the most accurate structured PDF parser available in the codebase
2. fallback extraction using a second PDF library if text quality is poor or empty
3. optional OCR path for scanned or image-based PDFs
4. page-level preservation so search results always reference original pages
5. metadata extraction including title, author, creation date, and document properties when available

The unified parser should preserve:

* page number
* per-page text
* extracted metadata
* parser method used
* OCR status
* extraction confidence or quality flags when possible

This is where the current multiple `pdf\_parser.py` implementations should be merged into one `ParserOrchestrator` pattern.

If the codebase already includes EPUB support, keep it, but keep PDF as the first-class document type.

\---

### 3\. Text Normalization Layer

Before chunking and indexing, text should flow through a standard normalization pipeline.

Responsibilities:

* whitespace cleanup
* hyphenation repair across line breaks
* header/footer suppression when repeated
* Unicode normalization
* quote and punctuation normalization
* page marker retention
* paragraph boundary preservation
* lightweight de-noising for OCR artifacts

This should not be scattered between parser, tokenizer, and search logic. It should be centralized so every downstream stage sees consistent text.

This is one of the biggest hidden optimization opportunities in a PDF app. Better normalization improves chunking, indexing, snippets, and ranking all at once.

\---

### 4\. Semantic Chunking Layer

Across the uploaded codebase there appear to be one or more `chunker.py` implementations, and at least one architecture description suggesting more advanced layered chunking. That should become a major pillar of the unified app.

The app should **not** index only whole documents and should **not** create blind fixed-size chunks only.

The best integrated approach is a layered chunking strategy:

#### Layer A: structural segmentation

Split on:

* title-like headings
* section boundaries
* page boundaries
* paragraph boundaries
* list boundaries

#### Layer B: size-aware chunk refinement

Then enforce target chunk sizes using character and token limits so chunks stay searchable and readable.

#### Layer C: overlap for recall

Apply small overlap windows so concepts crossing chunk boundaries remain retrievable.

#### Layer D: parent-child relationships

Store both:

* parent section chunk
* child searchable chunk

That enables both precise hits and broader context display.

Each chunk record should include:

* `chunk\_id`
* `doc\_id`
* `page\_start`
* `page\_end`
* `section\_title`
* `position\_in\_doc`
* `token\_count`
* normalized text
* display text
* optional parent chunk reference

This is one of the highest leverage places to combine the repo’s best ideas, because chunk design strongly affects ranking quality and snippet quality.

\---

### 5\. Tokenization, Stemming, and Synonym Expansion

The uploaded repo contains repeated modules for tokenization, stemming, and synonyms. These should all remain, but they need a clear contract and ordering.

Recommended search-language pipeline:

1. tokenize query
2. remove filler words and low-signal glue terms when appropriate
3. normalize case and punctuation
4. optionally stem tokens using the repo’s `stemmer.py`
5. expand synonyms from `synonyms.json` or `synonyms.py`
6. preserve exact phrase capability for quoted searches
7. support field-aware operators if present or planned

The key design principle is that synonym expansion should be **boosting-aware**, not just blind replacement. That is:

* exact term match should score highest
* stemmed form should score slightly lower
* synonym match should still help but not dominate

This allows the app to feel intelligent without returning obviously unrelated results.

A user-editable synonym layer is worth keeping because it makes the app adaptable to domain-specific document sets.

\---

### 6\. Query Understanding Layer

The best query path in the consolidated app should come from merging the explicit `query\_parser.py` work with the stronger retrieval ideas described in the architecture docs.

The unified query parser should support:

* simple keyword search
* quoted phrase search
* AND/OR/NOT style boolean logic where available
* field filters such as file type, author, year, folder, tags
* natural-language-ish queries with filler-word cleanup
* safe parsing into an FTS-compatible expression

The parser should also classify query intent when useful, for example:

* exact phrase intent
* broad exploratory intent
* metadata-filtering intent
* multi-term relevance intent

That classification can control retrieval behavior such as stricter phrase boosting versus broader lexical expansion.

This layer should be deterministic and inspectable. Users and developers should be able to see how a query was interpreted.

\---

### 7\. Indexing Layer

The indexing layer should combine the strongest SQLite/FTS design already present in the repo with a more explicit separation between document metadata and searchable chunks.

Recommended indexing model:

#### Document table

Stores one row per source file.

Fields should include:

* `doc\_id`
* path
* filename
* title
* author
* created\_at
* modified\_at
* file\_hash
* page\_count
* file\_type
* indexed\_at
* parse\_status
* parser\_used
* OCR\_used

#### Chunk table

Stores canonical chunk metadata.

Fields should include:

* `chunk\_id`
* `doc\_id`
* `chunk\_index`
* `page\_start`
* `page\_end`
* `section\_title`
* token\_count
* raw text
* normalized text
* display text
* parent\_chunk\_id

#### FTS table

Use FTS5 against chunk text, and optionally selected metadata fields.

#### Auxiliary tables

For:

* synonyms
* search history
* saved queries
* tags
* ingestion jobs
* index diagnostics

The indexing pipeline should support:

* first-time bulk indexing
* incremental updates
* deletion cleanup
* partial reindex when only one file changes
* transaction-safe writes
* index versioning and migrations

The repo already appears to contain `schema.py` and `indexer.py` concepts that can become the basis of this system. Those should be promoted into the canonical storage engine rather than duplicated per app variant.

\---

### 8\. Retrieval and Ranking Layer

This is where the repo’s repeated `bm25.py`, `searcher.py`, and FTS logic should be unified into one hybrid retrieval flow.

The best overall approach is:

#### Phase 1: fast candidate retrieval

Use SQLite FTS5 to retrieve a candidate set quickly.

#### Phase 2: reranking

Rerank the candidate set using a richer scoring function that blends:

* FTS score or match signal
* BM25 score
* phrase proximity
* exact match boosts
* title/heading match boosts
* metadata match boosts
* synonym-match discounting
* section importance boosts
* recency boosts only if appropriate

This is much stronger than either plain FTS or plain BM25 alone.

A recommended final scoring model could look like:

```text
final\_score =
    exact\_match\_boost
  + phrase\_boost
  + heading\_boost
  + metadata\_boost
  + normalized\_bm25
  + proximity\_score
  + field\_match\_score
  - synonym\_penalty\_if\_only\_indirect
```

This should remain interpretable. Ideally, every result can expose a mini score breakdown for debugging.

That keeps the app explainable while still feeling sophisticated.

\---

### 9\. Facets and Filters

The existence of `facets.py` is a strong signal that the app should preserve structured browsing, not just free-text search.

Faceting should be first-class in the unified app.

Recommended facets:

* file type
* author
* year
* folder or collection
* tags
* parser method
* OCR status
* document length buckets

Why this matters:

A good PDF intelligence app is not just a search box. It is a **search-and-narrow** system. Facets make the library explorable, debuggable, and much more useful for large corpora.

The SQL-driven facet aggregation logic should be kept and standardized against the new schema.

\---

### 10\. Snippet and Evidence Generation

One of the most important product details is what the user actually sees in results.

The unified result model should display:

* document title or filename
* page number range
* section heading if known
* highlighted snippet
* why this matched
* score or confidence indicator if useful

The snippet builder should:

* center around the best-matching text window
* prefer sentence boundaries
* highlight exact query terms first
* optionally highlight synonyms differently
* avoid ugly truncation
* preserve page awareness

This is where the app becomes more than “a local full-text index.” It becomes a **trustworthy evidence system**.

\---

### 11\. Result Navigation and Reading Experience

The app should not stop at listing hits.

A fully integrated result experience should allow users to:

* click a hit and jump to the relevant page
* browse surrounding chunk context
* open the source document from the result pane
* move to previous/next hit inside the document
* inspect metadata and indexing details
* copy matched text cleanly

If the current codebase has multiple UI variants, the one chosen for consolidation should be the one that best supports this reading-and-verification loop rather than just raw search submission.

The killer feature in a PDF query app is **grounded navigation back into the source**.

\---

### 12\. UI Consolidation Strategy

Because the export includes multiple application shells, I would unify the UI around one official surface and make everything else secondary.

The desktop app should include five primary panels or modes:

#### Library view

For managing uploaded files, indexing status, collections, and metadata.

#### Search view

Main query box, facets, results list, and snippet preview.

#### Reader view

Page-aware source viewing with hit navigation.

#### Diagnostics view

Parser used, OCR status, chunk counts, index freshness, query interpretation, candidate counts, and score details.

#### Settings view

Paths, parser preferences, OCR toggles, chunking settings, stopwords, synonyms, theme, and performance limits.

If one of the existing shells already has better shortcuts, theme support, or desktop packaging, keep those UX details. But all UI surfaces should call into the same core services.

No business logic should live in the GUI layer.

\---

### 13\. Upload and Library Management

Since the user specifically wants an app intended for uploading and querying PDF text, the upload flow needs to be treated as a core product surface, not an afterthought.

Recommended upload and library features:

* drag-and-drop file upload
* folder ingestion
* recursive library scanning option
* duplicate detection by file hash
* background indexing queue
* progress display
* file-level indexing status
* reindex selected file
* remove file from library and index
* watch folder option for automatic ingestion

This should integrate with the hashing and incremental index logic already suggested by modules like `file\_hash.py` and `indexer.py`.

\---

### 14\. Observability and Debugging Features

The more features that get unified, the more important internal visibility becomes.

The consolidated app should expose internal diagnostics for:

* parser selected
* extraction quality status
* OCR fallback triggered or not
* chunk counts by document
* average chunk size
* tokens generated
* query parse output
* FTS candidate counts
* BM25 rerank statistics
* indexing time per document
* stale or failed index entries

Without this, tuning the system becomes guesswork. With it, the app becomes maintainable.

This is especially important because the uploaded codebase appears to contain several versions of the same algorithmic components.

\---

### 15\. Configuration System

Right now the repeated constants, requirements, and duplicated setup files likely mean configuration has drifted across variants.

The consolidated core should move all tunables into one formal config system.

Suggested config areas:

* chunk size and overlap
* parser priority order
* OCR enable/disable
* stemming enable/disable
* synonym expansion rules
* stopword handling
* top-k retrieval sizes
* rerank weighting
* snippet window size
* database path
* cache paths
* logging verbosity

Use one config file model and one runtime source of truth.

This will make the app much easier to tune and package.

\---

### 16\. Canonical Internal Data Models

The existing codebase would benefit a lot from a shared domain model so every module speaks the same language.

Recommended core models:

#### `ParsedDocument`

Represents the extracted source.

Contains:

* document identity
* source path
* metadata
* page records
* parser method
* OCR flags
* extraction diagnostics

#### `Chunk`

Represents a searchable text unit.

Contains:

* chunk identity
* document reference
* page range
* text variants
* section info
* token counts
* ordering info

#### `SearchQuery`

Represents a parsed user query.

Contains:

* raw query
* normalized query
* operators
* phrases
* filters
* expansions
* intent classification

#### `SearchResult`

Represents a ranked hit.

Contains:

* document and chunk references
* score
* score breakdown
* snippet
* page location
* highlights
* match rationale

Once these models exist, almost all the duplicated modules can be consolidated around them.

\---

### 17\. Suggested Package Layout

Here is the structure I would recommend as the consolidated official app layout:

```text
pdf\_intelligence\_core/
├── pyproject.toml
├── README.md
├── data/
│   └── default\_synonyms.json
├── src/
│   └── pdf\_intelligence/
│       ├── \_\_init\_\_.py
│       ├── main.py
│       ├── config.py
│       ├── models.py
│       ├── services/
│       │   ├── ingest\_service.py
│       │   ├── parse\_service.py
│       │   ├── chunk\_service.py
│       │   ├── index\_service.py
│       │   ├── search\_service.py
│       │   ├── snippet\_service.py
│       │   └── diagnostics\_service.py
│       ├── parsers/
│       │   ├── base.py
│       │   ├── pdf\_parser.py
│       │   ├── epub\_parser.py
│       │   └── ocr\_parser.py
│       ├── text/
│       │   ├── normalizer.py
│       │   ├── tokenizer.py
│       │   ├── stemmer.py
│       │   ├── synonyms.py
│       │   └── chunker.py
│       ├── storage/
│       │   ├── schema.py
│       │   ├── migrations.py
│       │   ├── repository.py
│       │   └── file\_hash.py
│       ├── search/
│       │   ├── query\_parser.py
│       │   ├── bm25.py
│       │   ├── ranker.py
│       │   ├── facets.py
│       │   └── searcher.py
│       ├── ui/
│       │   ├── app.py
│       │   ├── library\_view.py
│       │   ├── search\_view.py
│       │   ├── reader\_view.py
│       │   ├── diagnostics\_view.py
│       │   └── settings\_view.py
│       └── utils/
│           ├── constants.py
│           ├── logging.py
│           └── paths.py
└── tests/
```

This layout is intentionally designed so nearly every repeated module from the current export has a clear destination.

\---

## How I Would Merge the Existing Repo Into This Core

### Preserve directly with light cleanup

These are likely concepts that should survive almost as-is:

* `tokenizer.py`
* `stemmer.py`
* `synonyms.py` and `synonyms.json`
* `file\_hash.py`
* facet SQL logic in `facets.py`
* FTS schema concepts in `schema.py`
* launch and packaging ideas that already work well

### Merge and refactor into one canonical implementation

These are the modules most likely to need synthesis from multiple variants:

* `pdf\_parser.py`
* `chunker.py`
* `indexer.py`
* `query\_parser.py`
* `searcher.py`
* `bm25.py`
* `main.py`

### Demote to adapters or compatibility shims

These are patterns that should exist only if needed for migration:

* old alternate app shells
* older launch entrypoints
* duplicate setup files
* redundant packaging scripts

### Archive after migration

Any module that duplicates functionality but adds no distinct value should be archived once the new core passes integration tests.

This is the difference between true consolidation and merely piling abstractions on top of duplication.

\---

## Search Quality Strategy

<!-- END FILE 1: julius\_suggested\_plan.md -->

\---

<!-- BEGIN FILE 2: julius\_suggested\_plan\_part\_1\_strategy\_and\_architecture.md -->

# Julius Suggested Plan Part 1 - Strategy and Architecture

# Julius' Suggested Plan

## Purpose

This plan consolidates the strongest architectural, product, and implementation ideas across the uploaded PDF app/codebase variants into one integrated roadmap. The goal is not to take the easiest path or simply choose one folder as the winner. The goal is to **weave together the best working concepts from the entire codebase into one optimized core** for uploading, parsing, indexing, and querying the text of PDF files as comprehensively and holistically as possible.

The right outcome is a single product core that preserves the value already present across the repository while removing duplication, drift, and competing implementations.

\---

## Core Product Vision

The unified app should revolve around one clean end-to-end flow:

**Upload PDFs and other supported documents -> extract text robustly -> normalize and enrich metadata -> chunk text intelligently -> index documents and chunks -> query with high-quality lexical retrieval -> present grounded page-aware results with explanations and navigation.**

That means the consolidated architecture should optimize for:

1. **Reliable ingestion** of messy PDFs and scanned documents
2. **High-quality retrieval** that feels intelligent without becoming opaque
3. **Fast iteration** so reindexing and experimentation stay practical
4. **Traceability** so users can see where answers came from
5. **Extensibility** so the app can absorb future features without another rewrite
6. **Reuse of existing code** so the strongest parts of the current repo are preserved rather than discarded

\---

## What the Uploaded Codebase Appears to Contain

The uploaded export appears to include multiple parallel or successive implementations of the same app family, including variants under folders such as Claude and Vibestral, and multiple repeated modules for:

* `pdf\_parser.py`
* `epub\_parser.py`
* `chunker.py`
* `tokenizer.py`
* `schema.py`
* `indexer.py`
* `query\_parser.py`
* `bm25.py`
* `searcher.py`
* `stemmer.py`
* `synonyms.py`
* desktop launchers, packaging files, and app shells

There are also repeated `README.md`, `ARCHITECTURE.md`, `requirements.txt`, `setup.py`, `pyinstaller.spec`, and launch scripts. That usually means the codebase contains not just implementation duplication, but **competing assumptions** about what the app is supposed to be.

This is actually an advantage if handled correctly. It means the repository already contains a rich feature inventory. The task is to turn that inventory into one coherent platform.

\---

## Strategic Recommendation

Do **not** consolidate by selecting one folder and deleting the rest.

Instead, consolidate by creating one official core package and treating the other folders as **feature donors**.

The target architecture should center on a single package such as:

```text
pdf\_intelligence\_core/
```

Everything else should either:

* feed into this core as migrated functionality,
* become a thin adapter around the core,
* or be archived as deprecated once its best ideas are absorbed.

This approach preserves the most value while eliminating fragmentation.

\---

## The Integrated Architecture I Would Build

### 1\. Ingestion Layer

This layer should unify all document entry paths and normalize them into one canonical internal representation.

Responsibilities:

* accept uploaded PDFs and other supported files
* identify file type
* fingerprint files using hash, size, and modified time
* detect whether the file is new, changed, or already indexed
* route to the proper parser
* capture document-level metadata early

Use the strongest ideas already present around:

* file hashing
* incremental reindex logic
* parser routing
* launch/UI upload flows

The output of this layer should be a standard `ParsedDocument` object regardless of source format.

\---

### 2\. Parsing Layer

The parser system should be one of the most important pieces of the unified product because PDF extraction quality determines everything downstream.

The app should adopt a parser cascade rather than a single parser dependency.

Recommended parsing strategy:

1. primary text extraction using the most accurate structured PDF parser available in the codebase
2. fallback extraction using a second PDF library if text quality is poor or empty
3. optional OCR path for scanned or image-based PDFs
4. page-level preservation so search results always reference original pages
5. metadata extraction including title, author, creation date, and document properties when available

The unified parser should preserve:

* page number
* per-page text
* extracted metadata
* parser method used
* OCR status
* extraction confidence or quality flags when possible

This is where the current multiple `pdf\_parser.py` implementations should be merged into one `ParserOrchestrator` pattern.

If the codebase already includes EPUB support, keep it, but keep PDF as the first-class document type.

\---

### 3\. Text Normalization Layer

Before chunking and indexing, text should flow through a standard normalization pipeline.

Responsibilities:

* whitespace cleanup
* hyphenation repair across line breaks
* header/footer suppression when repeated
* Unicode normalization
* quote and punctuation normalization
* page marker retention
* paragraph boundary preservation
* lightweight de-noising for OCR artifacts

This should not be scattered between parser, tokenizer, and search logic. It should be centralized so every downstream stage sees consistent text.

This is one of the biggest hidden optimization opportunities in a PDF app. Better normalization improves chunking, indexing, snippets, and ranking all at once.

\---

### 4\. Semantic Chunking Layer

Across the uploaded codebase there appear to be one or more `chunker.py` implementations, and at least one architecture description suggesting more advanced layered chunking. That should become a major pillar of the unified app.

The app should **not** index only whole documents and should **not** create blind fixed-size chunks only.

The best integrated approach is a layered chunking strategy:

#### Layer A: structural segmentation

Split on:

* title-like headings
* section boundaries
* page boundaries
* paragraph boundaries
* list boundaries

#### Layer B: size-aware chunk refinement

Then enforce target chunk sizes using character and token limits so chunks stay searchable and readable.

#### Layer C: overlap for recall

Apply small overlap windows so concepts crossing chunk boundaries remain retrievable.

#### Layer D: parent-child relationships

Store both:

* parent section chunk
* child searchable chunk

That enables both precise hits and broader context display.

Each chunk record should include:

<!-- END FILE 2: julius\_suggested\_plan\_part\_1\_strategy\_and\_architecture.md -->

\---

<!-- BEGIN FILE 3: julius\_suggested\_plan\_part\_2\_search\_and\_data\_model.md -->

# Julius Suggested Plan Part 2 - Search and Data Model



* `chunk\_id`
* `doc\_id`
* `page\_start`
* `page\_end`
* `section\_title`
* `position\_in\_doc`
* `token\_count`
* normalized text
* display text
* optional parent chunk reference

This is one of the highest leverage places to combine the repo’s best ideas, because chunk design strongly affects ranking quality and snippet quality.

\---

### 5\. Tokenization, Stemming, and Synonym Expansion

The uploaded repo contains repeated modules for tokenization, stemming, and synonyms. These should all remain, but they need a clear contract and ordering.

Recommended search-language pipeline:

1. tokenize query
2. remove filler words and low-signal glue terms when appropriate
3. normalize case and punctuation
4. optionally stem tokens using the repo’s `stemmer.py`
5. expand synonyms from `synonyms.json` or `synonyms.py`
6. preserve exact phrase capability for quoted searches
7. support field-aware operators if present or planned

The key design principle is that synonym expansion should be **boosting-aware**, not just blind replacement. That is:

* exact term match should score highest
* stemmed form should score slightly lower
* synonym match should still help but not dominate

This allows the app to feel intelligent without returning obviously unrelated results.

A user-editable synonym layer is worth keeping because it makes the app adaptable to domain-specific document sets.

\---

### 6\. Query Understanding Layer

The best query path in the consolidated app should come from merging the explicit `query\_parser.py` work with the stronger retrieval ideas described in the architecture docs.

The unified query parser should support:

* simple keyword search
* quoted phrase search
* AND/OR/NOT style boolean logic where available
* field filters such as file type, author, year, folder, tags
* natural-language-ish queries with filler-word cleanup
* safe parsing into an FTS-compatible expression

The parser should also classify query intent when useful, for example:

* exact phrase intent
* broad exploratory intent
* metadata-filtering intent
* multi-term relevance intent

That classification can control retrieval behavior such as stricter phrase boosting versus broader lexical expansion.

This layer should be deterministic and inspectable. Users and developers should be able to see how a query was interpreted.

\---

### 7\. Indexing Layer

The indexing layer should combine the strongest SQLite/FTS design already present in the repo with a more explicit separation between document metadata and searchable chunks.

Recommended indexing model:

#### Document table

Stores one row per source file.

Fields should include:

* `doc\_id`
* path
* filename
* title
* author
* created\_at
* modified\_at
* file\_hash
* page\_count
* file\_type
* indexed\_at
* parse\_status
* parser\_used
* OCR\_used

#### Chunk table

Stores canonical chunk metadata.

Fields should include:

* `chunk\_id`
* `doc\_id`
* `chunk\_index`
* `page\_start`
* `page\_end`
* `section\_title`
* token\_count
* raw text
* normalized text
* display text
* parent\_chunk\_id

#### FTS table

Use FTS5 against chunk text, and optionally selected metadata fields.

#### Auxiliary tables

For:

* synonyms
* search history
* saved queries
* tags
* ingestion jobs
* index diagnostics

The indexing pipeline should support:

* first-time bulk indexing
* incremental updates
* deletion cleanup
* partial reindex when only one file changes
* transaction-safe writes
* index versioning and migrations

The repo already appears to contain `schema.py` and `indexer.py` concepts that can become the basis of this system. Those should be promoted into the canonical storage engine rather than duplicated per app variant.

\---

### 8\. Retrieval and Ranking Layer

This is where the repo’s repeated `bm25.py`, `searcher.py`, and FTS logic should be unified into one hybrid retrieval flow.

The best overall approach is:

#### Phase 1: fast candidate retrieval

Use SQLite FTS5 to retrieve a candidate set quickly.

#### Phase 2: reranking

Rerank the candidate set using a richer scoring function that blends:

* FTS score or match signal
* BM25 score
* phrase proximity
* exact match boosts
* title/heading match boosts
* metadata match boosts
* synonym-match discounting
* section importance boosts
* recency boosts only if appropriate

This is much stronger than either plain FTS or plain BM25 alone.

A recommended final scoring model could look like:

```text
final\_score =
    exact\_match\_boost
  + phrase\_boost
  + heading\_boost
  + metadata\_boost
  + normalized\_bm25
  + proximity\_score
  + field\_match\_score
  - synonym\_penalty\_if\_only\_indirect
```

This should remain interpretable. Ideally, every result can expose a mini score breakdown for debugging.

That keeps the app explainable while still feeling sophisticated.

\---

<!-- END FILE 3: julius\_suggested\_plan\_part\_2\_search\_and\_data\_model.md -->

\---

<!-- BEGIN FILE 4: julius\_suggested\_plan\_part\_3\_packaging\_migration\_and\_execution.md -->

# Julius Suggested Plan Part 3 - Packaging Migration and Execution



### 9\. Facets and Filters

The existence of `facets.py` is a strong signal that the app should preserve structured browsing, not just free-text search.

Faceting should be first-class in the unified app.

Recommended facets:

* file type
* author
* year
* folder or collection
* tags
* parser method
* OCR status
* document length buckets

Why this matters:

A good PDF intelligence app is not just a search box. It is a **search-and-narrow** system. Facets make the library explorable, debuggable, and much more useful for large corpora.

The SQL-driven facet aggregation logic should be kept and standardized against the new schema.

\---

### 10\. Snippet and Evidence Generation

One of the most important product details is what the user actually sees in results.

The unified result model should display:

* document title or filename
* page number range
* section heading if known
* highlighted snippet
* why this matched
* score or confidence indicator if useful

The snippet builder should:

* center around the best-matching text window
* prefer sentence boundaries
* highlight exact query terms first
* optionally highlight synonyms differently
* avoid ugly truncation
* preserve page awareness

This is where the app becomes more than “a local full-text index.” It becomes a **trustworthy evidence system**.

\---

### 11\. Result Navigation and Reading Experience

The app should not stop at listing hits.

A fully integrated result experience should allow users to:

* click a hit and jump to the relevant page
* browse surrounding chunk context
* open the source document from the result pane
* move to previous/next hit inside the document
* inspect metadata and indexing details
* copy matched text cleanly

If the current codebase has multiple UI variants, the one chosen for consolidation should be the one that best supports this reading-and-verification loop rather than just raw search submission.

The killer feature in a PDF query app is **grounded navigation back into the source**.

\---

### 12\. UI Consolidation Strategy

Because the export includes multiple application shells, I would unify the UI around one official surface and make everything else secondary.

The desktop app should include five primary panels or modes:

#### Library view

For managing uploaded files, indexing status, collections, and metadata.

#### Search view

Main query box, facets, results list, and snippet preview.

#### Reader view

Page-aware source viewing with hit navigation.

#### Diagnostics view

Parser used, OCR status, chunk counts, index freshness, query interpretation, candidate counts, and score details.

#### Settings view

Paths, parser preferences, OCR toggles, chunking settings, stopwords, synonyms, theme, and performance limits.

If one of the existing shells already has better shortcuts, theme support, or desktop packaging, keep those UX details. But all UI surfaces should call into the same core services.

No business logic should live in the GUI layer.

\---

### 13\. Upload and Library Management

Since the user specifically wants an app intended for uploading and querying PDF text, the upload flow needs to be treated as a core product surface, not an afterthought.

Recommended upload and library features:

* drag-and-drop file upload
* folder ingestion
* recursive library scanning option
* duplicate detection by file hash
* background indexing queue
* progress display
* file-level indexing status
* reindex selected file
* remove file from library and index
* watch folder option for automatic ingestion

This should integrate with the hashing and incremental index logic already suggested by modules like `file\_hash.py` and `indexer.py`.

\---

### 14\. Observability and Debugging Features

The more features that get unified, the more important internal visibility becomes.

The consolidated app should expose internal diagnostics for:

* parser selected
* extraction quality status
* OCR fallback triggered or not
* chunk counts by document
* average chunk size
* tokens generated
* query parse output
* FTS candidate counts
* BM25 rerank statistics
* indexing time per document
* stale or failed index entries

Without this, tuning the system becomes guesswork. With it, the app becomes maintainable.

This is especially important because the uploaded codebase appears to contain several versions of the same algorithmic components.

\---

### 15\. Configuration System

Right now the repeated constants, requirements, and duplicated setup files likely mean configuration has drifted across variants.

The consolidated core should move all tunables into one formal config system.

Suggested config areas:

* chunk size and overlap
* parser priority order
* OCR enable/disable
* stemming enable/disable
* synonym expansion rules
* stopword handling
* top-k retrieval sizes
* rerank weighting
* snippet window size
* database path
* cache paths
* logging verbosity

Use one config file model and one runtime source of truth.

This will make the app much easier to tune and package.

\---

### 16\. Canonical Internal Data Models

The existing codebase would benefit a lot from a shared domain model so every module speaks the same language.

Recommended core models:

#### `ParsedDocument`

Represents the extracted source.

Contains:

* document identity
* source path
* metadata
* page records
* parser method
* OCR flags
* extraction diagnostics

#### `Chunk`

Represents a searchable text unit.

Contains:

* chunk identity
* document reference
* page range
* text variants
* section info
* token counts
* ordering info

#### `SearchQuery`

Represents a parsed user query.

Contains:

* raw query
* normalized query
* operators
* phrases
* filters
* expansions
* intent classification

#### `SearchResult`

Represents a ranked hit.

Contains:

* document and chunk references
* score
* score breakdown
* snippet
* page location
* highlights
* match rationale

Once these models exist, almost all the duplicated modules can be consolidated around them.

\---

### 17\. Suggested Package Layout

Here is the structure I would recommend as the consolidated official app layout:

```text
pdf\_intelligence\_core/
├── pyproject.toml
├── README.md
├── data/
│   └── default\_synonyms.json
├── src/
│   └── pdf\_intelligence/
│       ├── \_\_init\_\_.py
│       ├── main.py
│       ├── config.py
│       ├── models.py
│       ├── services/
│       │   ├── ingest\_service.py
│       │   ├── parse\_service.py
│       │   ├── chunk\_service.py
│       │   ├── index\_service.py
│       │   ├── search\_service.py
│       │   ├── snippet\_service.py
│       │   └── diagnostics\_service.py
│       ├── parsers/
│       │   ├── base.py
│       │   ├── pdf\_parser.py
│       │   ├── epub\_parser.py
│       │   └── ocr\_parser.py
│       ├── text/
│       │   ├── normalizer.py
│       │   ├── tokenizer.py
│       │   ├── stemmer.py
│       │   ├── synonyms.py
│       │   └── chunker.py
│       ├── storage/
│       │   ├── schema.py
│       │   ├── migrations.py
│       │   ├── repository.py
│       │   └── file\_hash.py
│       ├── search/
│       │   ├── query\_parser.py
│       │   ├── bm25.py
│       │   ├── ranker.py
│       │   ├── facets.py
│       │   └── searcher.py
│       ├── ui/
│       │   ├── app.py
│       │   ├── library\_view.py
│       │   ├── search\_view.py
│       │   ├── reader\_view.py
│       │   ├── diagnostics\_view.py
│       │   └── settings\_view.py
│       └── utils/
│           ├── constants.py
│           ├── logging.py
│           └── paths.py
└── tests/
```

This layout is intentionally designed so nearly every repeated module from the current export has a clear destination.

\---

## How I Would Merge the Existing Repo Into This Core

### Preserve directly with light cleanup

These are likely concepts that should survive almost as-is:

* `tokenizer.py`
* `stemmer.py`
* `synonyms.py` and `synonyms.json`
* `file\_hash.py`
* facet SQL logic in `facets.py`
* FTS schema concepts in `schema.py`
* launch and packaging ideas that already work well

### Merge and refactor into one canonical implementation

These are the modules most likely to need synthesis from multiple variants:

* `pdf\_parser.py`
* `chunker.py`
* `indexer.py`
* `query\_parser.py`
* `searcher.py`
* `bm25.py`
* `main.py`

### Demote to adapters or compatibility shims

These are patterns that should exist only if needed for migration:

* old alternate app shells
* older launch entrypoints
* duplicate setup files
* redundant packaging scripts

### Archive after migration

Any module that duplicates functionality but adds no distinct value should be archived once the new core passes integration tests.

This is the difference between true consolidation and merely piling abstractions on top of duplication.

\---

## Search Quality Strategy

<!-- END FILE 4: julius\_suggested\_plan\_part\_3\_packaging\_migration\_and\_execution.md -->

