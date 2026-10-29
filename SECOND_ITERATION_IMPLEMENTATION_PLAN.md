# Second Iteration Plan: small, measured fixes to the baseline

Why this exists: the brief says "start with a baseline that works end to end, measure it, then improve the weakest
part. Show us that loop." The baseline is committed and measured (`eval/results/baseline*.json`, `eval/RESULTS*.md`,
`eval/failure_analysis*.md`). This iteration makes **three small, evidence-backed changes**, re-measures on the same two
question sets, and reports the delta honestly, including what did not improve and what got worse.

It is deliberately modest. Dense/hybrid retrieval, vision verification, a calculator tool and a refusal threshold are
left for `THIRD_ITERATION_IMPLEMENTATION_PLAN.md` (written after this iteration's numbers are in, see section 6).

## 1. Baseline numbers this iteration must beat (k=5, unchanged questions)

| metric | core (20) | hard (18) |
|---|---|---|
| retrieval hit@1 / hit@5 (page) | 76% / 100% | 53% / 93% |
| chunk-level recall@5 | 96% | 83% |
| status / facts / judge correct | 95% / 100% / 95% | 94% / 87% / 89% |
| false-refusal rate | 6% | 7% |
| oracle judge correct | 95% | 100% |
| corpus | 28 chunks | 28 chunks |

Reference runs on disk: `baseline`, `baseline_k3`, `baseline_k8` (core) and `hard_baseline` (hard). Do not overwrite or
delete them. Both eval question files are marked REVIEWED: **do not edit any question**. If a question turns out to be
wrong, write it in `docs/decisions.md` and tell the author instead of silently changing it.

## 2. Evidence driving each change (from the baseline failure analysis)

| # | Change | Evidence | Stage |
|---|---|---|---|
| A | Fix the merged-table duplicate chunk | `p8-x1` is a flattened second copy of Table 2's rows, because `pipeline.py` only marks table blocks consumed on the page where the table starts. Seen via h04: the model answered from the partial copy, confidently wrong. | ingestion bug |
| B | Light normalisation in the BM25 tokenizer: stemming plus UK/US spelling | Appendix B hypothesis "no stemming" never demonstrated on the core set; h05 ("utilization") only passed because a second keyword matched. | retrieval |
| C | Default `k` from 5 to 8 | k sweep on the core set: false refusals 12% / 6% / 0% at k = 3 / 5 / 8, status 85% / 95% / 95%. h04's table is at rank 6. hit@8 is 100% on both sets. | retrieval depth |

Not in scope (stays a documented failure): h01 ("underused warehouses", the table has zero word overlap with the
question) needs meaning-based retrieval, so it is **expected to still fail** after this iteration.

## 3. Pre-registered predictions (write these into `eval/ITERATIONS.md` BEFORE running the eval)

Commit the predictions first, then run, so the delta cannot be rationalised afterwards.

- A: corpus drops from 28 to 27 chunks; `p8-x1` no longer exists; Table 2 stays one chunk with 23 rows on pages [7, 8].
  Retrieval for q04, q05, q06, h06, h15 changes slightly (the duplicate no longer competes). Expect h04 to improve.
- B: h05 table rank improves or stays; no regression on number-heavy questions (stemming must not touch tokens with digits).
- C: false-refusal rate falls toward 0% on core; retrieval hit@8 unchanged (already 100%); **cost rises about 40-60%** because more
  context is sent; **risk**: more context may make the generator stretch on unanswerable questions (watch refusal recall)
  and may add unverified citations.
- Overall: hard set judge-correct goes up by about 1 question (h04); h01 still fails; core stays at or near 95-100%.

If a prediction is wrong, say so in the results. A change that does not help is reported, and kept or reverted with a
one-line reason in `docs/decisions.md`.

## 4. Implementation steps (commit locally after each; conventional commits; end with the attribution line from the system reminder)

**Step 0: protect the baseline.** Confirm `git status` is clean and `uv run pytest -q` passes. Do not clear `.cache/llm`:
the vision responses must stay cached so the committed image transcripts are reused and the delta isolates the code
changes. Add `eval/ITERATIONS.md` with the baseline row and the section-3 predictions. Commit: `docs(eval): iteration 2 predictions`.

**Step A: table continuation fix** (`src/kirana_rag/ingest/pipeline.py`).
- Before the per-page loop, build `table_regions: dict[int, list[bbox]]` from every merged table's `parts` (page, bbox).
- In the page loop, mark blocks inside `table_regions[rec.number]` as consumed, instead of doing it only for tables found
  on that page. Report-agnostic (no page or table names).
- Tests: a synthetic two-page PDF (reuse `tests/pdfmaker.py`) where a table continues on page 2: assert the merged table
  chunk exists, and **no prose chunk on page 2 contains any of the continuation table's cell text**.
- Re-ingest with `uv run kirana ingest <pdf> --force` (vision stays cached). Check: 27 chunks, `p8-x1` gone, `p7-t1` has 23 data rows.
- Run `uv run python -m kirana_rag.retrieve "<q>"` for h04's question and note where `p7-t1` ranks.
- Update `docs/ingestion_notes.md` (one line: duplicate chunk removed, date).

**Step B: tokenizer normalisation** (`src/kirana_rag/retrieve.py`; add dependency `snowballstemmer`, pure Python).
- After the existing tokenisation: tokens containing a digit are left untouched; other tokens go through (1) a small UK→US
  spelling pass: the regex `isation(s)?` → `ization\1`, plus a short explicit dict (`labour`, `colour`, `centre`, `programme`,
  ...), then (2) the English Snowball stemmer. Apply to both index and query (same function).
- Keep it a few lines and explainable. No synonym lists (that is iteration 3's problem).
- Tests (extend `tests/test_retrieve.py`): `utilisation`/`utilization`/`utilisations` collapse to one token; `trucks`/`truck`;
  `8,420` and `1.71` unchanged; a toy-corpus ranking where the US-spelled query now finds the UK-spelled chunk.
- Update the `tokenize` docstring (it currently says "No stemming on purpose") and `docs/decisions.md`.

**Step C: default k = 8** (`src/kirana_rag/config.py` `DEFAULT_TOP_K`, and the `-k` defaults in `cli.py`; README flags).
- One-line change plus text updates. Nothing else uses 5 as a magic number: grep `5` in `cli.py` and `eval/runner.py`
  (`report.py` reads hit@5 as a metric name, which stays).

**Step D: measure.** In this order, each with `--doc <doc_id>` (required when several docs are ingested):
1. `uv run kirana eval --tag iter2 --doc <id>` (core, writes `eval/results/iter2.json`)
2. `uv run kirana eval --suite hard --tag hard_iter2 --doc <id>`
3. optional k check: `--tag iter2_k5 -k 5` for both suites, so the effect of A+B alone can be separated from C.
Use the response cache; do not loop over the whole eval while debugging (use `--only`).

**Step E: report.**
- `eval/RESULTS.md` and `eval/RESULTS_HARD.md` already render baseline vs latest side by side; check they pick `iter2` / `hard_iter2` as latest.
- Fill `eval/ITERATIONS.md`: for each metric, baseline vs iteration 2, predicted vs actual, one honest sentence. List every
  question whose outcome changed (fixed, newly broken, unchanged failure). Say which of A, B, C caused what, using the `iter2_k5` run.
- Update `eval/failure_analysis.md` / `failure_analysis_hard.md` with a short "after iteration 2" section: what is still failing and why.
- Update the README results table (add an "iteration 2" column) and "what I would do with another week".
- `uv run ruff check`, `uv run ruff format`, `uv run pytest` all clean.

## 5. Rules for the implementing session

- Same rules as the baseline plan section 6: honest numbers, never print/log/commit the API key, no `.env*` or PDFs in git, simple readable code.
- Do not edit the eval questions, `must_contain`, or `gold_*` labels to improve a score. Do not delete baseline results.
- Do not implement anything from section 6; resist it even if a fix looks easy.
- If something regresses, keep the evidence, say so, and decide keep/revert in `docs/decisions.md`.
- Commit locally after each step. Push only when the author says so.
- Finish with a summary: predicted vs actual table, questions that changed, anything worse, open questions for the author.

## 6. Deliberately left for the third iteration (do NOT do now)

Candidates, ordered by the baseline evidence (finalise `THIRD_ITERATION_IMPLEMENTATION_PLAN.md` from iteration 2's numbers):

1. Meaning-based retrieval: local dense embeddings (`fastembed`, `BAAI/bge-small-en-v1.5`) fused with BM25 (reciprocal rank fusion). Targets h01 (table with zero word overlap), h03, synonym and conceptual ranking.
2. Verify image transcripts: two-run agreement or a check pass over each diagram edge and chart value; flag disagreement as "needs review". Targets q14 and the vision non-determinism limitation.
3. Table-aware retrieval: when one chunk of a table is retrieved, bring the whole table, or none; short natural-language description per table chunk.
4. Calculator tool for arithmetic (the 1.72 vs 1.71 slip), instead of model arithmetic.
5. Refusal threshold or a "partial evidence" rule, only if the harder set shows retrieval-score separation or confident wrong answers persist.
6. A larger, harder eval set (more types, chunk-level labels everywhere, a second document) so the next deltas are not limited by a 38-question sample.

Expected state after this iteration: h01 and q14 still failing, synonym and conceptual questions still ranking low. That is the point: it
gives the third iteration real work and keeps each step in the git history small and attributable.
