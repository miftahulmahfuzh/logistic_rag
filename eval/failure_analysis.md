## Failure analysis (hand-written after reading every failure in `baseline`, `baseline_k3`, `baseline_k8`)

See also `failure_analysis_hard.md` / `RESULTS_HARD.md` for the harder 18-question set, where the baseline is clearly weaker.

Honest headline first: the baseline scores high (k=5: 95% status, 100% facts, 95% judge, 100% hit@5, 100% citations
verified). With 20 questions on a 13-page document, **this test set is probably too easy** to separate good from bad
retrieval: 100% of questions reach hit@3. One question fails outright, and the more informative signal is in the
weaker numbers below the headline. Both eval sets have since been reviewed by the author.

### q14 (diagram, `baseline` k=5): wrong refusal. Failing stage: **ingestion (VLM transcription)**

- Evidence: the page 7 crop shows `Hat Yai -- 18 trucks/day (cross-border) --> Shah Alam`. The committed transcript says
  `Lat Krabang (main hub) -- 18 trucks/day (cross-border) --> Shah Alam`. Retrieval is fine (p7-f1 at rank 1) and the oracle
  pass fails identically (refused, judge wrong), so the generator is correct to refuse: the text it was given does not
  contain a Hat Yai to Shah Alam edge. It even states what the transcript does say.
- Note: an earlier ingest run (older prompt) transcribed this edge correctly, so the VLM is non-deterministic on graph
  topology even at temperature 0. I did not re-roll to get a better number.
- Proposed fix: verify diagram transcripts (second VLM pass that checks each edge against the crop, or ask for edges
  in a structured form and compare two runs, flagging disagreement). Longer term: a dedicated diagram prompt that lists
  node positions first, then edges.

### Systemic limitation: vision output is non-deterministic and unverified

q14 is one instance of a general property. Every fact that exists only in an image (charts, KPI cards, the diagram, the
scanned tariff: 9 of the 20 questions) reaches the answer through a `glm-4.6v` transcript that (a) can differ between
runs at temperature 0 (seen on the Figure 3 diagram, and on whether a chart title is transcribed at all) and (b) is never
checked. On this report the transcripts matched the page images on every number I compared (all six KPI cards, all chart
values, all seven tariff rates), so only the diagram's edge topology was wrong. The score is therefore a measurement of
**one ingest run**: re-ingesting with a cleared cache can move image-question results in either direction. The response
cache pins the committed run, which is why `kirana eval` is repeatable, but repeatable is not the same as reliable.
I state this as a system limitation rather than hiding it behind the cache.

### Weaker signals that are not outright failures

1. **Gold-page hit overstates retrieval for tables (retrieval metric weakness).** A hit means any chunk covering a gold
   page, so the prose chunk `p7-x1` counts for q04/q05/q06 even though the answer is in the table chunk `p7-t1`. The
   table chunk's actual ranks: q04 rank 3, q05 rank 2, q06 **rank 5**, q07 (`p9-t1`) rank 3. Hypothesis: BM25 prefers
   prose that repeats the question words ("utilisation", "cold") over a table whose cells are numbers and codes.
   Evidence it matters: at k=3 q06 is wrongly **refused** ("the table itself is not included in the excerpts"), and
   false-refusal rate rises from 0% (k=8) to 6% (k=5) to 12% (k=3). Stage: retrieval. Fix: dense/hybrid retrieval, plus
   a chunk-level (not page-level) gold annotation in the eval set.
2. **q01 at k=3 (retrieval depth):** the relevant chunks (p2-x1 CEO letter, p4-t1 Table 1) are not in the top 3; the
   model summed the quarterly chart to 8,420 but said growth could not be computed (judge: partial, status wrong). At k=5
   the first gold hit is rank 3 and the answer is correct. Stage: retrieval ranking. `p2-x1` states the revenue and
   growth but ranks below two chart chunks.
3. **q03 arithmetic (generation):** 2,310 / 1,347 = 1.7149, correct rounding 1.71. The generator wrote 1.72 in the oracle
   run and at k=3 (the deterministic check failed, the LLM judge said "correct", a recorded disagreement). It passes at
   k=5. The conclusion (within the 2.0x limit) is right either way. Stage: generation. Fix: compute arithmetic in code
   (a calculator tool) rather than in the model.
4. **q04 oracle citation page:** the model cited page 7 for the Cibitung row, which lives on page 8 of the merged table
   chunk (pages [7, 8]). The verifier accepts it (page belongs to the chunk) but `citation_page_ok` counts it wrong
   against gold page 8. This is a precision limit of chunk-level page metadata for merged tables: the chunk does not say
   which rows sit on which page. Fix: a per-row page column in merged tables.
5. **q08 conflict at k=3:** answered `answered` with the right content (82, mentions 96, cites errata) rather than
   `conflict`; this counts as wrong status (at k=3 only; k=5 and k=8 return `conflict`). Stage: generation (status choice).
6. **Refusal behaviour is good but untested at the margin.** All three unanswerable questions are refused (recall 100%).
   Refusal precision is 75% only because q14 was wrongly refused. The top BM25 score of an unanswerable query (2.5 to 6.3)
   overlaps the range of answerable ones, so a score threshold would not separate them; the refusal comes from the
   generator, not from retrieval. I did not add a threshold.
7. **q17 retrieval:** the only supporting page (13, "Schedule C not included") is rank 5 of 5. It would be lost at k=3,
   but the generator refuses anyway; being right for a weaker reason.

### Hypotheses from Appendix B

- No stemming/synonyms hurting conceptual questions: not demonstrated by this set (no failure traced to it). The set has
  no `flood`/`consolidation` style question; adding some is on the improvement list.
- Chart chunks ranking low: **not observed**. All chart/KPI/diagram/scan questions retrieve the right chunk at rank 1.
  The figure titles that the VLM transcribes carry enough vocabulary.
- VLM errors: confirmed once (q14), see above.
- Generator stretching on unanswerable questions: **not observed**.
- Conflict question: both p2 and p12 chunks at k=5: yes (p12-x2 rank 2, p2-x1 rank 5, p9-x1 rank 3).

### Weakest part and next steps (not implemented in this session)

**Weakest part: trust in the image transcripts** (one confirmed topology error, and the VLM is non-deterministic),
followed by **retrieval ranking of table chunks** that the page-level metric hides.

Ordered improvements:
1. Verify figure/diagram transcripts (second pass or two-run agreement), and surface a "needs review" flag.
2. Chunk-level gold labels in the eval set, plus harder questions (synonyms, conceptual wording, near-duplicate rows).
3. Stemming/synonym normalisation for BM25 (`utilisation`/`utilization`).
4. Local dense embeddings + hybrid (reciprocal rank fusion) so table chunks rank on meaning, not word overlap.
5. Arithmetic via a calculator tool instead of the model.
6. Refusal threshold only if the harder set shows retrieval-score separation (the current evidence says it does not).

## After iteration 2 (A table duplicate, B stemming, C k=8)

Still failing: **q14** (diagram edge attached to the wrong node by the vision model; the transcript is cached, so unchanged).
New: q03's `must_contain` check fails because the answer says "1.71-1.72x" (generator arithmetic wording, judge still correct), and
the oracle pass for q06 came back partial once (one misread value). Chunk recall@5 slipped 96% to 94% and the first-gold-chunk
rank got slightly worse on average under stemming; k=8 hides it. See `eval/ITERATIONS.md`.

## After iteration 3 (`iter3`, hybrid retrieval, k=8; separation run `iter3_bm25`)

Judge, status and facts are unchanged from iteration 2 (95% / 95% / 94%). Failures that remain:

- **q14 (diagram): still an image-transcription failure, not retrieval.** Gold chunk rank 1. The judge now gives `partial` instead of `wrong` because the answer
  reports the 18 trucks/day lane but attaches it to the wrong node. The committed transcript is cached and unchanged.
- **q03 (net debt/EBITDA): unchanged.** 1.71 vs 1.72 arithmetic wording, facts check fails, judge correct.
- Retrieval ranks changed: q01 first-gold chunk 6 to 3, q07 1 to 4 (3 with BM25 spelling-only: the table lost the rank that Snowball had given it), q13 1 to 2.
  No answer changed because k=8 contains all of them. Core page hit@1 is 82% (88% in iteration 2).
