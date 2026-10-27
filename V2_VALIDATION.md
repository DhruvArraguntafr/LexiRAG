> Historical record from before the three-section refactor. UI routes and commands here may refer to removed screens or scripts. See [README.md](README.md) and [REFACTOR_VALIDATION.md](REFACTOR_VALIDATION.md) for the current app.

# LexiRAG 2.0 — validation and delivery

Validated on **25 October 2026**, Windows, Python 3.11.9. The original RAG architecture and v1 entry point are preserved. The primary application is now `main.py` with NiceGUI/FastAPI in one local process.

## Automated results

- **80 pytest tests passed** in the final regression run, including the original tests and new v2 backend/OCR coverage. The obsolete test requiring a Tesseract error was updated to test automatic OCR failure recovery.
- `compileall` passed for the application, backend, core, database, UI, reports, evaluation, scripts and tests.
- `pip check` reported **no broken requirements**.
- Real Edge/Chromium browser smoke testing rendered all **10 routes**, with both empty and populated research states.
- The live browser/Gemini workflow passed **13 checks**, with no mocked model responses or browser JavaScript errors.
- After a server restart, browser checks verified persisted workspaces, saved conversations and briefs; rich-text edit/save/reload/download; evidence notes/tags; an explicitly annotated graph relationship; a manual timeline entry; Ctrl+K search; and desktop/tablet/phone layouts. No browser JavaScript errors were observed.
- A final browser drag/drop event on the actual uploader overlay queued the original native PDF again, completed successfully, and retained four distinct documents without re-embedding the duplicate.

Exact packages are in `requirements-lock.txt`: NiceGUI 3.18.0, RapidOCR 3.10.0, ONNX Runtime 1.31.0, PyMuPDF 1.28.2, PyMuPDF4LLM 0.3.4, plus the retained LangChain/Gemini/FAISS/BM25/Ragas stack.

## Genuine OCR verification

No `Advisory-7.pdf` was found in the project, including ignored/hidden project files outside the environment/model cache. Its absence was not substituted with a claim that the original failure was reproduced.

Representative files were generated from known teaching text and actually uploaded through the new browser interface:

| Fixture | Original PDF pages | Expected extraction | Result |
| --- | ---: | --- | --- |
| Native-Teaching.pdf | 2 | Native text | Passed |
| Scanned-Teaching.pdf | 2 | Raster-only pages; no native text | Actual RapidOCR/ONNX text recognized on both pages |
| Mixed-Teaching.pdf | 2 | Native first page; raster second page | Correct method selected independently on each page |
| Incomplete-Text.pdf | 1 | Native header over an image body | Automatic OCR recovered the body rather than indexing only the header |

The persisted test library has **7 original pages: 3 native and 4 RapidOCR**, including **21 OCR line boxes**. All four documents contain usable indexed content. The raster fixtures' native `get_text()` output was independently confirmed empty. The real recognition tests matched known text such as “thirty days” and checked bounding boxes against original PDF dimensions.

Startup health uses a rendered “LEGAL OCR READY 2026” image and verifies actual recognition, rather than only checking whether a package imports. The default workflow succeeded without a Tesseract installation or mandatory `TESSDATA_PREFIX` configuration.

A live Gemini answer cited the **Scanned-Teaching.pdf** notice clause. Clicking that citation opened the original image-only PDF at **file page 1**, with the recognized line region highlighted. The rendered original and quotation were visually inspected and matched. Highlighting is explicitly labeled an OCR **line region**, not exact character-level ground truth.

Isolated failure tests also forced OCR to fail on the scanned page of a mixed document: the native page remained searchable, the failed page retained its original number and unreadable warning, and the document was marked partially processed. Retry, failed-ingestion rollback, safe cancellation and index recovery were tested. Duplicate uploads retain extraction warnings and do not regenerate embeddings.

## Live workflow results

The isolated browser test corpus is in `data/v2-validation/corpus/`; the user's main library was not populated with fixtures. The configured **gemini-3.5-flash-lite** model made real generation requests.

| Check | Actual result |
| --- | --- |
| Scanned-PDF legal question | Two accepted cited findings correctly described the 30-day notice and payment obligation. Sources came only from the selected scanned document. |
| Citation inspection | Original page opened beside the answer; OCR coordinates highlighted the quoted source line. |
| Save finding/evidence | Findings and exact supporting passages persisted in SQLite. |
| Context-aware follow-up | “What about the second document?” resolved the displayed selected source order and retrieved fresh native-document evidence, excluding earlier AI prose as evidence. |
| Unsupported authority | The nonexistent Supreme Court ruling question returned insufficient evidence, no findings, and explicit limitations. |
| Document comparison | Independent retrieval produced a comparison citing two selected sources; both original previews opened side by side. |
| Evidence graph | Saved question/finding/evidence/document nodes rendered. A real SVG node click opened its details and source action. Later a user-annotated relationship was saved through the browser. |
| Source timeline | Seven explicit source events were extracted. A separate manual entry was added and clearly labeled. |
| Research brief | Selected findings were assembled with source references, edited, saved and exported through an actual browser PDF download. |
| Reopening research | Conversations, findings and brief edits survived page reloads, new service instances and a server restart. |
| Document summary | The document-library summary action invoked Gemini and persisted an accepted cited summary. |
| Guided evaluation | A labeled dataset ran semantic, hybrid and reranked methods; measured results, charts and JSON were saved. |
| Responsive UI | Desktop, tablet at 768 px and phone at 390 px were checked. The tablet overlay found in an early screenshot was corrected; final layouts showed no horizontal overflow or automatic drawer obscuring the page. |

The final brief editor supports rich text, Markdown and preview. Heading sizes and editor proportions were refined after visual inspection. PDF export retains readable headings, quotations, original-page references and review notes. The earlier raw-Markdown/orphan-heading export issues remain fixed.

## Measured retrieval experiment

Four supported questions were authored for the known teaching notice clause in each fixture, with explicit gold chunk IDs. K=3, three retrieval methods, **12 actual measurements**. Labels describe synthetic fixture clauses; there was no independent human annotator.

| Method | Precision@3 | Recall@3 | MRR | Mean retrieval seconds |
| --- | ---: | ---: | ---: | ---: |
| Semantic | 0.3333 | 1.0000 | 1.0000 | 0.0432 |
| Hybrid | 0.3333 | 1.0000 | 1.0000 | 0.0399 |
| Hybrid + reranking | 0.3333 | 1.0000 | 1.0000 | 0.2079 |

One gold relevant chunk among three results explains precision=1/3. No accuracy improvement from reranking was measured on this small corpus. Latency depends on hardware/cache state. Faithfulness, semantic citation correctness and aggregate rejection rates were **not measured** in this retrieval experiment; their values remain null. The individual unsupported-question check is a functional result, not a general rejection-rate benchmark.

## Preserved behavior and new integrity checks

The original source archive excludes credentials. `app.py` and the v1 UI/tests remain available. Additive migration tests verified that original document/chunk IDs, vector bytes and corpus revision survive migration; a pre-v2 database backup is created. Workspace searches reject an empty scope instead of falling back to the entire library. Stale saved research/briefs are blocked when their source chunks or memberships change. Original PDFs are not modified by preview highlights.

Background processing keeps the event loop available, tracks real page/batch progress, marks interrupted jobs for retry, and supports safe cancellation at stage boundaries. Reset waits for ingestion cancellation before clearing active data, then permits new uploads again. A complete cached embedding/reranker snapshot is preferred locally, avoiding repeated Hub probes and concurrent duplicate model initialization.

## Artifacts and screenshots

The following are actual browser captures of synthetic test research:

- [Home](docs/screenshots/home.png)
- [Dark theme](docs/screenshots/dark-home.png)
- [Scanned-PDF answer and highlighted evidence](docs/screenshots/research-ocr.png)
- [Interactive evidence graph](docs/screenshots/evidence-graph.png)
- [Rich research-brief editor](docs/screenshots/brief-editor.png)
- [Measured evaluation charts](docs/screenshots/analytics.png)
- [Phone layout](docs/screenshots/phone.png)

Private local validation outputs:

- [Downloaded research brief PDF](data/v2-validation/LexiRAG-v2-live-brief.pdf)
- [Browser smoke results](data/v2-validation/browser-results.json)
- [Live workflow results](data/v2-validation/live-results.json)
- [Restart/editor/annotation checks](data/v2-validation/restart-results.json)
- [Final visual and drag/drop check](data/v2-validation/final-browser-results.json)
- [OCR fixture generator](scripts/create_ocr_fixtures.py)

The published screenshot copies contain only generated teaching material and validation workspace data. Full runtime libraries and raw validation files remain under ignored `data/`.

## Remaining limits

- There is no authentic Indian-law quality benchmark or independent human labeling study. No improvement over a general LLM is claimed; the optional general-LLM baseline was not added.
- English OCR was genuinely tested. Other Indian scripts, handwriting, difficult stamps, very poor scans and arbitrary-language PDF shaping are not validated. A clearer source or specialized model may be required.
- Highlighting is native text or recognized line regions; exact character-level highlights are not promised.
- PyMuPDF4LLM layout assistance is conservative; complex tables/columns may still need source inspection.
- The graph represents saved evidence and explicit annotations, not a complete statutory/judicial citation network. “Potentially contrary” does not certify contradiction or overruling.
- Timeline event roles are conservative textual labels; ambiguous numeric dates and unsupported commencement/applicability inferences are omitted.
- Rich text supports common document formatting, not full Word-style layout fidelity. User edits require review before relying on the brief.
- Cancellation is cooperative. In-flight OCR/model calls are allowed to finish. No production-scale load, multi-user isolation or public deployment hardening is claimed.
- Live Ragas quality judging was not rerun; the actual Ragas/Instructor adapter remains covered by isolated integration tests with mocked external judge responses.

## Launch

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

Open **http://127.0.0.1:8080** or use `launch.bat`. The existing `.env` key and model remain configured. No separate backend terminal or Tesseract setup is needed.
