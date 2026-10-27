> Historical record from before the three-section refactor. UI routes and commands here may refer to removed screens or scripts. See [README.md](README.md) and [REFACTOR_VALIDATION.md](REFACTOR_VALIDATION.md) for the current app.

# Live workflow checklist — 8/8 passed

**Latest cross-document validation (25 October 2026):** the historical checklist
below is unchanged. The new comparison pipeline completed 10/12 real Gemini runs
on six topics; two remained partial under strict evidence checks. Four-page
browser/source/report checks passed. See [CROSSDOC_VALIDATION.md](CROSSDOC_VALIDATION.md)
for actual retrieval measurements, held-out questions and remaining failures.
Manual review also found a misleading scope interpretation in the separate
browser-exported report; passing citation and UI checks do not establish legal accuracy.

Completed on 24 October 2026 using the configured **gemini-3.5-flash-lite** model and actual local Sentence Transformer, FAISS, BM25 and cross-encoder models. All eight workflows were driven through **Streamlit AppTest UI interactions**, with no Gemini response mocks. The unit/regression suite also passed: **60 tests**.

Two clearly labeled synthetic teaching agreements were uploaded into a separate test library under `data/live-checklist/corpus/`. The main application's library was not modified. These checks demonstrate application behavior on controlled contractual text; they are not a benchmark of Indian-law accuracy.

| Check | Outcome | Evidence |
| --- | --- | --- |
| Upload multiple PDFs | Passed | Uploaded both PDFs in one UI batch; both visible in the library; 4 original pages and 12 chunks persisted in SQLite and FAISS. |
| Ask a legal question | Passed | A real Gemini response correctly stated Agreement A's 30-day written notice and continuing liability for completed services; 2 verified citations. |
| Inspect citations | Passed | Opened the original source viewer, navigated pages, and independently matched every research quotation against the actual cited PDF page. |
| Compare two documents | Passed | Two comparison findings cited both selected PDFs; correctly distinguished 30-day and 60-day notice and the wording about completed-service fees; 4 verified citations. |
| Generate a summary | Passed | Real Gemini summary contained 6 requested headings and 10 verified citations, all from Agreement A. Express dates matched the document. |
| Test an unanswerable question | Passed | Asked for a nonexistent Supreme Court judgment invalidating the agreements. Gemini returned `insufficient_evidence=true`, no findings, and explicit limitations even though passages were retrieved. |
| Export a research report | Passed | Opened a real 2-page PDF, verified both document names and file-page citations, checked text bounds, and visually inspected both rendered pages. Fixed raw Markdown labels and an orphan evidence heading found during inspection. |
| Run retrieval evaluation | Passed | Uploaded 9 questions to the UI, ran semantic/hybrid/hybrid-with-reranking retrieval, and verified 27 saved per-question measurements plus visible results tables/charts. |

## Measured retrieval results

Eight supported questions had explicit gold labels for known fixture clauses, reviewed against their source documents. One additional question was explicitly unsupported. Gold labels were authored for these fixtures; there was no independent human annotator. Every supported question had one gold relevant chunk, with K=3. Unsupported questions are excluded from relevance metric averages.

| Method | Precision@3 | Recall@3 | MRR | Mean retrieval seconds |
| --- | ---: | ---: | ---: | ---: |
| Semantic | 0.3333 | 1.0000 | 0.8542 | 0.1319 |
| Hybrid | 0.3333 | 1.0000 | 0.9375 | 0.1090 |
| Hybrid + reranking | 0.3333 | 1.0000 | 0.9167 | 0.4442 |

These are actual results from this small controlled run. A precision of 1/3 reflects one relevant labeled chunk among three returned results. Latencies depend on hardware, cache state and corpus size. Reranking did not outperform hybrid on this fixture set. Retrieval evaluation did not request answer-quality judging; faithfulness and citation-correctness metrics remain unmeasured in that experiment. The separately tested unsupported question passed as one live functional check, not an estimated general rejection rate.

## Review artifacts

- [Exported research PDF](data/live-checklist/LexiRAG-live-research-report.pdf)
- [Research answer with source passages](data/live-checklist/research-answer.md)
- [Comparison with citations](data/live-checklist/comparison.md)
- [Document summary](data/live-checklist/summary.md)
- [Unanswerable-question response](data/live-checklist/unsupported-answer.json)
- [Machine-readable checklist](data/live-checklist/checklist.json)
- [Retrieval experiment](data/live-checklist/retrieval-experiment.json)
- [Labeled questions](data/live-checklist/labeled-questions.jsonl)
- [Gold passage labels and source text](data/live-checklist/gold-label-review.json)
- [Original cited page preview](data/live-checklist/cited-source-page.png)
- [Report page 1](data/live-checklist/report-page-1.png), [report page 2](data/live-checklist/report-page-2.png)

These local artifacts are excluded from version control by `data/` ignore rules. The summaries and responses reflect this particular model run; subsequent generations may differ.

## Reproduce

```powershell
.\.venv\Scripts\python.exe -m scripts.check_live_workflows
.\.venv\Scripts\python.exe -m pytest -q --tb=short
```

The live runner requires the existing Gemini key, makes real API calls, and uses already cached local model weights. It exercises multi-file upload, chat, source viewer, comparison, summary, refusal, the PDF export code used by the UI, and evaluation. An alternative isolated directory can be passed with `--output-dir`. AppTest automates Streamlit widgets and rendering; browser-engine layout and OS download dialogs were not automated. Original PDFs and exported report pages were also rendered and visually inspected separately.
