# Third Iteration Plan: meaning-based retrieval, a stemmer decision, and a generality holdout

Why this exists: the brief says the pipeline "must work on a new PDF without code changes" and the demo round gives us a
second document from the same company. Iteration 2 gained its numbers mostly from a deeper `k`, and its tokenizer change
(B) helped some questions and hurt others. Every improvement so far was measured on one report, so the risk now is
**overfitting to that report**. This iteration therefore does two things at once: it fixes the largest remaining retrieval
weakness (no meaning-based matching: h01, h03, h12, h04/h05 ranks), and it adds a **holdout document** so we can see
whether a change transfers.

Read `eval/ITERATIONS.md`, `eval/failure_analysis*.md` and `docs/decisions.md` first. Same style as the second plan.

## 1. Baseline this iteration must beat (iteration 2, k=8, unchanged questions)

| metric | core (20) | hard (18) |
|---|---|---|
| hit@1 / hit@5 (page) | 88% / 100% | 60% / 93% |
| chunk-level hit@1 / recall@5 | 82% / 94% | 47% / 73% |
| status / facts / judge correct | 95% / 94% / 95% | 94% / 93% / 94% |
| false-refusal rate | 6% | 7% |
| mean first-gold-chunk rank (retrieval only, 32 questions) | 1.91 (A+B), 1.72 (A only) | |
| corpus | 27 chunks | 27 chunks |

Reference runs on disk: `baseline*`, `hard_baseline`, `iter2*`, `hard_iter2*`. Never overwrite or delete them. Both eval
question files are REVIEWED: **do not edit any question, `must_contain` or `gold_*` label**.

## 2. Generality rules (these override convenience)

The recruiter's demo is a second document from the same company, unseen. So:

1. **Nothing document-specific in `src/`.** `tests/test_generality.py` must stay green; extend its forbidden list with
   words from the new holdout document too.
2. **Fix hyperparameters before looking at results.** Embedding model, fusion constant (RRF `k=60`, the standard value),
   equal fusion weights: choose them in section 3, commit, then run. Do not sweep them on the 38 questions.
3. **A holdout document the code is never tuned on.** Written in Step A, before any retrieval change. It is
   reported, not used to pick settings. If a change helps Kirana and hurts the holdout, that is overfitting: say so and do not keep it.
4. **Prefer mechanisms over rules.** No synonym lists, no per-question handling, no thresholds fitted to these scores.
5. **Always compare against both:** the Kirana sets and the holdout, in one table.

## 3. Pre-registered decisions and predictions (commit to `eval/ITERATIONS.md` BEFORE running any eval)

Fixed in advance:
- Dense model: `BAAI/bge-small-en-v1.5` via `fastembed` (small, local, no API). Chunks are embedded as `header + text`; the query is embedded with the model's query prefix.
- Fusion: reciprocal rank fusion of BM25 and dense rankings, constant 60, equal weight, over the full ranking.
- Default `k` stays 8.
- Stemmer: decided by the ablation in Step B, with the rule stated here: keep Snowball only if it does not lower the mean first-gold-chunk rank on **both** Kirana and holdout retrieval-only metrics; otherwise keep only the UK/US spelling pass.

Predictions (to be marked right or wrong afterwards):
- Hybrid raises chunk recall@5 on hard from 73% toward 85% or more, and moves h04, h05, h12 up. h01 may be fixed (zero word overlap); if it is not, say so.
- Hit@8 stays 100%. Core stays at 95% or above.
- Cost per question is unchanged or slightly lower (a better top-8 does not need more context); index build adds a one-time model download and a few seconds of embedding.
- Holdout: hybrid is not worse than BM25-only on holdout retrieval-only metrics. If it is, the iteration is reported as overfit.
- Risk: dense retrieval may promote vaguely related chunks over exact-number matches (e.g. "1.71x" queries). Watch number-heavy questions.

## 4. Implementation steps (commit locally after each; conventional commits; attribution line from the system reminder; do not push unless the author says so)

**Step 0: protect the baseline.** `git status` clean, `uv run pytest -q` passes. Keep `.cache/llm` (cached vision transcripts and answers stay; the delta isolates retrieval). Add an "Iteration 3" section to `eval/ITERATIONS.md` with the baseline table and the section-3 decisions and predictions. Commit: `docs(eval): iteration 3 predictions`.

**Step A: holdout document and questions** (before touching retrieval).
- Build `scripts/make_holdout_pdf.py` that generates a synthetic annual report for a **different fictional company** (different industry words, UK spelling, one table spanning two pages, a text-layer table with synonyms of the Kirana ones, one chart image rendered with matplotlib or PyMuPDF drawing, 6 to 8 pages). Reuse `tests/pdfmaker.py` helpers where sensible. The PDF is generated, not committed (same rule as other PDFs); the script is committed.
- Write `eval/questions_holdout.yaml` (about 12 questions: lookup, table, synonym/paraphrase, a conceptual one, a cross-reference, 2 unanswerable, with gold pages and gold chunks). Mark it `status: HOLDOUT, written before iteration 3 changes`. **After this commit its questions are frozen.**
- Make `kirana eval --suite holdout` work (small change to the suite selection in `cli.py`; results to `RESULTS_HOLDOUT.md` and `failure_analysis_holdout.md`). Ingest the holdout and run the **current code** (`--tag holdout_iter2`). This is the holdout baseline.
- Commit: `feat(eval): holdout document, questions and suite`.

**Step B: stemmer ablation (retrieval only, no LLM).**
- Add an env/config switch (`KIRANA_NORMALISE=none|spelling|full`, default `full` for now) in `retrieve.py`. Compute chunk-level first-gold rank, hit@1, recall@5 for the three modes on Kirana core + hard and on the holdout. Put the table in `eval/ITERATIONS.md`.
- Apply the rule from section 3 to pick the default; one line in `docs/decisions.md`. Keep the switch only if it stays simple; otherwise remove it after deciding.
- Tests for whichever mode wins. Commit: `feat(retrieve): decide normalisation by ablation`.

**Step C: hybrid retrieval** (`src/kirana_rag/retrieve.py`, new `src/kirana_rag/embed.py`; add dependency `fastembed`).
- Embed all chunks once per ingest and store `embeddings.npy` next to `chunks.jsonl` in `.cache/<doc_id>/` (an index step, not per query). Missing file: embed on first load and save.
- `Index.search` ranks with BM25 and with cosine similarity, fuses with RRF (section 3 constants), returns `Hit` with the fused score and keeps the BM25 and dense ranks on the hit for debugging (`python -m kirana_rag.retrieve` prints both).
- Keep a `--retriever bm25|hybrid` option in `ask` and `eval` so the delta is reproducible; default `hybrid`.
- If the model download fails offline, fall back to BM25 with a clear one-line warning (never crash).
- Tests: toy corpus where a paraphrase with no shared words finds the right chunk under hybrid but not BM25 (use a mocked embedder that is deterministic; do not download in tests); RRF math on a known pair of rankings; fallback path.
- Commit: `feat(retrieve): hybrid BM25 plus dense retrieval`.

**Step D: measure.** In this order, each with `--doc <doc_id>`:
1. `uv run kirana eval --tag iter3 --doc <kirana_id>` and `--suite hard --tag hard_iter3`.
2. `--suite holdout --tag holdout_iter3 --doc <holdout_id>`.
3. Separation runs: `--retriever bm25` on all three suites (`iter3_bm25`, ...) so the effect of the retriever is separated from the stemmer decision.
Use the response cache; debug with `--only`.

**Step E: report.**
- Fill the Iteration 3 section of `eval/ITERATIONS.md`: baseline vs iter3 vs holdout, predicted vs actual, every question whose outcome changed, which step caused what.
- Failure-analysis "after iteration 3" sections; README results table gets an "iteration 3" column plus a holdout column; update "what I would do with another week" and the generality section.
- `uv run ruff check`, `uv run ruff format`, `uv run pytest` clean.

## 5. Rules for the implementing session

- Honest numbers; never print, log or commit the API key; no `.env*` or PDFs in git; simple readable code that reads like the surrounding code.
- Pre-register before running. Do not edit eval questions, `must_contain` or `gold_*` labels to improve a score, and do not tune any setting on the holdout.
- Do not implement section 6 items. If something regresses, keep the evidence and decide keep/revert in `docs/decisions.md`.
- Commit locally after each step. Do not push; the author does that.
- Finish with a summary: predicted vs actual table (Kirana core, hard, holdout), questions that changed, anything worse, open questions for the author.

## 6. Left for a later iteration (do NOT do now)

1. Verify image transcripts (two-run agreement or a check pass); targets q14 and vision non-determinism.
2. Calculator tool for arithmetic (the 1.71 vs 1.72 wording slip in q03).
3. Table-aware retrieval (whole table or none) and short natural-language descriptions per table chunk.
4. Refusal threshold or "partial evidence" rule, only if retrieval scores separate answerable from unanswerable.
5. A larger eval set across several documents, so deltas are not limited by a 38-question, single-report sample.
6. Cross-encoder reranking.
