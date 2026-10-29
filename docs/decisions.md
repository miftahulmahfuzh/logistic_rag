# Decisions and deviations from the plan

One line per decision, dated.

- 2026-10-29: Python pinned to 3.12 (`.python-version`); `uv` had otherwise picked 3.14.
- 2026-10-29: Header/footer stripping also requires the line to sit in the top or bottom 12% of the page, on top of "repeats on >= 50% of pages" (and >= 2 pages). Reason: a body heading repeated on two pages of a short subset PDF must not be dropped.
- 2026-10-29: Vision prompt got one generic sentence, "Begin with its title, heading or caption line if it has one". Reason: the first ingest run silently dropped the title of the revenue-by-country chart. The change was made after viewing the ingest output, before any eval run; no question text was consulted.
- 2026-10-29: A figure is typed `scan` when its image covers >= 60% of the page or the page has < 150 text chars. The plan said "full-page scan"; the tariff page image covers 69% of the page, not 100%.
- 2026-10-29: A caption (`Figure|Fig.|Chart N` for images, `Table N` for tables) is removed from the prose chunks when it is attached to a table/figure, so its words are indexed once.
- 2026-10-29: Chunk ids are `p<page>-<letter><n>` with `t` table, `f` figure, `x` text, `s` scan. When a retrieval set spans several documents and two ids collide, the prompt and citation verifier use `<doc_id>/<chunk_id>`.
- 2026-10-29: Vision transcripts are NOT deterministic even at temperature 0 (the Figure 3 diagram came back with a different edge assignment on a second run, see docs/ingestion_notes.md). The on-disk response cache pins whichever transcript was produced by the run whose output is committed in the eval results.
- 2026-10-29: Added a second, harder eval set (`eval/questions_hard.yaml`, 18 questions, written before any improvement) at the author's request, because the core set is too easy to show a baseline-to-improved delta. The brief asks for 15-20 questions: the 20-question core set is the brief's eval set, the hard set is an extension. Results go to `RESULTS_HARD.md`.
- 2026-10-29: Added optional chunk-level gold labels (`gold_chunks`) and chunk recall@k, because page-level hits let a prose chunk on the right page count as a hit for a table question.
- 2026-10-29: Corrected h15's `must_contain` after seeing the first answer (it required city names; the table also names sites by code). Answer was right; recorded in the question notes.
- 2026-10-29: `kirana eval` now refuses to run when more than one document is ingested without `--doc`. A first hard/core re-run silently included a 4-page subset document (from the generality demo) in the corpus and polluted the metrics; those runs were discarded and the subset cache removed before the committed results were produced.
- 2026-10-29: Token prices added to `config.py` from docs.z.ai/guides/overview/pricing (glm-5.3 $1.4 in / $4.4 out per M tokens; glm-4.6v $0.3 / $0.9). The author pays a flat subscription, so dollar figures are list-price equivalents.
- 2026-10-29: Known ingestion defect left unfixed on purpose so the baseline stays as measured: the continuation page of a merged table also emits a flattened prose chunk (see `eval/failure_analysis_hard.md`). First item of the improvement list.
- 2026-10-29: Author reviewed both eval sets (questions.yaml, questions_hard.yaml); status changed from DRAFT to REVIEWED.
- 2026-10-29: Iteration 2, change A (merged-table duplicate fixed): the known defect above is resolved; corpus 28 -> 27 chunks.
- 2026-10-29: Iteration 2, change B: BM25 tokenizer applies `isation(s)?` -> `ization`, a short UK->US dict and the English Snowball stemmer (`snowballstemmer`, pure Python) to tokens without digits; same function for index and query. No synonym lists. Reason: baseline hypothesis "no stemming"; h05 only passed via a second keyword. Keep/revert is decided after the measurement (see eval/ITERATIONS.md).
