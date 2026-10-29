# Document intelligence for annual-report PDFs (devx AI Labs take-home A1)

Ingest a company PDF (prose, tables, charts, KPI cards, diagrams, a scanned page), ask questions from the command line,
get answers that cite their pages, and measure retrieval and answer quality separately. Built for a fictional customer,
Kirana Logistics Group's investor-relations team, but nothing in `src/` is specific to that document (a test enforces it).

## Run it in 5 commands

```bash
uv sync
cp .env.example .env.local        # then put your key in LLM_API_KEY (never commit this file)
uv run kirana ingest <report>.pdf
uv run kirana ask "What was net profit in 2024?"
uv run kirana eval                # writes eval/results/baseline.json and eval/RESULTS.md
```

Useful flags: `ask -k 5` (default 8), `ask --json`, `ask --doc <doc_id>`, `eval --only q03,q09`, `eval --tag mytag -k 3`.
Ingesting takes about 2 minutes the first time (8 vision calls, two at a time); later runs hit the on-disk cache in `.cache/`.

## Architecture

```
PDF --> ingest ---------------------------------------------> .cache/<doc_id>/
        per page:                                              pages.jsonl, chunks.jsonl, vision/*.png
        1. text blocks (PyMuPDF)          -> prose chunks
        2. tables (page.find_tables)      -> table chunks (continued tables merged across pages)
        3. images / scans                 -> vision model transcript -> figure / scan chunks

question --> BM25 top-k --> glm-5.3 (JSON, temperature 0) --> code verifies every citation --> CLI output
                              status: answered | refused | conflict
eval:  eval/questions.yaml --> retrieval metrics (no LLM) + answer metrics (must_contain + LLM judge)
                              + oracle pass (gold-page chunks fed directly) --> eval/RESULTS.md
```

### Ingestion method per content type

| Content | Method | Why |
|---|---|---|
| Prose | PyMuPDF text blocks in reading order; repeated header/footer lines removed | Exact and free; headers would pollute BM25 |
| Tables with a text layer | `find_tables()` -> markdown with caption; a table that continues on the next page with the same header is merged into one chunk | Keeps rows and columns aligned, numbers exact; a vision model would risk digit errors |
| Charts, KPI cards, diagrams, scans | Crop the image region at 200 DPI and transcribe with `glm-4.6v` (one generic prompt) | These facts are not in the text layer. One mechanism also covers the scanned page; no OCR engine is installed |

The vision trigger is generic: an embedded image covering at least 3% of the page, or any image on a page with under 150
text characters. Every chunk carries a context header (`[doc | page | type: caption]`) that is indexed with its text.
Details and the by-eye check of every transcript are in `docs/ingestion_notes.md`.

## Key decisions and trade-offs

- **Two models, because `glm-5.3` cannot see images.** The native endpoint rejects images and the Anthropic-compatible
  route accepts them but returns confident wrong numbers (96 for a chart whose value is 89.7). So `glm-5.3` does text
  (answering, judging) and `glm-4.6v` does vision. This is the single most important finding of the build.
- **BM25 first.** No embeddings endpoint is available (`embedding-3` rejected). BM25 is the honest baseline: no model
  download, millisecond index builds, easy to explain. Dense/hybrid is the first improvement, after the numbers are committed.
- **No vector database.** The report is 28 chunks; an in-memory index rebuilt per run is the right size.
- **Chunking:** page-aware, about 300 tokens, tables never split, one chunk per image. The report is short, so the
  natural unit is a page section; bigger chunks dilute BM25, smaller ones cut a fact from its subject.
- **Grounding is checked in code.** The model must quote verbatim; code checks the chunk was retrieved, the page belongs
  to it and the quote is a substring. Unverified citations are printed with a warning and counted in the eval.
- **Refusal by instruction, not by score threshold.** Eval shows retrieval scores of unanswerable questions overlap
  those of answerable ones, so a threshold would not help yet.
- **Retrieval and generation are measured separately**, including an oracle pass (gold-page chunks fed directly), so a
  failure can be assigned to ingestion, retrieval or generation.
- All LLM calls go through one client with retry and backoff, concurrency of 2, and a response cache keyed on the full request.

## Results: baseline (k=5) vs iteration 2 (k=8) (full tables in `eval/RESULTS.md`, `eval/RESULTS_HARD.md`, `eval/ITERATIONS.md`)

Two question sets, same questions in both columns. The 20-question **core** set is the brief's eval set. The 18-question
**hard** set (paraphrase, US/UK spelling, conceptual wording, near-duplicate rows, near-miss unanswerables) was written
before any improvement work so the "baseline, measure, fix, measure again" loop has something to move.
Iteration 2 made three small changes: (A) fixed the duplicate chunk from merged tables, (B) added spelling and stemming normalisation
to BM25, (C) raised the default k from 5 to 8. Predictions were committed before the run.

| metric | core baseline | core iteration 2 | hard baseline | hard iteration 2 |
|---|---|---|---|---|
| retrieval hit@1 / hit@5 (page-level) | 76% / 100% | 88% / 100% | 53% / 93% | 60% / 93% |
| chunk-level hit@1 / recall@5 | 71% / 96% | 82% / 94% | 33% / 83% | 47% / 73% |
| status correct | 95% | 95% | 94% | 94% |
| facts correct (must_contain) | 100% | 94% | 87% | 93% |
| LLM judge correct | 95% | 95% | 89% | 94% |
| judge correct with oracle (gold-page) context | 95% | 89% | 100% | 100% |
| citations verified by code | 100% | 100% | 100% | 100% |
| refusal recall / false-refusal rate | 100% / 6% | 100% / 6% | 100% / 7% | 100% / 7% |
| est. cost of the answer calls, whole set (z.ai list price) | $0.048 | $0.057 | $0.040 | $0.052 |

What moved: h04 is fixed and hard judge-correct rose by one question, almost entirely from the deeper context (k=8). With A+B at k=5 the
judge scores are 90% core and 83% hard, i.e. worse than baseline. What did not: h01 and q14 still fail (expected), and
stemming made the first-gold-chunk rank worse on average (chunk recall@5 on hard 83% to 73%), which k=8 hides. Predictions that were wrong:
cost rose 21-28%, not 40-60%; false refusals did not reach 0%; h05 did not improve. Single runs on 38 questions: directional, not proof.

The hard set is retrieval-limited, not generation-limited: with the gold pages handed to the generator it scores 100%,
with retrieved context 89% at baseline. The core set's one failure (q14) is an image-transcription error. See
`eval/failure_analysis.md` and `eval/failure_analysis_hard.md` for every failure, its stage and the evidence.
Both eval sets have been reviewed by the author. Cost uses z.ai pay-as-you-go list prices; the real account is a
flat subscription.

## Iteration 2: what improved, what did not, and the generality guard

The loop: baseline, measure, find the weakest part, fix, measure again (`eval/ITERATIONS.md` has predictions written
before the run and the verdict on each).

| change | effect |
|---|---|
| A. Merged-table duplicate fixed (ingestion) | corpus 28 to 27 chunks; the table no longer competes with a flattened copy of itself; h04 now answered correctly |
| B. UK/US spelling and stemming in BM25 | helps some questions (q07, q08, h10), hurts others (h04, h05, h12); net slightly negative on rank, flagged for decision |
| C. Default k 5 to 8 | the main driver: hard-set judge 83% to 94% (compared with A+B at k=5), at +21-28% cost |

Net: hard set judge-correct 89% to 94%, core unchanged at 95%, h01 and q14 still fail by design.

**Overfitting guard.** The pipeline must work on a second, unseen document without code changes, so each fix is a
generic mechanism (a merged table's blocks are consumed on every page it spans; a language-level tokenizer), never a
rule keyed to this report. `tests/test_generality.py` fails if document-specific literals enter `src/`, the eval
questions are frozen and were not edited to improve a score, and an unseen-document check is part of the next iteration.
The 38 questions all come from one report, so gains here are evidence for the mechanism, not proof of transfer.

## Known limitations

- Page-level gold labels overstate retrieval for tables (a prose chunk on the same page counts as a hit).
- **Vision output is non-deterministic and unverified.** The same image can be transcribed differently across runs at temperature 0 (seen on a diagram edge and a chart title). Facts that live only in images (9 of 20 core questions) inherit that risk, so the eval numbers describe one ingest run. The response cache makes reruns repeatable, not reliable.
- Stemming (iteration 2) lowered the rank of some table chunks; k=8 compensates. Whether to keep the Snowball pass is an open decision (`docs/decisions.md`).
- Reading order is top-to-bottom, left-to-right; multi-column layouts would interleave.
- BM25 has light stemming and UK/US spelling normalisation but no synonyms; conceptual questions with different wording will degrade (h01 still fails).
- Arithmetic is done by the model (one rounding slip observed).
- Only text-layer tables are parsed as tables; a table inside an image is a vision transcript.
- A small corpus: conclusions about k and ranking may not transfer to a 200-page report.

## What I would do with another week

Verify image transcripts with a second pass; add chunk-level gold labels and 30 harder questions (synonyms, near-duplicate
rows, conceptual wording); decide on the stemmer, then local dense embeddings with hybrid fusion; a calculator tool for arithmetic;
table-aware retrieval (whole table or none); per-row page tracking for merged tables; layout-aware reading order; a small review UI for flagged transcripts.

## How AI tools are used

Built with Claude Code (Claude Sonnet 5.5 writes the code from an author-verified plan).
Author brainstorms the detailed requirements and features and also reviews the code.
At runtime the system calls GLM-5.3 (answers, judging) and GLM-4.6V (image transcription) through the z.ai API.

## Layout

`src/kirana_rag/` (`ingest/`, `retrieve.py`, `answer.py`, `prompts.py`, `llm.py`, `cli.py`, `eval/`), `eval/` (questions, results,
analysis), `docs/` (ingestion notes, decisions), `scripts/make_subset_pdf.py` (builds a 4-page subset PDF: ingest it and ask
questions with no code changes), `tests/` (pytest, LLM mocked).
