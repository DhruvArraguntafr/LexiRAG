> Historical record from before the three-section refactor. UI routes and commands here may refer to removed screens or scripts. See [README.md](README.md) and [REFACTOR_VALIDATION.md](REFACTOR_VALIDATION.md) for the current app.

# Implementation validation

**Current cross-document update:** 158 regression tests passed; 12 real Gemini
comparison runs across six topics completed 10 answers and correctly retained
two partial results. Every displayed quotation verified against its stored source.
Four-page browser, source-viewer, save and report-export checks passed; original
documents and saved records were preserved. Measurements and remaining failures
are in [CROSSDOC_VALIDATION.md](CROSSDOC_VALIDATION.md), including a misleading
scope interpretation found during manual report review despite valid quotations.

**Current Rules retrieval repair:** 142 tests passed. The actual complaint-deadline question now succeeds with Rule 4(5), 48 hours and one month, supported by original PDF page 4. A separate consent question and the fresh browser/source/report check passed. No OCR replacement or reindex was needed; existing data and the four-page UI were preserved. See [RULE45_VALIDATION.md](RULE45_VALIDATION.md). Earlier comparison and retrieval results remain historical evidence.

Validated on Windows with Python 3.11.9. Exact package versions, including optional evaluation dependencies, are captured in `requirements-lock.txt`.

## Completed checks

- `python -m pytest -q --tb=short`: **60 passed**, including the PDF formatting regression check.
- `python -m compileall -q app.py config core database evaluation ui utils scripts tests`: passed.
- `python -m pip check`: no broken requirements.
- Streamlit server launched at `http://127.0.0.1:8501`; `/_stcore/health` returned HTTP 200 with `ok`.
- AppTest exercised all eight workspace routes, a keyword query against a populated library, and original-PDF page rendering.
- `python -m scripts.smoke_local` passed with the actual downloaded `all-MiniLM-L6-v2` embedding model and `ms-marco-MiniLM-L6-v2` cross-encoder. It exercised real FAISS, BM25, hybrid RRF and reranking on temporary synthetic teaching PDFs.
- Ran the CLI ingestion and three-mode evaluation workflow on generated teaching agreements in `data/verification/`, using the actual model weights. Experimental JSON is saved under that private verification directory. This is a workflow check on fictional agreements, not a legal-research benchmark. The main application library remains empty until the user uploads documents.
- Native Gemini structured-output chain construction passed without making an API request.
- Real Ragas collections and Instructor async adapter were exercised end to end against mocked HTTP responses from the Gemini-compatible endpoint, including repeated scoring to verify client/event-loop lifecycle.

## Live user checklist

**8/8 passed** using actual Gemini calls, real cached local models and Streamlit AppTest UI interactions. Uploaded two synthetic teaching PDFs into an isolated test library; checked a cited answer, original-page quotations and navigation, two-document comparison, six-part cited summary, evidence-insufficient refusal, readable PDF export, and all three retrieval evaluation modes. No Gemini response mocks were used for these eight checks. The main library was not modified.

See [LIVE_TEST_RESULTS.md](LIVE_TEST_RESULTS.md) for each outcome, actual measured scores, artifact links, labeling provenance and the reproducible runner. The exported report was visually inspected and formatting issues corrected. This validates controlled workflows, not general legal accuracy.

## Tests cover

PDF page/section preservation, invalid/blank/password-protected/scanned PDFs, OCR error handling, page/size limits, failed-ingestion rollback, duplicate detection, file/hash safety, persistent and corrupted FAISS recovery, filtered semantic search, BM25/RRF behavior, reranker failures, document and bulk deletion, missing API keys, provider-error redaction, invalid citation removal, independent comparison retrieval, hierarchical summary coverage, readable PDF reports, metric definitions, invalid/stale dataset rejection and UI navigation.

## Not live-tested

- Broad Gemini answer quality, quota boundaries and live Ragas judging: live Gemini access and the four generation workflows now pass on the teaching fixtures. General answer quality and live Ragas faithfulness/citation-support scoring still require a larger evaluation; Ragas integration unit tests use mocked external judgments.
- Real Tesseract OCR: scanned-PDF detection and OCR-failure handling were tested, but local OCR output quality requires an installed engine/language pack and representative scans.
- Indian-law retrieval accuracy, amendment currency, judicial-treatment status and semantic correctness of legal explanations: require authentic documents, manually labeled held-out questions and human review. No scores for these are fabricated.
- Large-corpus concurrency/load testing and multilingual export shaping: the application targets trusted local academic use, with English-focused default embedding/reranking models.
