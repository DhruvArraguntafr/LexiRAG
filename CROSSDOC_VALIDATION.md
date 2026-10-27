> Historical record from before the three-section refactor. UI routes and commands here may refer to removed screens or scripts. See [README.md](README.md) and [REFACTOR_VALIDATION.md](REFACTOR_VALIDATION.md) for the current app.

# Cross-document retrieval and comparison validation

Validated on 25 October 2026 against the existing local Consumer Protection Act,
Consumer Protection (E-Commerce) Rules and Advisory-7 PDFs. The four-page NiceGUI
interface, OCR engine, SQLite schema and uploaded files were preserved.

## What caused the unreliable comparisons

AI Research previously sent comparison questions through the ordinary shared
retrieval pool. It did not guarantee independent evidence from each selected
document. The dedicated comparison route searched per document, but its main
query remained the entire comparison question: instrument names, definitions and
institution names could outrank the actual duties or procedures requested.
Quotation verification checked provenance, but separate summaries could still
be presented as a completed comparison without a joint finding.

This was a retrieval, context-allocation and answer-coverage problem. No missing
OCR pages or missing index records were discovered in this investigation; no
re-extraction or reindexing was needed.

## Implemented behavior

- `core/comparison_plan.py` detects comparison language and derives bounded
  concept subqueries before keyword cleanup. Document aliases come from names
  and first-page titles. Unique shorthand references resolve only within the
  allowed document selection. The planner contains retrieval vocabulary, not
  legal answers, statutory numbers or question-specific responses.
- `core/comparison_retriever.py` runs the existing FAISS, BM25, RRF and legal
  reference lookup independently for every selected PDF and concept. Explicit
  reference matches remain protected even when later expansion queries retrieve
  the same chunk again. Document and metadata filters remain in force.
- The local cross-encoder reranks candidates by concept. A majority of negative
  anchor logits triggers one bounded expanded search; these scores are only a
  search hint, not calibrated probabilities or evidence that an answer is absent.
  Related terminology, shorter procedural queries and adjacent page/provision
  context help recover operative passages. Model failures fall back to scoped
  hybrid retrieval.
- Context space is reserved per document, with interleaved source labels. Context
  never imports a passage from an unselected document. Any clipped passage remains
  a contiguous substring of the original stored chunk with its original page.
- `core/document_comparison.py` asks for joint issue-based findings. It retries
  once with expanded evidence when citations, paired findings or coverage are
  insufficient. Single-source comparative claims are withheld. Valid joint
  findings can remain usable after an unsupported extra claim is removed.
  Separate summaries alone remain explicitly incomplete.
- `backend/research_service.py` routes comparison questions in AI Research
  through the same comparator used by Compare Documents. No new UI controls were
  introduced. Existing immutable excerpt selection and strict quotation/page
  validation remain in place.

Private diagnostics record questions, subqueries, scope, IDs, pages, scores and
expansion/reranking status; they do not record PDF text. The standalone live
verifier uses its own diagnostic directory to avoid Windows log rotation
conflicts with the running application.

## Measured retrieval results

Four newly declared topic questions were frozen before the implementation:
product information, complaint redress, defective-goods refunds, and consent
versus self-audits. Labels refer to actual existing chunk IDs. The baseline was
captured before replacing the old comparator. Evaluation uses eight anchors per
question: four per selected PDF for per-document methods, eight total for the
shared-pool baseline. Adjacent context sent to Gemini is excluded from these
anchor metrics. Metrics are macro-averages across the four questions.

| Method | Labelled precision | Labelled recall | Per-document MRR | Documents with a labelled hit |
| --- | ---: | ---: | ---: | ---: |
| Previous shared-pool hybrid | 0.5000 | 0.5491 | 0.6875 | 0.7500 |
| Previous dedicated comparator | 0.4375 | 0.4777 | 0.6563 | 0.8750 |
| New planner, hybrid, recovery disabled | 0.4375 | 0.4777 | 0.6250 | 0.7500 |
| Same planner with cross-encoder, recovery disabled | 0.5000 | 0.5491 | 0.6875 | 0.8750 |
| New automatic comparison, including weak-evidence recovery | 0.5313 | 0.5804 | 0.6875 | 0.8750 |

Thus reranking improved labelled recall from 47.8% to 54.9% with recovery disabled;
automatic recovery brought it to 58.0%. It did **not** improve every question.
Consent/self-audit labelled recall remained 71.4%, below the shared-pool
baseline's 100%; its first-hit rank also regressed with reranking. All methods
returned chunks from both PDFs in this small set, which by itself does not
establish relevant coverage. The redress case still missed the frozen positive
Act labels among its top four anchors, although later context included actual
Section 38 procedure on original PDF page 19.

These labels are not exhaustive; some unlabelled passages are legally relevant.
This is a small development validation set used to assess the reranking choice,
not a blinded legal benchmark or a measure of legal correctness.

Both local models were warmed before the final measurement. Mean observed
retrieval wall times were 2.19 s shared hybrid, 2.15 s planned hybrid, 8.10 s
planned reranked, and 14.70 s automatic recovery. Other validation jobs were
running on the same CPU, so these are observed timings, **not** isolated speed
benchmarks. Cold-start/model-download time is additional. The stronger retrieval
path has a measurable latency cost.

## Real Gemini results

Used the configured `gemini-3.5-flash-lite` with actual PDF passages, real cached
embedding and cross-encoder weights, and no generation mocks. Each question was
run through both public research service routes.

| Topic | AI Research | Compare Documents |
| --- | --- | --- |
| Product information and disclosure | Complete; 1 joint finding | Complete; 2 joint findings |
| District Commission and grievance redress | **Partial**; separate supported findings only | Complete; 1 joint finding |
| Defective goods, returns and refunds | Complete; 3 joint findings | Complete; 1 joint finding |
| Consent, dark patterns and self-audits | Complete; 3 joint findings | Complete; 2 joint findings |
| Misleading advertising and responsibility — held out | **Partial**; invalid citation withheld | Complete; 4 joint findings |
| Personal-information disclosure versus purchase consent — held out | Complete; 1 joint finding | Complete; 1 joint finding |

The last two questions were declared after the production comparison behavior
was frozen, run once on each route, and not used to tune answers or retrieval.
They have no invented relevance labels or retrieval scores. A later unit-tested
score-marker preservation fix concerns explicit numbered-reference expansion;
neither held-out question contains an explicit numbered reference.

**10/12 completed; 2/12 remained safely partial.** Every run retrieved and cited
both selected PDFs. Of 111 attempted references in the final returned runs, 110
verified; the invalid reference was withheld. Every displayed quotation was
independently matched to its actual stored chunk, document and PDF page. These
counts exclude discarded earlier generation attempts during recovery.

Two unsupported controls asking for a nonexistent uploaded Supreme Court
overruling judgment were both rejected with zero findings. Spot review of the
redress comparison confirmed Act Section 38 on PDF page 19 and Rules 4(5) on PDF
page 4; the latter supports 48-hour acknowledgment and one-month redressal.

Remaining failures are real: AI Research's redress run still produced separate
findings after bounded recovery, and the held-out advertising run still attempted
one invalid citation. No further model retries were used to select a prettier
result. Valid provenance and paired citations are structural checks, not a
guarantee of entailment, legal completeness or current law.

Manual inspection of the additional browser-driven **scope** report found a
semantic error beyond the twelve topic runs: a heading/claim described exclusion
of personal, non-commercial activities as shared, although its own Act citation
concerns exclusion of commercial-purpose purchases (with an exception for
self-employment livelihood). The quotations were genuine; the common-scope
interpretation was misleading. The browser's passing result verifies navigation,
citations, saving and exports, **not legal accuracy**. This semantic error remains
unresolved and requires claim-entailment review beyond quotation matching. The
newly saved browser-test finding is marked for review with this observation.

## Regression, browser and preservation checks

- `python -m pytest -q --tb=short`: **158 passed**.
- Compile checks passed; `python -m pip check` found no broken requirements.
- Real browser checks passed for all four desktop routes and four phone layouts,
  with exactly four navigation entries and no browser errors.
- A fresh browser-driven comparison opened original PDF citations from both
  documents, saved a finding, exported a comparison report, exported saved
  research and reopened a persisted report. All three PDF downloads succeeded.
- The pre-change SQLite backup was compared against the current database:
  all original 3 document rows, 332 chunks including vector bytes, 50 page rows,
  workspace memberships, 24 earlier runs, 5 saved findings, 7 evidence rows and
  2 report/brief rows remain identical. Document hashes and corpus revision are
  unchanged. Verification added new runs, one saved finding and report data;
  it did not delete or replace previous research.

Private artifacts are under `data/cross-document-validation/`: `baseline.json`,
`measured-retrieval.json`, `verified-live-results.json`,
`holdout-live-results.json`, `preservation.json`, and `browser/`.
Earlier prototype runs are retained there and are not the final results above.

## Reproduce on this existing library

```powershell
.\.venv\Scripts\python.exe -m pytest -q --tb=short
.\.venv\Scripts\python.exe -m scripts.evaluate_crossdoc --warmup --output data/cross-document-validation/repeated-retrieval.json
# Real external provider calls; adds research history, preserves document data:
.\.venv\Scripts\python.exe -m scripts.verify_crossdoc --live --output data/cross-document-validation/repeated-live.json
.\.venv\Scripts\python.exe -m scripts.verify_crossdoc --live --dataset evaluation/crossdoc_holdout_questions.json --output data/cross-document-validation/repeated-holdout.json
.\.venv\Scripts\python.exe -m scripts.check_four_page_app --compare --output data/cross-document-validation/repeated-browser
.\.venv\Scripts\python.exe -m scripts.audit_crossdoc_preservation
```

The last browser command needs the local server running. Gemini outputs are
stochastic; repeated runs can differ. These datasets reference this specific
private library; other libraries need their own source IDs and manual labels.
