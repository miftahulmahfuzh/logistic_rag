# Decisions and deviations from the plan

One line per decision, dated.

- 2026-10-29: Python pinned to 3.12 (`.python-version`); `uv` had otherwise picked 3.14.
- 2026-10-29: Header/footer stripping also requires the line to sit in the top or bottom 12% of the page, on top of "repeats on >= 50% of pages" (and >= 2 pages). Reason: a body heading repeated on two pages of a short subset PDF must not be dropped.
- 2026-10-29: Vision prompt got one generic sentence, "Begin with its title, heading or caption line if it has one". Reason: the first ingest run silently dropped the title of the revenue-by-country chart. The change was made after viewing the ingest output, before any eval run; no question text was consulted.
- 2026-10-29: A figure is typed `scan` when its image covers >= 60% of the page or the page has < 150 text chars. The plan said "full-page scan"; the tariff page image covers 69% of the page, not 100%.
- 2026-10-29: A caption (`Figure|Fig.|Chart N` for images, `Table N` for tables) is removed from the prose chunks when it is attached to a table/figure, so its words are indexed once.
- 2026-10-29: Chunk ids are `p<page>-<letter><n>` with `t` table, `f` figure, `x` text, `s` scan. When a retrieval set spans several documents and two ids collide, the prompt and citation verifier use `<doc_id>/<chunk_id>`.
- 2026-10-29: Vision transcripts are NOT deterministic even at temperature 0 (the Figure 3 diagram came back with a different edge assignment on a second run, see docs/ingestion_notes.md). The on-disk response cache pins whichever transcript was produced by the run whose output is committed in the eval results.
