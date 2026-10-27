> Historical record from before the three-section refactor. UI routes and commands here may refer to removed screens or scripts. See [README.md](README.md) and [REFACTOR_VALIDATION.md](REFACTOR_VALIDATION.md) for the current app.

# Simplified interface validation

Validated on Windows with Python 3.11.9. The existing backend, local models, database schema and automatic RapidOCR workflow are retained.

## Automated checks

- `python -m pytest -q --tb=short`: **91 passed** (80 existing tests plus 11 checks for the simplified flow).
- `python -m compileall -q main.py app.py config core backend database evaluation ui utils scripts tests`: passed.
- `python -m pip check`: no broken requirements.
- New tests verify exactly four primary destinations, retained advanced routes, automatic first-collection creation, adoption of a legacy library, repeated-use behavior, collection isolation and plain-language upload progress.
- Restarted the main app at `http://127.0.0.1:8080`: health endpoint passed; all four primary pages rendered in Edge; Advanced was collapsed; no browser errors. The main library was retained.

## Actual browser and provider checks

`scripts/check_simple_ui.py --live` passed using actual Microsoft Edge, the configured Gemini model, local Sentence Transformer embeddings, FAISS/BM25 and RapidOCR. No generation mocks were used for these checks. The server used an isolated library under `data/simple-ui-check/corpus`; the main library was not populated or cleared.

| Flow | Observed result |
| --- | --- |
| First visit | Four primary links visible; optional Advanced tools collapsed. Example question fills the large Home question box. |
| Upload | A genuine browser drag/drop plus multiple file selection prepared three teaching PDFs in one automatically created collection. |
| Automatic scan reading | The raster-only PDF produced actual OCR page records and usable passages without processing choices or Tesseract setup. |
| Ask from Home | The question navigated to AI Research, invoked Gemini and persisted a new answer. |
| Citations | Displayed quotations matched retrieved passages. Clicking a citation loaded a highlighted original page; the original-PDF link returned a PDF with a page anchor. |
| Save | The finding was saved in SQLite and appeared in My Research; the button changed to Saved. |
| Compare | Two explicitly selected PDFs produced a comparison table and findings with citations to both sources. The teaching agreements required thirty and sixty days respectively. |
| Report export | The comparison PDF downloaded. Selected saved findings produced a readable report with source references and PDF page numbers. The saved report downloaded again from Reports. |
| History | A saved comparison reopened from Past questions with its evidence and export action. |
| Summary | Home's Summarize button generated a new persisted, cited document summary. |
| Unsupported question | A question about a nonexistent future Supreme Court decision produced an insufficient-evidence answer. |
| Navigation | All four primary routes and ten optional routes rendered successfully, with no browser JavaScript errors. |
| Responsive layout | Light/dark Home views and all four primary pages at 390-pixel phone width rendered without horizontal page overflow. |

Actual artifacts are retained privately in `data/simple-ui-check/`: `results.json`, screenshots, synthetic PDF fixtures, downloaded reports and the test corpus. Public screenshots of these teaching fixtures are in `docs/screenshots/simple/`.

## Boundaries

These are functional regression checks on explicitly synthetic teaching agreements, not an Indian-law accuracy benchmark. They do not establish legal correctness, amendment currency, judicial treatment, multilingual OCR quality, large-corpus performance or production security. Earlier backend/evaluation validation remains documented in `V2_VALIDATION.md`; the earlier Streamlit application and its tests are preserved.

The first sandboxed Gemini check could not reach the provider. Live checks passed after the test server received network access. Credentials were not printed, copied into tests or changed by this interface update.
