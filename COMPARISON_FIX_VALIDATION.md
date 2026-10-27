> Historical record from before the three-section refactor. UI routes and commands here may refer to removed screens or scripts. See [README.md](README.md) and [REFACTOR_VALIDATION.md](REFACTOR_VALIDATION.md) for the current app.

# Scanned-document comparison repair

Verified with the existing uploaded Consumer Protection Act and scanned Consumer Protection (E-Commerce) Rules, real local retrieval, Gemini and Microsoft Edge. The four-page interface is unchanged.

## Actual causes

**Retrieval:** replaying the actual scope-comparison question retrieved Act passages on pages 20, 28, 32 and 39; the expanded attempt still omitted the scope/application provision on page 1. In this reproduced baseline, quotations passed the old validator (1/1 initially; 2/2 after expansion), but the comparison remained incomplete because relevant Act evidence was missing.

**Quotation copying:** an earlier saved failure recorded 5 attempted references and 4 valid references. Its rejected raw quotation was not retained, so the precise historical character difference cannot be reconstructed. Inspection of the actual scanned Rules and indexed text confirmed `alle-commerce` versus printed `all e-commerce`, stray OCR marks before the proviso, indentation and mixed dash/quote typography. Ordinary line breaks were already handled by whitespace collapsing; punctuation spacing and typography were not. Actual recognition errors cannot safely be treated as formatting.

The original Rules PDF page 2 (printed page 80) was rendered and visually inspected. Its eight pages have no native PDF text; the indexed and later page-level OCR both contain some recognition errors.

## Repair

- Scope comparisons search equivalent legal terms (scope, extent, applicability, application) and prioritize the leading provision's continuations within each selected PDF. Filters and evidence budgets remain enforced.
- Gemini comparisons select source-owned excerpt IDs. Code copies the corresponding contiguous original text from retrieved chunks and then runs the usual citation validator. Unknown IDs, incorrect ownership and unsupported citations fail closed. No quotation is reconstructed across chunks or pages.
- Conservative matching handles layout whitespace, typographic quotes, equivalent dash glyphs, ligatures and restricted alphabetic line-wrap hyphenation. Accepted references resolve to the exact original substring before display or saving.
- No edit-distance matching, spelling repair, O/0 substitution, changed numbers/negation or invented source text is allowed. Highlighting uses the same formatting matching on the selected original page; uncertain OCR alignment retains the existing honest fallback without an asserted highlight.

No UI feature, dependency or database migration was added.

## Actual verification

- Backend live comparison: **complete, 7/7 valid citations**, with evidence from both original PDFs.
- Separate browser live comparison: **complete, 7/7 valid citations**, again covering both documents. Every quote was checked as an exact stored-chunk substring with matching document ID and PDF page.
- Cited Act evidence: PDF page **1**. Cited Rules evidence: PDF page **2**.
- Both citation buttons opened the correct original pages. Pages were also reopened from saved research and visually inspected.
- Saving, comparison PDF export, saved-findings report creation and downloading the persisted report passed.
- Four desktop/phone pages passed; no JavaScript errors.
- Full regression: **132 passed**. Compilation passed. `pip check`: no broken requirements.

New tests cover harmless typography, original-substring resolution, altered words/numbers/negation/section references, wrong-source and cross-page quotes, unknown excerpt IDs, source ownership, Gemini selection schema, continuation retrieval, saving and page-local highlighting.

## Preservation and reproduction

A SQLite-consistent backup was taken first. Document, chunk/vector, membership and page-record rows remained identical. Every pre-existing finding, evidence record, brief and research run remained unchanged. Original PDF hashes still match their IDs. Browser verification added new research/findings/reports without changing older records.

Private artifacts: `data/comparison-fix-validation/` contains `before.sqlite3`, `baseline.json`, `verified.json`, `preservation.json`, and browser screenshots, downloaded reports and `final-comparison-result.json`.

```powershell
.\.venv\Scripts\python.exe -m scripts.verify_scanned_comparison --live --require-complete --output data/comparison-fix-validation/recheck.json
.\.venv\Scripts\python.exe -m scripts.check_four_page_app --compare --output data/comparison-fix-validation/browser-recheck
```

These commands send retrieved excerpts to Gemini. The first defaults to the two longest existing PDFs; `--documents ACT_ID RULES_ID` selects them explicitly. The browser check targets the running app on port 8080.

This verifies the uploaded versions and this actual comparison, not amendment currency or every possible OCR/legal interpretation. Genuine recognition errors remain visible in original quotations and are not guessed away to force validation.
