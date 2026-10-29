# Fourth Iteration Plan: general ingestion fixes, measured with repeated runs

Why this exists: holdout v2 (`eval/failure_analysis_holdout2.md`) exposed ingestion weaknesses that the Kirana report does not have: interleaved
two-column reading order, footnotes glued to the neighbouring prose chunk, a table over three pages merged over two, a table of contents ingested as
a table chunk, merged header cells that turn the second header row into a data row. The author wants them fixed **without** breaking the recruiter's
unseen document, which is probably Kirana-like (single column, ruled tables). The author also wants answer-level comparisons made with
repeated runs, because one run on 28 questions cannot separate a one-question difference from LLM noise.

Read first: `eval/ITERATIONS.md` (Holdout v2 sections), `eval/failure_analysis_holdout2.md`, `docs/decisions.md`, `docs/ingestion_notes.md`,
`THIRD_ITERATION_IMPLEMENTATION_PLAN.md` sections 2 and 5, and `src/kirana_rag/ingest/` end to end.

## 1. Baselines this iteration is measured against (do not overwrite or delete any run on disk)

Retrieval only, hybrid + `spelling`, mean first-gold-chunk rank (`eval/results/ablation_v2.md`): Kirana pooled 1.41, holdout v1 1.45, holdout v2 2.70.
Answers, k=8, single runs: core 95% judge-correct, hard 94%, holdout v1 92%, holdout v2 89% (BM25-only 93%). Corpus: Kirana 27 chunks, Northmere 10, Halbrook 68.
Reference chunk files: copy `.cache/<doc_id>/chunks.jsonl` of all three documents to `eval/results/chunks_before/<doc_id>.jsonl` in Step 0 (small text files; they are
the "before" side of the regression check). All four question files are frozen: **do not edit any question, `must_contain`, `gold_text` or `gold_*` label.**
Gold chunk ids of holdout v2 refer to the *old* chunking; see Step E for how they are handled.

## 2. Generality rules (these override convenience)

1. **Nothing document-specific in `src/`.** `tests/test_generality.py` stays green; add words from any new synthetic test PDF to its forbidden list.
2. **Detect from layout, never from content or names.** Geometry (block x-ranges, font sizes, position on the page, ruling lines, dotted leaders) is allowed.
   Words ("Contents", "Note", "Table of", company or section names) are not. No per-document thresholds fitted to the three PDFs; thresholds are written down in
   Section 3 before any measurement and reasoned from typography (for example "a footnote is set at least 15% smaller than body text"), not tuned.
3. **A page that is not special must come out exactly as before.** Single-column pages, ruled single-page tables and figures must produce the same chunks
   (same text, same order). This is the regression contract, checked in Step A and Step F.
4. **Each fix must fail safe.** If the detector is unsure (a page that is ambiguous between one and two columns), keep the old behaviour.
5. **Test on layouts the three documents do not contain.** Every fix gets unit tests on small synthetic PDFs built with `tests/pdfmaker.py` or PyMuPDF
   (for example a three-column page, a footnote on a page with no table, a four-page table, a two-column page that also has a full-width heading and a full-width table).
6. Mechanisms, not rules: no synonym lists, no per-question handling, nothing tuned on the holdouts.

## 3. Pre-registered decisions and predictions (commit to `eval/ITERATIONS.md` BEFORE running any eval or re-ingesting any document)

Fixed in advance (not tuned; the implementing session may refine the mechanism, not these numbers, without recording why in `docs/decisions.md` before looking at results):
- **Columns:** a page is multi-column when its text blocks (excluding blocks that span more than 70% of the page width, which are full-width headings, captions and tables)
  fall into 2 to 3 groups whose x-ranges overlap by less than 5% of the page width and each group holds at least 3 blocks. Read order: full-width blocks and column groups in
  top-to-bottom bands; inside a band, column by column, each top to bottom. Otherwise: the current order.
- **Footnotes:** a block in the bottom 25% of the page, whose font size is at most 85% of the page's body size and that begins with a marker (a digit, a superscript digit or a symbol),
  becomes its own chunk of type `text`, section unchanged, and its marker is kept. Not merged with other prose.
- **Tables over N pages:** merge any run of consecutive pages where each continuation table has the same header row and the same column count and the previous one ends in the lower 60% of
  its page and the next starts in the upper 40% (the existing thresholds), without a limit on the number of pages.
- **Table of contents:** a block group whose lines mostly (at least 60%) end in a run of dots or spaces followed by a page number is treated as navigation, kept as a single text chunk
  with type `text` (not `table`).
- **Merged header cells:** when the first two rows of a table are a header band (the second row's first cell is empty, or the first row has empty cells between non-empty ones),
  fold them into one header row (`Inpatient / Elective`, ...). Otherwise leave as is.
- **Repeated runs:** N = 3 per answer-level comparison, with the response cache bypassed for the answer and judge calls (vision transcripts stay cached so the ingest is the
  only thing that changes). Report mean and min-max per metric. A difference counts as real only if the ranges do not overlap; otherwise it is "within noise".
- Default `k`, retriever and normalisation do not change.

Predictions (to be marked right or wrong afterwards):
1. Regression contract: re-ingesting Kirana and Northmere gives chunk text identical to the saved "before" files except where a fix applies; every difference is listed and explained
   (expected: none on Northmere, none or a footnote/ToC difference on Kirana). If any other difference appears, the fix is reported as not general and reverted or narrowed.
2. Halbrook re-ingest: the column pages read in order (`p4-x1` no longer jumps between columns; the glossary starts at its first term), the footnote becomes its own chunk
   (v15 gold moves to a footnote chunk), the ward table becomes one chunk over pages 13 to 15, the contents page becomes a text chunk, `p12-t1` has one header row. Chunk count 66 to 80.
3. Retrieval only: holdout v2 mean first-gold rank improves (below 2.70, using the Step E labels); Kirana pooled and holdout v1 do not get worse (<= 1.41 and <= 1.45).
4. Answers (3 runs each): holdout v2 judge-correct mean is at least as high as before and v15 is correct in at least 2 of 3 runs. Kirana core, hard and holdout v1 means stay within the
   baseline's noise range. The v12 failure may persist (it is a ranking issue); say so if it does.
5. Noise: the run-to-run range on holdout v2 judge-correct is at least 2 questions (7 points) wide. This is a prediction about the noise, and it decides how to read everything else.
6. Risk: the column detector misclassifies at least one page of Kirana or Northmere (for example a KPI-card page with several narrow blocks). If so, record the page and tighten the detector from
   typography, not from that page's content.
7. Hybrid vs BM25 on holdout v2 after the fixes: within noise at answer level.

## 4. Implementation steps (commit locally after each; conventional commits; attribution line from the system reminder; push to origin main when finished)

**Step 0: protect the baseline.** `git status` clean, `uv run pytest -q` passes. Copy the three `chunks.jsonl` files as in Section 1. Add a "Iteration 4" section to
`eval/ITERATIONS.md` with Section 1's table and Section 3's decisions and predictions. Commit: `docs(eval): iteration 4 predictions`.
Nothing is re-ingested and no eval is run before this commit.

**Step 1: repeated-run support (no behaviour change).** Add an option to bypass the response cache for answer and judge calls (for example `--repeat N` on `kirana eval`, which runs N
times with a per-repeat cache salt and writes `eval/results/<tag>_r1.json` ... `_rN.json`; vision calls keep using the cache). Add a small summariser (script or
`kirana eval --summarise <tag>`) that prints mean and min-max per metric over the repeats. Unit tests with the LLM mocked. Default behaviour of every existing command is unchanged.
Commit: `feat(eval): repeated runs with a cache salt and mean/range summary`.

**Step 2: baseline noise measurement on the old chunks.** Before touching ingestion, run 3 repeats (`holdout2_baseline_rN`, `hard_baseline_rN`... name them `before_<suite>_rN`) of all four suites on the
current ingest with the default code. This is the "before" side with its noise range. Commit the JSON results: `feat(eval): iteration 4 before-fix repeated runs`.

**Step 3: ingestion fixes, one commit each, each with its synthetic-PDF unit tests and a regression check against the saved chunk files.**
A. Multi-column reading order. B. Footnotes as their own chunks. C. Tables over any number of pages. D. Table-of-contents detection. E. Merged header cells.
Commit messages: `fix(ingest): ...`. After each, re-run `uv run pytest -q`; after A to E, the regression script must show Kirana and Northmere unchanged apart from listed, explained differences.
Write that check as `scripts/chunk_diff.py <before.jsonl> <after.jsonl>` (prints added, removed, changed chunks by text); keep it in the repo.

**Step 4: re-ingest and re-label.** Re-ingest the three PDFs with `--force` (vision stays cached by image hash, so charts and scans do not change; if the doc id changes because the PDF bytes were regenerated,
say so and use the original PDFs, not regenerated ones). Run `scripts/chunk_diff.py` for all three and put the summary in `eval/ITERATIONS.md`.
Holdout v2 gold chunk ids refer to the old chunking: re-run `scripts/resolve_gold_chunks.py` from the frozen `gold_text` into a **new file** `eval/questions_holdout2_v2chunks.yaml` (a copy; the frozen file
is not touched) and use that file for iteration 4 runs. Do the same for any Kirana or Northmere question whose gold chunk id no longer exists (copy files, never edit the originals; if none is needed, say so).
Commit: `feat(ingest): re-ingest with iteration 4 fixes`.

**Step 5: measure.** (a) Retrieval-only ablation on all four sets (`scripts/retrieval_ablation.py`, pointing at the relabelled holdout v2 file). (b) 3 repeats of all four suites with the new ingest
(`after_<suite>_rN`). (c) One BM25-only repeat set on holdout v2 (3 runs) for prediction 7. Commit results: `feat(eval): iteration 4 measurements`.

**Step 6: report.** Fill the Iteration 4 section of `eval/ITERATIONS.md`: before vs after with mean and range per suite, retrieval table, the chunk-diff summary, predicted vs actual, every question
whose outcome changed in a majority of runs, anything worse. Update `eval/failure_analysis_holdout2.md` with an "after iteration 4" section (which weaknesses are fixed, which remain),
the README (limitations list: remove what is fixed, keep what is not; results; "what I would do with another week"), and `docs/decisions.md`. Update the Kirana and Northmere failure analyses only if their numbers changed.
`uv run ruff check`, `uv run ruff format`, `uv run pytest` clean. Commit: `docs: iteration 4 report`. Push to origin main.

## 5. Rules for the implementing session

- Honest numbers; never print, log or commit the API key; no `.env*` or PDFs in git; simple readable code that reads like the surrounding code.
- Pre-register before running; do not edit any frozen question file, `must_contain` or label; do not tune any threshold or setting on any holdout; if a detector misfires, tighten it from typography and say so.
- A fix that changes Kirana or Northmere chunks unexpectedly is a failed generality test: narrow it or revert it and record why in `docs/decisions.md`.
- Do not change the default normalisation, retriever or k. Do not implement Section 6.
- If a result is worse, keep the evidence and decide keep/revert in `docs/decisions.md`.
- Finish with a summary: predicted vs actual, before vs after with ranges, what changed on Kirana (it must be nothing unexplained), anything worse, open questions.

## 6. Left for a later iteration (do NOT do now)

1. Retrieval changes (dense rank dilution by mixed-topic chunks, cross-encoder reranking, table-aware retrieval).
2. Verifying image transcripts (two-run agreement).
3. Calculator tool for arithmetic.
4. Tables inside images, rotated pages, right-to-left text, real scanned documents with OCR noise.
5. A real third-party document.
