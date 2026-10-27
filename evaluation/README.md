# LexiRAG evaluation protocol

No benchmark scores ship with the project. The CLI saves measured experimental runs in the configured `data/evaluation/` directory. Test-suite outcomes and synthetic-fixture scores are not evidence of performance on real Indian legal materials.

## Prepare human relevance labels

1. Index your chosen corpus and freeze the documents, embedding model and chunk settings.
2. Export exact chunk IDs and text: `python -m evaluation.export_chunks --output data/annotation_chunks.jsonl`. This contains private excerpts; do not commit or share it unnecessarily.
3. Write research questions and manually inspect the original PDFs. Label **all** chunks relevant to each supported question. Annotate unsupported questions separately. Account for overlapping chunks when labeling. A second annotator and an adjudication log improve academic rigor.
4. Save UTF-8 JSONL, one object per line:

```json
{"id":"privacy-01","question":"Which provisions govern withdrawal of consent?","relevant_chunk_ids":["actual-sha256-chunk-id-1","actual-sha256-chunk-id-2"],"unsupported":false,"document_ids":[]}
{"id":"unanswerable-01","question":"What does a judgment not in this corpus hold?","relevant_chunk_ids":[],"unsupported":true,"document_ids":[]}
```

Replace example IDs with current IDs from the export. `document_ids` is optional: an empty list searches the whole library. Unknown IDs, duplicate case IDs, supported questions without labels, and labels outside a document filter are rejected. Re-label after changing chunk settings or re-ingesting documents. Avoid using a supported question's answer as the query.

## Run experiments

```powershell
# Semantic versus hybrid versus hybrid with a real cross-encoder
python -m evaluation.runner data/questions.jsonl --k 6

# Local retrieval only, without downloading the reranker
python -m evaluation.runner data/questions.jsonl --k 6 --modes semantic hybrid

# Also call Gemini to measure response latency, refusal and citation provenance
python -m evaluation.runner data/questions.jsonl --k 6 --answers

# Add the Ragas collections API and Gemini judge
python -m pip install -r requirements-eval.txt
python -m evaluation.runner data/questions.jsonl --k 6 --answers --ragas
```

The three-section application exposes evaluation through these CLI tools.
Ragas is optional
to avoid adding its sizeable evaluation stack to normal application use. Faithfulness
uses `ragas.metrics.collections.Faithfulness`; the judge calls **Gemini**, through
Google's OpenAI-compatible endpoint and the maintained Instructor adapter. No OpenAI
key or OpenAI-hosted model is used.

For per-document comparison experiments on the existing library, run
`python -m scripts.evaluate_crossdoc --warmup`. This compares shared hybrid,
planned hybrid, controlled reranking without recovery, and automatic comparison
with recovery at the same anchor budget. `crossdoc_questions.json` contains the
four manually labelled validation cases; `crossdoc_holdout_questions.json` contains
generation-only held-out questions and must not be scored as labelled retrieval.
Real provider checks use `python -m scripts.verify_crossdoc --live`. See
[the measured comparison report](../CROSSDOC_VALIDATION.md) for limits and results.

The evaluation requirements pin `langchain-community==0.4.1`: Ragas 0.4 imports compatibility symbols removed in Community 0.4.2. Application generation and retrieval use the maintained LangChain Core / Google GenAI APIs directly. The collections metrics require an asynchronous judge client; LexiRAG manages that client per question so repeated evaluations work in the same process.

## Metric definitions

| Metric | Definition and denominator |
| --- | --- |
| Precision@K | Unique relevant retrieved chunk IDs in the first K / K. Missing results count as misses. Supported questions only. |
| Recall@K | Unique relevant retrieved IDs in first K / total gold relevant IDs. Supported questions only. |
| MRR | Mean inverse rank of the first gold relevant chunk among retrieved top-K results, or zero if none. Supported questions only. |
| Citation provenance | Valid source IDs and verbatim quote matches / all attempted evidence references in raw model output, before invalid findings are withheld. Structural validation, **not entailment**. |
| Citation correctness | Ragas faithfulness applied to each displayed claim against each of its individually cited passages; averaged across citation pairs. An LLM-judged claim-support estimate. |
| Answer faithfulness | Ragas faithfulness of displayed answer statements against all evidence actually supplied to generation. No score for a refusal without claims. |
| Retrieval latency | Wall time for embedding, FAISS/BM25/RRF and optional reranking. Includes first-use model loading. |
| Response latency | Retrieval plus answer generation and citation validation, excluding evaluation judge calls. |
| Unsupported rejection rate | Unsupported questions answered with `insufficient_evidence=true` **and no findings** / unsupported questions, with answer generation enabled. Partial unsupported findings do not count as safe refusals. |
| Supported answer rate | Supported questions with at least one accepted finding and no complete refusal / supported questions. Helps expose systems that always refuse. |

Undefined or unmeasured values are `null`, not zero. Aggregate metrics are macro-averages over measured questions/pairs. Experiments save corpus revision, model IDs, dataset checksum, K and per-question IDs/measurements. They omit question, answer and excerpt text. Saved experiments include their corpus revision for identifying stale results. Source hash labels can still reveal document identity; keep experiment files private where required.

For reproducible research, archive the private corpus, annotation protocol, environment lock, model revisions/downloads and seed dataset together. Run warm-up queries before a second latency experiment and report whether cold-start cost is included. Use held-out questions to tune K, RRF/candidate settings and reranking; do not tune on your test set. Small datasets, overlapping passages and model-judged metrics can bias results. Inspect citations and refusal examples manually; these scores do not establish legal accuracy.

## Optional synthetic smoke experiment

```powershell
python -m scripts.create_demo --index
python -m evaluation.runner data/demo/fixture-questions.jsonl --k 3 --modes semantic hybrid
```

This creates clearly labeled fictional teaching agreements and predefined relevance labels for their termination clauses. It runs the **real** embedding and retrieval pipeline. It is a workflow check, not a legal-research benchmark. The ordinary unit tests use deterministic embedding and generation doubles to test invariants without network/API charges.

