> Historical record from before the three-section refactor. UI routes and commands here may refer to removed screens or scripts. See [README.md](README.md) and [REFACTOR_VALIDATION.md](REFACTOR_VALIDATION.md) for the current app.

# E-Commerce Rules deadline retrieval repair

## Actual source investigation

The uploaded `Consumer Protection (E-Commerce) Rules, 2020.pdf` has SHA-256 `54fed9f2b119f487c66af671f338e7962f9cf22b55e1e8ba3456219e3394872a`. Rule 4(5) is clearly visible on **original PDF page 4**, printed page 82. It was visually checked against the rendered scan.

The relevant provision was already complete in both the original indexed OCR and the later page-level OCR. SQLite chunk `7b4ff64dae9267eaf68822751cf7759eb79800d7e1f906f8ab54c3f09dd1ad91` contains the full paragraph, including the forty-/eight line wrap and the one-month period from receipt. This chunk was present in the searchable FAISS index. The document belonged to the affected workspace.

The saved failed runs contained **zero attempted citations**. Their expanded evidence began with numerous Consumer Protection Act definitions and omitted the Rule 4(5) chunk. Consequently, Gemini's refusal was appropriate for the evidence it had received; this failure was not caused by missing OCR or quotation validation.

## Root cause and repair

“What is the time limit … consumer complaints” incorrectly satisfied a broad single-word definition trigger for “consumer.” Those definition chunks and their continuations occupied the retrieval budget. Full-question ranking also included the long instrument title and answer-format instructions, and recovery unconditionally appended a definition query.

The repair is general:

- Definition intent now requires the requested defined term itself, distinguishing “What is a consumer?” from “What is the time limit … consumer complaints?”
- Focused queries remove Act/Rules titles and answer-format boilerplate. Hybrid ranking combines original and focused semantic/BM25 results. A definition expansion is used only when actually requested.
- An explicitly named document receives priority **within the existing allowed scope**. Document, workspace and metadata filters are retained; an excluded PDF is never silently searched.
- Numbered-heading parsing tolerates OCR spacing such as `4.Duties`, `4 . Duties` and `(5)Every`, without guessing different digits or treating decimal numbers as headings.
- Answer guidance asks Gemini to name the supported legal provision explicitly when requested.

After repair, the complete Rule 4(5) chunk ranks **first** for the exact natural-language question. No legal answer, deadline or document-specific rule number was hardcoded into production retrieval or prompts.

**No OCR repair or reindex was necessary:** the target extraction and vectors were already intact. Replacing them would not address this failure and would risk saved references.

## Actual verification

- Fresh Gemini calls answered the exact question with **48 hours for acknowledgement** and **one month from receipt for redressal**, citing Rule 4(5) on PDF page 4.
- Gemini also supplied separately supported marketplace-seller context under Rule 6(4)(b), correctly citing PDF page 6. Verification permits that additional evidence while requiring the primary Rule 4(5) evidence on page 4.
- Independent control question: automatic consent/pre-ticked checkboxes. The answer correctly described the prohibition and affirmative-action requirement, supported by Rule 4(9) on page 4.
- The persisted live answers each had **2/2 validated references**. Every quote was checked against its actual stored chunk and page. These are real provider outputs, not test doubles.
- The final fresh browser call again answered the exact question, explicitly named Rule 4(5), opened original PDF page 4, and downloaded a readable cited PDF report. Four desktop/phone pages passed without JavaScript errors.
- Full regression: **142 passed**. Compilation passed; `pip check` reported no broken requirements.

The new regression fixtures use verified excerpts from the actual scan. Tests cover the exact question, another Rules provision, definition-intent discrimination, named-document ranking, OCR heading spacing, stale retry pools and document/metadata filter isolation.

## Preservation and artifacts

The pre-repair SQLite backup and preservation audit are in `data/rule45-validation/`. Original document rows, all chunk/vector rows, page records, memberships and pre-existing saved research remained unchanged. Original PDF hashes remain valid. Tests added new research runs and a downloaded report, without deleting or rewriting older records. No UI files or dependencies were changed.

Actual outputs include `live-results.json` (verified persisted real Gemini answers), `preservation.json`, original page images, and `browser/results.json`, the answer/source screenshot and exported report.

```powershell
# Fresh real-provider checks using the configured .env:
.\.venv\Scripts\python.exe -m scripts.verify_rules_research --live
# Or audit the latest persisted live answers without another provider request:
.\.venv\Scripts\python.exe -m scripts.verify_rules_research --from-saved
# Existing app must be running at port 8080:
.\.venv\Scripts\python.exe -m scripts.check_rules_question
```

This verifies the uploaded text and these actual questions; it does not claim universal legal accuracy, flawless OCR or current amendment status. Strict evidence validation remains enabled.
