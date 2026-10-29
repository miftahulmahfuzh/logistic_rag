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

Useful flags: `ask -k 8`, `ask --json`, `ask --doc <doc_id>`, `eval --only q03,q09`, `eval --tag mytag -k 3`.
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

## Baseline results (k=5; full tables in `eval/RESULTS.md` and `eval/RESULTS_HARD.md`)

Two question sets, same code, same ingest. The 20-question **core** set is the brief's eval set. The 18-question
**hard** set (paraphrase, US/UK spelling, conceptual wording, near-duplicate rows, near-miss unanswerables) was written
before any improvement work so the "baseline, measure, fix, measure again" loop has something to move.

| metric | core (20) | hard (18) |
|---|---|---|
| retrieval hit@1 / hit@5 (page-level) | 76% / 100% | 53% / 93% |
| chunk-level hit@1 / recall@5 | 71% / 96% | 33% / 83% |
| status correct | 95% | 94% |
| facts correct (must_contain) | 100% | 87% |
| LLM judge correct | 95% | 89% |
| judge correct with oracle (gold-page) context | 95% | 100% |
| citations verified by code | 100% | 100% |
| refusal recall / false-refusal rate | 100% / 6% | 100% / 7% |
| est. cost of the answer calls, whole set (z.ai list price) | $0.040 | $0.048 |

The hard set is retrieval-limited, not generation-limited: with the gold pages handed to the generator it scores 100%,
with retrieved context 89%. The core set's one failure (q14) is an image-transcription error. See
`eval/failure_analysis.md` and `eval/failure_analysis_hard.md` for every failure, its stage and the evidence.
Both eval sets have been reviewed by the author. Cost uses z.ai pay-as-you-go list prices; the real account is a
flat subscription.

## Known limitations

- Page-level gold labels overstate retrieval for tables (a prose chunk on the same page counts as a hit).
- **Vision output is non-deterministic and unverified.** The same image can be transcribed differently across runs at temperature 0 (seen on a diagram edge and a chart title). Facts that live only in images (9 of 20 core questions) inherit that risk, so the eval numbers describe one ingest run. The response cache makes reruns repeatable, not reliable.
- Known ingestion defect, left in the baseline on purpose: the continuation page of a merged table also emits a flattened prose chunk (`eval/failure_analysis_hard.md`).
- Reading order is top-to-bottom, left-to-right; multi-column layouts would interleave.
- BM25 has no stemming or synonyms; conceptual questions with different wording will degrade.
- Arithmetic is done by the model (one rounding slip observed).
- Only text-layer tables are parsed as tables; a table inside an image is a vision transcript.
- A small corpus: conclusions about k and ranking may not transfer to a 200-page report.

## What I would do with another week

Verify image transcripts with a second pass; add chunk-level gold labels and 30 harder questions (synonyms, near-duplicate
rows, conceptual wording); stemming then local dense embeddings with hybrid fusion; a calculator tool for arithmetic;
per-row page tracking for merged tables; layout-aware reading order; a small review UI for flagged transcripts.

## AI tools

Built with Claude Code (Claude Sonnet 5.5 wrote most of the code from a written plan). The author reviews the code and can explain it.
At runtime the system calls GLM-5.3 (answers, judging) and GLM-4.6V (image transcription) through the z.ai API.

## Layout

`src/kirana_rag/` (`ingest/`, `retrieve.py`, `answer.py`, `prompts.py`, `llm.py`, `cli.py`, `eval/`), `eval/` (questions, results,
analysis), `docs/` (ingestion notes, decisions), `scripts/make_subset_pdf.py` (builds a 4-page subset PDF: ingest it and ask
questions with no code changes), `tests/` (pytest, LLM mocked).
