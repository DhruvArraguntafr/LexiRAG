> Historical record from before the three-section refactor. UI routes and commands here may refer to removed screens or scripts. See [README.md](README.md) and [REFACTOR_VALIDATION.md](REFACTOR_VALIDATION.md) for the current app.

# Retrieval refusal investigation and four-page validation

The comparison limitation recorded below has since been repaired and verified on the actual uploaded PDFs. See [COMPARISON_FIX_VALIDATION.md](COMPARISON_FIX_VALIDATION.md) for the current 132-test and live comparison results. This report preserves the earlier investigation.

## Actual root cause

The uploaded Act was available: `CP Act 2019_1732700731.pdf`, SHA-256 `0ae7f82ab5b77d50087cd4cd2dd2dbc12755c0bdb31371fdefd042b020d50756`, 40 PDF pages. The original failed question and refusal were present in saved research.

The relevant text was **already extracted and indexed**. The consumer-rights definition begins on PDF page 3 and continues on page 4. The parent Section 2 Definitions heading is on PDF page 2. Relevant original chunk IDs include:

- `e2bb0fbcd7443d30c3d93dd4fbdfff6c4ed907dd09f43bd3a31fee332fe1b1a5`: definition and items (i)–(ii), page 3.
- `eb0f294a4a85c23e40373e757525b5fddccb33532aa3d158793aaf57be053ae4`: items (iii)–(vi), page 4.

These IDs existed in both SQLite and the real FAISS index. The saved initial search returned six other passages: general Act/rules references, Council objects and Authority functions. It returned neither of these two list passages. Generic full-question retrieval favored repeated statute/title words; the page-based chunks had no Section 2(9) locator and did not connect the continuation to the definition. There was no exact statutory lookup and no recovery pass after Gemini reported insufficient evidence. The refusal was appropriate for the incomplete evidence sent to the model.

The affected workspace contained all three uploaded PDFs. The saved sources included the Act; no document-type, jurisdiction or legal-date filter explained the omission. This was a retrieval/structure failure, not a missing Act or an API-key failure.

An additional legacy-data gap was confirmed: only the two-page advisory had stored page records. The Act and scanned rules had vectors/chunks but no `document_pages` records.

## Implemented repair

- Recognize normalized Section, Rule and Article references, including spaces inside numbered parentheses.
- Track statutory parents and numbered clauses across pages; distinguish judgment paragraphs and amendment footnotes from statute headings.
- Prioritize exact provisions and matched defined terms alongside semantic/BM25 fusion, and retrieve their continuation chunks plus parent-heading evidence. Prefer the longer requested defined term over an embedded shorter term.
- Restore missing legacy page records from the original PDFs, with automatic local OCR for scanned pages. Keep original chunk IDs, text and vectors intact. Long exact page anchors accommodate legacy OCR punctuation differences without replacing citation text.
- For new uploads, split along legal structure, keep short numbered lists together, retain page boundaries and carry provision labels onto continuation chunks.
- Before accepting insufficient evidence, perform bounded keyword reformulations and evidence expansion, including relevant neighboring chunks. Retry generation when the expanded context contains new evidence. All attempts retain the same document/workspace/metadata restrictions and exact quote validation.
- Comparisons receive the same bounded recovery independently for each selected document, with fair evidence allocation and source-coverage checks before another model call.
- Write private rotating diagnostics to `data/logs/retrieval.jsonl`: question, filters, retrieved IDs/pages, normalized section references and recovery outcome. Source passages and API credentials are never added to those diagnostic records.

No consumer-rights answer or Act-specific branch was added to production retrieval/generation code. The exact question and expected statutory phrases appear only in regression fixtures and verification scripts.

## Real document and Gemini verification

`scripts/verify_consumer_retrieval.py --workspace 3298207e1ad44556a60b8b3de503d4d3 --document 0ae7f82ab5b77d50087cd4cd2dd2dbc12755c0bdb31371fdefd042b020d50756 --live` passed against the actual library, real local embedding weights and configured Gemini provider.

- Initial automatic retrieval included every one of the six rights and parent-heading evidence from pages 2–4.
- Gemini returned a supported answer, with six separate rights and **6/6 verified citations**.
- The answer identified safety, information, choice, being heard, redressal and consumer awareness, citing Section 2(9) and its clauses.
- Each supporting quotation matched both its retrieved chunk and the text extracted directly from the original cited PDF page.
- Negative control: excluding the Act while retaining the other uploaded documents produced an insufficient-evidence response. Every initial/recovery source remained inside the allowed scope.
- Exact `Rule 4(5)` lookup also found its actual uploaded rules passage on PDF page 4. Article 21 and numeric-prefix distinctions are covered by independent fixtures.

Private actual outputs: `data/retrieval-fix-validation/real-act-results.json`, `before-retrieval.json`, `preservation-checks.json`, and browser screenshots/reports. `before.sqlite3` is a SQLite-consistent pre-repair backup.

## Preservation

Compared with that backup, all **3 document rows**, **332 complete chunk/vector rows**, and workspace memberships were identical. Every pre-existing finding, evidence record, brief and research run remained unchanged. Page records increased from 2 to 50. Live checks added new research runs and explicitly saved a finding; no original research or document was deleted or reindexed.

## Checks

- Full regression: **110 passed** (`python -m pytest -q --tb=short`).
- Compilation of the application, backend, UI, scripts and tests: passed.
- Dependency consistency: `python -m pip check` reported no broken requirements.
- Real browser checks exercise the actual failed question, clickable original-page evidence, saving a finding and downloading its PDF report.
- Comparison and saved-report download controls worked with actual saved findings. A stricter follow-up audit found that Gemini's Rules quotation had failed validation, leaving support from only one PDF. The comparator now retries when citation coverage is incomplete and **marks the result incomplete** if verified citations still fail to cover both documents. New tests cover both recovery and persistent one-sided evidence.
- The final live comparison of the Act and scanned Rules remained partial after strict quote validation. The app correctly withheld a complete-comparison claim; this was not counted as a successful complete legal comparison. Earlier browser-download checks alone were insufficient to establish two-document citation coverage.
- All four pages passed desktop and 390-pixel phone checks; removed tool routes returned to Home, with no browser JavaScript errors. The actual consumer-rights question also passed through the final browser build with six findings and six verified citations.
- The four registered pages are Home, AI Research, Compare Documents and My Research. The Advanced entry and specialist routes are removed; old tool URLs return to Home. Backend/CLI modules and their regression tests remain.

The real long rules filename exposed a phone-width dropdown overflow, which was corrected and checked with the actual document names.

## Limits

This verifies this actual Act, the selected additional legal-reference cases and existing regression coverage. It is not a general legal-accuracy benchmark. OCR, unusual statutory layouts, complicated nested numbering and semantic interpretation still require source review. Some live comparisons remain partial when Gemini fails exact quotation checks, even after retrieval recovery; validation is not relaxed to force an answer. Exact quotation checks establish provenance, not universal legal entailment or current amendment/judicial-treatment status. Online official PDF fetches timed out, so the uploaded original was the verification authority for this run.
