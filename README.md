# LexiRAG 2.0

**Upload PDFs. Ask a question. Check the source.**

A local Python application for reading legal documents, investigating source evidence and building persistent research. NiceGUI replaces the original Streamlit dashboard; FastAPI endpoints and the existing RAG engine run in the same process. SQLite stores workspaces, documents, conversations, saved findings, evidence relationships, timeline events, briefs and processing jobs.

Start with `main.py` or `launch.bat`. `app.py` is a compatibility launcher for the same application. The obsolete Streamlit implementation has been removed; its source archive remains in `data/backups/lexirag-v1-source.zip`. See [REFACTOR_VALIDATION.md](REFACTOR_VALIDATION.md) for the current cleanup and regression results.

## Windows setup and launch

```powershell
cd C:\Users\Swarnalata\Desktop\RAG
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# For a new installation only; do not overwrite an existing configured .env:
Copy-Item .env.example .env
```

Set `GOOGLE_API_KEY` in `.env` to your [Google AI Studio key](https://aistudio.google.com/apikey). Set `GEMINI_MODEL` to an available text-generation model for that project. The existing configured key is retained during this upgrade and is never displayed by the interface or committed.

Start one process:

```powershell
.\.venv\Scripts\python.exe main.py
```

Open **http://127.0.0.1:8080**. Alternatively, double-click `launch.bat`. No separately started backend, database, worker service, Tesseract installation or Windows environment-variable configuration is required for default English OCR. Set `LEXIRAG_PORT` in `.env` if another local port is needed. Restart after changing environment configuration.

For optional answer-quality evaluation:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-eval.txt
```

Python 3.11 on Windows is the validation target. Model loading and recognition run on CPU. Initial embedding/reranker use downloads public weights; later use prefers the complete local snapshot. RapidOCR's validated package includes its default ONNX models. Several GB of disk space and RAM are recommended for the full Python/torch/model environment. `requirements-lock.txt` records the exact validated environment, including optional development/evaluation packages; normal users need only `requirements.txt`.

## First research session

1. Open **Home** and drop your PDFs into the upload area. Scanned pages are read automatically; no collection setup or processing choices are required.
2. Type a question in the large question box and choose **Ask a question**.
3. Read the answer in **AI Research**. Click a document/page citation to view the highlighted original page and supporting passage.
4. Choose **Save finding** to keep a useful point, or **Export report** to download the current answer as a cited PDF.
5. Open **My Research** to revisit past answers, select saved findings for a report, or download a saved report again.

For a document summary, choose **Summarize** on its Home card. Questions, summaries, comparisons, saved findings and reports persist after restart. Existing research collections and their document boundaries are preserved. First use creates an initial collection automatically; an older library without collections is adopted into that first collection.

Example questions: "What are the main points in these documents?", "How much notice does this agreement require?", "Which documents discuss the right to privacy?", "What are the main differences between these agreements?"

LexiRAG supports legal research; it does not replace professional legal advice or independently verify current law, amendments or judicial treatment. Questions and relevant excerpts are sent to Google Gemini when you request an answer, comparison or summary. PDF originals remain local.

## Three sections

| Section | What you can do |
| --- | --- |
| Home | Drag and drop multiple PDFs, see preparation progress, ask a question, try example questions, open recent PDFs, summarize, or delete a document. |
| AI Research | Ask questions, follow up, optionally choose which PDFs to use, read clear answers, click original-page citations, save findings, copy answers and export PDF reports. |
| My Research | Select saved findings for a cited PDF report, reopen questions and comparisons, inspect saved passages and download persistent reports. |

These are the only application pages. `/comparison` and earlier tool URLs return to Home. The dedicated comparison pages and `ResearchService.compare` entry point have been removed. Inactive UI modules and the old Streamlit implementation are also removed. Existing documents and all saved records, including historical comparison answers, remain stored. Reopening or exporting a record still requires valid source documents. Search methods, legal-reference lookup, evidence expansion and OCR run automatically.

Questions involving several documents in AI Research retain independent
per-PDF, concept-based retrieval, automatic cross-encoder ranking, bounded evidence
expansion and balanced context. Joint findings must cite both sides; unsupported
comparative claims are withheld. See [CROSSDOC_VALIDATION.md](CROSSDOC_VALIDATION.md)
for measured gains, latency costs and the remaining partial-answer cases.

Light/dark themes, phone layouts, a responsive navigation drawer, global research search, Ctrl+K, Ctrl+Enter to ask, clear empty states and loading indicators are shared across the application. Original pages render locally, with a separate link to the original PDF at the cited page.

See [RULE45_VALIDATION.md](RULE45_VALIDATION.md) for the latest real E-Commerce Rules retrieval checks, [COMPARISON_FIX_VALIDATION.md](COMPARISON_FIX_VALIDATION.md) for scanned-PDF comparison results, and [RETRIEVAL_FIX_VALIDATION.md](RETRIEVAL_FIX_VALIDATION.md) for the Consumer Protection Act investigation. Earlier interface validation remains in [SIMPLE_UI_VALIDATION.md](SIMPLE_UI_VALIDATION.md) and [V2_VALIDATION.md](V2_VALIDATION.md).

## Automatic extraction and OCR

For each original PDF page, the processor:

1. Reads native text, text blocks, dimensions and image coverage.
2. Flags image-only pages, text-poor image pages, suspicious native encoding and dense vector-only pages.
3. Renders suspicious pages locally and uses RapidOCR's public `RapidOCR(...)(image)` API with the ONNX Runtime CPU engine.
4. Retains recognized text, confidence and line boxes transformed back to PDF coordinates.
5. Uses the old PyMuPDF/Tesseract path only as an optional fallback when Tesseract language data was already configured. It is not required or requested during normal use.
6. Keeps usable pages if another page fails. Unreadable/corrupt text is excluded and that original file page is flagged.
7. Splits readable text without crossing original page boundaries and indexes only usable chunks.

The app performs a real small-image OCR health check at startup in the background. The service can rerun it. A failure produces a recovery message, not a raw Python traceback or a mandatory `TESSDATA_PREFIX` instruction. Background jobs persist stages and page/batch counts in SQLite. Interrupted work is marked for retry after restart. Cancellation takes effect at a safe stage boundary; an ONNX or embedding call already executing is allowed to finish.

**Languages and limits:** English recognition was genuinely tested. The bundled recognition model also supports Chinese; this project does not claim that every Indian script, handwriting, stamp or damaged scan is supported. Other scripts need a suitable validated recognition model. OCR can misread legal text; inspect the original highlighted region before relying on a finding. Very high-resolution scans and large documents take longer on CPU.

PyMuPDF4LLM is used conservatively for an auxiliary readable-layout view on suitable complex pages. It does not replace exact citation text with unverified generated content. Native text boxes and OCR line regions are retained. Native PDF search highlights matching text; OCR highlights cover recognized **line regions**, not exact character positions. Where a reliable match is unavailable, the viewer explicitly shows the page and quotation without an asserted exact highlight.

`Advisory-7.pdf` was not present in the project. Validation therefore used actual raster-only, mixed native/scanned and incomplete-text teaching PDFs. Their original pages and rendered OCR highlights were inspected. See [V2_VALIDATION.md](V2_VALIDATION.md) for evidence and screenshots.

## Retrieval, generation and research integrity

The existing architecture remains: local normalized Sentence Transformer embeddings → exact FAISS cosine retrieval plus BM25 → Reciprocal Rank Fusion → optional cross-encoder reranking → bounded evidence → Gemini through maintained LangChain structured-output runnables.

| User search mode | Parameters |
| --- | --- |
| Fast search | Semantic, K=4, no reranker |
| Balanced search | Hybrid FAISS/BM25 with RRF, K=6, no reranker |
| Deep research | Hybrid with cross-encoder, K=12 |

The modes above remain internal/CLI capabilities; there are no technical retrieval controls in the interface. Automatic hybrid search adds exact legal-reference and defined-term lookup, carries numbered provisions across pages, and includes continuation chunks. Weak retrieval or an insufficient-evidence response triggers bounded keyword reformulations, neighboring passages and an expanded evidence set. Every attempt keeps the same document/workspace/metadata filters and strict quote validation. The context budget still applies. Candidate pools are bounded by the eligible corpus; RRF uses `1/(60+rank)`. Retrieval scores are relevance signals, not legal-confidence probabilities. An empty workspace is rejected rather than accidentally searching the whole library.

Older imports without page records recover those records from their original PDFs, using automatic local OCR when needed. Existing chunk IDs, text, vectors and saved references remain unchanged. New uploads split on statutory structure and retain page-local provision labels; short numbered lists stay together. Private rotating diagnostics in `data/logs/retrieval.jsonl` record questions, filters, chunk IDs and section references, never source passages or API keys.

Follow-ups use prior **user questions** and the displayed document order to resolve references. Explicit ordinal references can constrain fresh retrieval to the intended selected source. Prior generated prose is never substituted for source evidence. Complex ambiguous references should be clarified by naming the document; the system does not promise unrestricted conversational reasoning over a case-law corpus.

Every accepted finding must cite actually supplied passages and exact quotations. Whole findings with invalid source IDs, missing references or unsupported quotations are withheld. Facts and interpretations are separated, and a lack of evidence causes a refusal or explicit limitation. Interpretations and limitations appear with answers; structural provenance, duplicate evidence, short quotations and possible exception passages remain available through backend quality checks. These checks do **not** prove semantic entailment or legal correctness. Potentially contrary relationships remain user annotations until reviewed; no graph edge establishes that a judgment is overruled.

The retained backend evidence graph derives edges only from saved citations or explicit annotations with a recorded basis. It has no application page. Existing graph annotations and timeline records remain in SQLite.

Timeline extraction recognizes unambiguous ISO dates and written day/month/year dates. It labels roles only from nearby explicit wording; otherwise it uses “Mentioned date”. It avoids ambiguous numeric dates and year-only guesses. Enactment, publication, notification and commencement are not interchangeable. Automatic source dates cannot be edited into different facts; users can add labeled manual annotations instead.

Brief generation composes selected validated findings and exact source references **without another model call to fill missing sections**. Supported sections include background, provisions, judgments, findings, evidence analysis, potentially contrary evidence, limitations and conclusion. Empty sections are not padded with unsupported claims. User edits remain a draft and require review. Export is blocked if a selected finding's sources were removed or changed. Arial/DejaVu fonts support normal English reports; shaping of arbitrary Indic scripts is not guaranteed.

## Persistence, migrations and reliability

- SQLite remains authoritative for original documents, chunk metadata and normalized embedding blobs. FAISS artifacts are derived and recoverable.
- The v2 schema migration is additive and idempotent. A `metadata.pre-v2.sqlite3` backup is created before the first migration. Existing document IDs, chunk IDs, embedding vectors and revision values are preserved.
- Workspace membership, research runs, findings, evidence, annotated links, timeline events, briefs, processing jobs and recent activity are persisted in the same database.
- Reindexing builds replacement extraction and embeddings before changing stored content. Existing workspace membership and unchanged chunk references are preserved. Changed chunk IDs invalidate stale evidence safely.
- Document hashes prevent duplicate indexing, including repeated uploads across workspaces. Attach an existing library PDF to another workspace without regenerating embeddings.
- Missing, stale or corrupt FAISS files rebuild from SQLite vectors. No pickle files are deserialized. Atomic replacements, transactions and corpus locks protect mutations.
- Models load lazily and are reused across worker calls. A complete cached snapshot is preferred before network lookups, avoiding repeated downloads and parallel duplicate model initialization.
- Page previews are cached locally in process memory. Rendering adds highlights to an in-memory document, never modifies the original PDF.

Run the migration independently if desired:

```powershell
.\.venv\Scripts\python.exe -m scripts.migrate_database
```

Back up the database, uploads and any required private exports together. The pre-v2 database backup is retained on reset; it is a backup, not a second active corpus.

## Configuration and privacy

`.env.example` lists all settings. Keep keys only in `.env` or process environment variables. Defaults:

- `LEXIRAG_DATA_DIR=data`, `LEXIRAG_PORT=8080`
- `EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2`
- `RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L6-v2`
- `CHUNK_SIZE=900`, `CHUNK_OVERLAP=120`, `LLM_CONTEXT_CHARS=24000`
- Upload limit 30 MB / 1,000 original pages per PDF

Document text, original PDFs, embeddings, OCR and local search remain on this machine. Questions and selected excerpts go to Google Gemini during generation. Ragas optionally sends answers/excerpts for evaluation. Prompt tracing is disabled. Application logs avoid questions, answers, keys and document text; the SQLite research history intentionally persists those materials for the user's own workspaces. `.env`, active runtime data, private exports, indexes, logs and session secrets are ignored by version control.

This is a trusted **local, single-user** app bound to loopback. There is no internet deployment hardening, authentication, multi-tenant isolation or encryption at rest. Do not expose its port publicly for confidential materials. Extracted text is untrusted data and has no tool execution access. Prompt injection and erroneous interpretations remain possible even with constrained generation.

Delete a workspace to delete its saved research while retaining library PDFs. Delete a PDF to remove the original, indexed page/chunk records and embeddings across workspaces; saved research referencing it becomes unavailable and copied draft/history text may remain in the database. Use workspace deletion/full reset when removing those copies as well. Full reset safely cancels ingestion and removes active workspace research, library/index records, pending PDFs, jobs and experiments. Backups, screenshots, downloaded exports and provider-side data are not remotely erased. Logical deletion is not forensic secure erasure.

## Tests and actual validation

```powershell
.\.venv\Scripts\python.exe -m pytest -q --tb=short
.\.venv\Scripts\python.exe -m compileall -q main.py backend core database ui utils evaluation scripts
.\.venv\Scripts\python.exe -m pip check
```

The original tests are preserved, with the obsolete mandatory-Tesseract expectation updated to the automatic OCR contract. New tests cover migration integrity, workspace isolation and persistence, background failure/retry/cancellation, real OCR on actual raster PDFs, mixed pages, original-page boxes, saved evidence, relationship provenance, fresh-context retrieval, timelines, editable briefs, PDF export, reset/recovery and API uploads. Unit RAG tests use explicit deterministic test doubles; the real OCR test uses actual RapidOCR/ONNX output.

Install browser-test tools only when needed:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

`scripts/check_simple_ui.py` drives an actual Edge/Chromium browser through the three main sections, confirms removed routes return to Home, uploads generated PDFs including a real scan, checks automatic reading, and captures desktop/phone screenshots. Add `--live` to test actual Gemini answers, cited summaries, unsupported-question rejection and downloaded reports. Use a separate data directory so development tests do not modify your library:

The runner below starts and stops an isolated server automatically. Each run needs a fresh directory:

```powershell
.\.venv\Scripts\python.exe -m scripts.check_application --directory refactor-validation/application --live
```

To run the server and browser check separately:

```powershell
# Terminal 1: isolated server
$env:LEXIRAG_DATA_DIR="$PWD/data/simple-validation/corpus"
$env:HF_HOME="$PWD/data/model_cache"
$env:LEXIRAG_PORT="8082"
.\.venv\Scripts\python.exe main.py
# Terminal 2: browser check; --live uses the configured Gemini key
.\.venv\Scripts\python.exe -m scripts.check_simple_ui --live
```

Obsolete browser scripts for earlier interfaces have been removed. Use `check_simple_ui.py` for the current flow.

For regular use, one `python main.py` command is sufficient. Refer to [V2_VALIDATION.md](V2_VALIDATION.md) for measured results, artifacts, screenshots and limitations. Previous v1 live results remain in [LIVE_TEST_RESULTS.md](LIVE_TEST_RESULTS.md) as historical evidence rather than claims about the new UI.

## Evaluation

The evaluation CLI accepts human-authored JSONL labels with actual chunk IDs. Export passage IDs, inspect originals, label all relevant chunks, choose retrieval methods and run the experiment. See [evaluation/README.md](evaluation/README.md) for the full annotation protocol and metric definitions.

```powershell
.\.venv\Scripts\python.exe -m evaluation.export_chunks --output data/annotation_chunks.jsonl
.\.venv\Scripts\python.exe -m evaluation.runner data/questions.jsonl --k 6
# Optional live answer/rejection and Ragas evaluation:
.\.venv\Scripts\python.exe -m evaluation.runner data/questions.jsonl --k 6 --answers --ragas
```

Precision@K, Recall@K, MRR, retrieval/response latency, structural citation provenance, semantic citation support, answer faithfulness and rejection rates are reported only when actually measured. Null means unmeasured or undefined. Experiments record dataset provenance and the corpus revision. Ragas uses its collections API with an async Gemini judge through Google's OpenAI-compatible endpoint; no OpenAI-hosted model or OpenAI key is required. Its compatibility pin for LangChain Community is documented in `requirements-eval.txt`.

Synthetic teaching data is explicitly distinguished from authentic legal evaluation. No controlled general-LLM baseline is included; performance improvements over an ordinary chatbot are not claimed without measurements. The practical additions are source traceability, reusable workspace evidence, chronology and editable briefs.

## Structure

```text
main.py                       NiceGUI + FastAPI entry point (one process)
launch.bat                    Windows launcher
app.py                        Compatibility launcher for main.py
config/                       Environment configuration and limits
backend/                      Workspace, research, evidence, document, job,
                              source preview, timeline, brief and API services
core/                         Existing retrieval/generation plus automatic OCR,
                              evidence graph and conservative date extraction
database/store.py             SQLite data access and corpus persistence
database/migrations.py        Additive v2 schema and backup
ui/layout.py, theme.py         Shared navigation and design system
ui/pages/                     Home, AI Research and My Research only
ui/source_viewer.py            Local page navigation and honest highlighting
ui/research_components.py      Findings, citation actions, saving and export
utils/                        Cited Markdown and PDF report exports
evaluation/                   Reusable CLI metrics/experiments and protocol
tests/                        Original and v2 regression/integration tests
scripts/                      Migration, OCR fixtures, browser and live checks
data/                         Ignored private runtime data and validation artifacts
```

## Troubleshooting and current boundaries

| Issue | Recovery |
| --- | --- |
| Gemini key/model/quota failure | Verify `.env` model access in AI Studio, allow connectivity, check quota, then restart/retry. Search and OCR remain local. |
| First local model download fails | Allow the Hugging Face download once, check disk space/proxy, then retry. Complete cached snapshots are reused locally. |
| One scanned page cannot be read | Inspect its original image and extraction warnings. Other readable pages remain indexed. Retry processing after checking OCR health or supply a clearer scan. |
| PDF uses an unsupported script | Use a suitable tested RapidOCR recognition model or obtain a searchable text PDF. Do not assume English tests validate all Indian languages. |
| App closed during indexing | The persisted job is marked interrupted. Choose Try again on Home; partially committed embeddings are not used. |
| Source no longer opens | Restore the missing original or remove/re-upload it. Saved runs with changed source IDs require fresh research. |
| FAISS corruption | Search rebuilds it from SQLite vectors. Restore SQLite/uploads from backup if the authoritative data is damaged. |
| Port 8080 is occupied | Change `LEXIRAG_PORT` and restart. |
| Browser connection lost | Reload; saved workspace history, evidence and briefs persist. An already submitted model request may finish server-side. |

Default extraction heuristics can miss difficult scans; OCR and legal interpretation still need review. Background cancellation is cooperative rather than instant. Native/line-region highlighting is honest about its precision. Exact quote provenance is checked automatically; semantic correctness still requires review. The project has no production-scale concurrency or general Indian-law benchmark claim. Specialist backend modules remain available for code/CLI use, with no corresponding application screens.

Maintained API references: [NiceGUI](https://nicegui.io/documentation), [RapidOCR public usage](https://rapidai.github.io/RapidOCRDocs/main/install_usage/rapidocr/usage/), [PyMuPDF4LLM](https://pymupdf.readthedocs.io/en/latest/pymupdf4llm/), [LangChain Gemini](https://docs.langchain.com/oss/python/integrations/chat/google_generative_ai), [Ragas faithfulness](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/).
