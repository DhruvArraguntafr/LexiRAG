# Three-section refactor validation

Validated on 27 October 2026, Python 3.11 on Windows.

## Result

The application has exactly **Home, AI Research and My Research**. The dedicated
Compare Documents screen, its advanced predecessor, navigation item, page imports,
page registration, comparison-specific CSS and `ResearchService.compare` entry
point are removed. Old tool URLs, including `/comparison`, return to Home.
There is no comparison API endpoint.

## Removed and simplified

- Removed 22 obsolete source/config/test files: ten inactive NiceGUI page modules
  (including both comparison screens), the two Streamlit presentation modules,
  the unused rich editor converter, Streamlit configuration, seven obsolete
  browser/validation scripts and the Streamlit-only UI test module.
- Replaced the old `app.py` implementation with a compatibility launcher for the
  current app. Both `python main.py` and `python app.py` launch the same UI.
- Removed unreachable result-rendering branches and the dead workspace-creation
  dialog and page helpers. Kept one result renderer for answers and saved history.
- Removed unused imports, formatted the shared research dispatch, and documented
  why shared multi-document retrieval and historical result fields remain.
- Removed Streamlit and pandas as direct application requirements, moved pytest
  to development requirements, and declared FastAPI directly because the backend
  imports it. Pruned eight obsolete pins from the full environment lock:
  Streamlit, Altair, PyDeck, watchdog, jsonschema, jsonschema-specifications,
  referencing and rpds-py. Other dependencies and versions are unchanged.
- Updated README, evaluation instructions, navigation tests, API checks and
  multi-document research tests. Earlier validation documents are marked as
  historical, and their evidence remains available.
- Added isolated browser-server orchestration, data-preservation verification,
  historical result/export coverage, and a copied-library workflow checker.

The removed Streamlit tests covered nine obsolete UI cases; one test for the
removed editor converter was also retired. The added history compatibility test
brings the current suite to 149 tests. Browser checks exercise the actual current
NiceGUI interface instead of the removed Streamlit interface.

## Preserved

- FAISS + BM25 hybrid retrieval, reciprocal rank fusion, semantic/keyword modes,
  exact legal-provision retrieval, neighboring passages, bounded recovery,
  document/workspace/metadata filters and cross-encoder support.
- Gemini integration, structured output, untrusted-evidence instructions,
  exact quotation validation, unsupported-finding rejection and refusal behavior.
- PDF validation, automatic RapidOCR, native/mixed/scanned processing, partial-page
  recovery, original PDF viewing and citation highlighting.
- Saved findings, research history, summaries, Markdown/PDF exports, saved reports,
  persistence, workspace isolation, transactions, locks and index recovery.
- Existing visual design, keyboard actions, global search, responsive navigation,
  light/dark themes and mobile layouts.

AI Research already used the core multi-document analysis engine. That shared
engine remains because removing it would change existing research behavior and
weaken paired citation coverage. It is reachable through AI Research only, with
no dedicated comparison screen or service entry point. Historical
`comparison_rows` serialization and report rendering remain compatible.

No schema migration, document deletion, reindexing, embedding regeneration or
rewriting of existing research records was performed on the original library.
Retained backend graph/timeline/brief capabilities and their stored records were
not removed simply because they have no current page.

## Checks performed

| Check | Result |
| --- | --- |
| Before-change regression suite | 158 passed |
| Current regression suite | 149 passed |
| Python compilation and local import targets | Passed |
| Installed dependency consistency (`pip check`) | Passed |
| Real embedding, FAISS, BM25, hybrid and cross-encoder smoke | Passed |
| Real browser upload, including drag/drop and scanned OCR | Passed |
| Real Gemini answer, exact citations and original PDF viewing | Passed |
| Save finding, answer export, selected-findings report and re-download | Passed |
| Reopen history, cited summary and unsupported-question refusal | Passed |
| Exactly three sections, removed-route redirects and both launchers | Passed |
| Light/dark themes and all three mobile layouts | Passed; no browser errors |
| New history and report reopened in a fresh process | 3 readable runs, 1 valid finding, 1 report exported |
| Real legal provision in a copy of the existing library | Rule 5(7), Direct Selling Rules 2021; 3 verified citations |
| Real multi-document AI Research | Complete paired finding, 2/2 verified citations, both PDFs covered; unsupported control rejected |
| Existing data file hashes | All 254 files unchanged |
| Existing SQLite records | Every row in all 15 tables unchanged |
| SQLite integrity / foreign keys | `ok` / no violations |

Unit/integration coverage includes corrupt PDFs, failed OCR pages, cancellation,
retry, workspace scoping, stale sources, migrations, vector-store recovery,
fabricated citations, provider failures, legal-reference continuation and
cross-encoder fallback. The dedicated historical compatibility test confirms that
a valid old comparison can be reopened after restart, saved as a finding and
exported as a cited PDF.

The first sandboxed Gemini attempt was blocked by Windows socket permissions.
Live checks succeeded after network access was approved. No application security
or error-handling changes were needed. A historical Rule 4(5) verifier was not
applicable to this library: it contains the 2021 E-Commerce amendment rather than
the 2020 Rules. The real-library check instead used Rule 5(7) of the uploaded
Direct Selling Rules.

## Pre-existing history limitation

The original library contains four PDFs, 281 chunks, 39 page records, 73 past
research runs, seven saved findings and four saved reports. The past runs and
reports refer to documents no longer in that library: all 73 old runs are blocked
by the existing stale-source checks, all seven old findings have invalid source
links, and all four old reports are blocked from export.

The archived **before-change code produces the same results** against a copy of
the baseline database. This is pre-existing data state, not a refactor regression.
All records and original file bytes are preserved. Source validation was not
bypassed, and citations were not remapped to unrelated current documents.

## Reproduce and inspect

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m scripts.smoke_local
# Fresh, isolated server + actual browser; --live calls configured Gemini:
.\.venv\Scripts\python.exe -m scripts.check_application --directory refactor-validation/new-check --live
# Verify the original before-change manifest, without modifying the library:
.\.venv\Scripts\python.exe -m scripts.check_preservation verify
```

Private artifacts are under the ignored `refactor-validation/` directory:

- `source-before.zip`: source/configuration backup without credentials.
- `before.sqlite3`, `data-before.json`, `preservation.json`: baseline and audit.
- `pytest.xml`: current regression results.
- `browser-live/results.json`, screenshots and downloaded PDFs: real browser evidence.
- `existing/results.json`, `existing/real-provision-report.pdf`: copied-library checks.
- `restart/results.json`, `baseline-history.json`: restart and pre-existing stale-source evidence.
- `multidoc-results.json`: real Gemini paired-citation and unsupported-control checks.
- `changes.json`, `dependencies-removed.txt`: detailed cleanup inventory.

Earlier runtime data, backups, validation artifacts, models, indexes and uploads
under `data/` remain untouched. Application architecture and frameworks are unchanged.
