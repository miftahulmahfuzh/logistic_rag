## Failure analysis, holdout v2 (`holdout2_baseline`, current code, hybrid + `spelling`, k=8; separation run `holdout2_bm25`)

28 questions on the Halbrook Regional Health Group report (30 pages, **68 chunks**). The questions and their `gold_text` were frozen before the
document was ingested; gold chunk ids were assigned by script from the first ingest (all 23 questions with evidence resolved). Nothing in `src/` was
changed for this document and no ingestion weakness was fixed: they are recorded here and left for a separate plan.

Headline: judge-correct 25/28 (89%) hybrid, 26/28 (93%) BM25-only; oracle context 28/28 in both. Every non-correct answer is a
context problem (the right chunk missing from the top 8, or in the wrong place inside a chunk), never a generation failure on gold context.
Page hit@8 is 100% (23/23) but chunk hit@8 is 91% (21/23): the two misses are v12 (hybrid rank 9, BM25 rank 6) and v15 (hybrid rank 13, BM25 rank 34).

### Ingestion weaknesses the document exposed (recorded, not fixed)

| weakness | evidence | effect on this eval |
|---|---|---|
| **Two-column reading order is interleaved.** Blocks are sorted by y then x, so the paragraphs of the left and right column alternate and a sentence that runs across the column break is cut in two | `p4-x1` starts "Dear colleagues and partners," then jumps to "rebuilding of the emergency department ..." (a sentence from the right column), then back; `p9-x1`, `p23-x1` (glossary starts "hospital between admission and discharge.") and `p6-*` (Medication safety before Mortality) are scrambled the same way; `p5-x4` joins a signature with the cut-off sentence "Pennine Orthopaedic Centre completed 11.2 thousand" | Chunks still contain the facts, so most questions are unaffected; v12's evidence is split across `p4-x1` and `p4-x2` by this, and the section label of several chunks is wrong (`p27-x3` is labelled "Water" but holds the travel paragraph). v16 (a sentence across the column break) was still answered correctly because both halves landed in `p10-x1` |
| **A table over three pages is merged across two** (the merge loop folds a table into the next page once) | `p13-t1` covers pages 13 and 14, `p15-t1` is a separate chunk that repeats the header | v07 (page 2 of the table) and v08/v09 (page 3) were answered correctly; the cost is that "highest occupancy" has to be assembled from two chunks (v09 gold `p15-t1` is rank 4 hybrid, 6 BM25, and the answer was right because the page-15 table was in the top 8) |
| **Merged header cells** become a header with an empty cell and the second header row becomes a data row | `p12-t1`: `\| Hospital \| Inpatient \| \| Outpatient \| \|` then `\| \| Elective \| Day case \| First \| Follow-up \|` | Values are intact and in the right columns; v06 correct. Risk (not realised here): a reader could pair a number with the wrong group header |
| **Footnotes are not separated from prose**: the footnote text is merged into whichever prose chunk sits next to it, and its marker stays in the body | `p8-x4` ("Training and development") ends with the footnote "¹ Headcount excludes Halbrook Rehabilitation GmbH ..." | **v15 failed**: the answer to "does 17,940 include the German clinic?" is in a chunk about training, rank 13 (hybrid) / 34 (BM25) |
| **A table of contents becomes a table chunk** (212 words, dotted leaders) | `p2-t1` | No question hit it; it did not appear in any top 8 inspected. It contains every section title, so it is a standing distractor for "where is X" queries |
| Page 14 has no chunk of its own and the headings on the ward pages are repeated | summary table in the ingest output | none |

Predicted but **not** observed: the table without ruling lines (Table 5, `p17-t1`) was detected and extracted cleanly (v10 correct, rank 2/1); the chart
and scan transcripts (`p10-f1`, `p11-f1`, `p25-s1`) have every value right (v18, v19, v20 correct). The euro-format table (`p22-t1`) kept `48.213,5`
verbatim (v11 correct). The landscape page (`p18-t1`) became one table chunk.

### Question-level failures

| id | hybrid | BM25 | what happened |
|---|---|---|---|
| **v12** (conceptual: why did capex rise) | **wrong** (refused) | partial | The reasons are in `p4-x2` (the Chair's review chunk that holds the "largest projects" sentence, split from its first half by the column interleave). Hybrid rank 9 (BM25 rank 6, dense rank 14; the chunk opens with a paragraph about board changes because of the column interleave, which probably dilutes its embedding), just outside k=8: the top 8 was filled with the cash-flow and five-year tables (`p28-t1`, `p29-t1`, `p29-x1`, `p9-t1`) that match "capital expenditure" and "rise". BM25 had it at rank 6, but the answer named only one of the three projects. Retrieval failure with an ingestion contribution; the clearest case in the four sets where a retrieval difference reaches the answer |
| **v15** (footnote) | partial | partial | See the footnote row above. The answer said "no" but missed the 612 figure. Retrieval failure caused by the footnote being glued to an unrelated chunk |
| **v14** (synonym: avoidable incidents) | partial | correct | Gold `p6-x1` is rank 1 for both. The hybrid answer states "two" but drops "one fewer than 2024"; the same chunk was in context in both runs. Generator / judge strictness, not retrieval (the deterministic facts check passes in both; `disagree` is flagged) |

Everything else is correct under both retrievers, including the conflict (v21: 11.2 weeks in the Chief executive's report vs 11.6 in Table 5 and
Figure 2, status `conflict` both runs), all five unanswerable questions (v22-v26, 5/5 refused, including the missing Appendix D)
and both false premises (v27, v28).

### Hybrid vs BM25 on this document

- Retrieval only (full ranking, 23 questions): mean first-gold-chunk rank 2.70 hybrid vs 3.57 BM25 (spelling normalisation); hit@1 57% vs 52%, recall@5 85% vs 78%.
  Hybrid is better at the rank level on average, but not on every question: v09 improves from rank 6 to 4, v12 gets worse from 6 to 9.
- Answers: 89% vs 93% judge-correct, 4.3% vs 0% false refusals. The difference is v12 (a retrieval miss that hybrid has and BM25 does not) and v14 (noise).
  With one run each, 1 question is 3.6 points, so this says "no answer-level advantage for hybrid on this document", not "BM25 is better".
- The prediction that retrieval differences would become visible in answers was right in direction for v12 (a chunk at rank 9 instead of 6 changed an
  answer), but the net answer difference went against hybrid.

### What this document does not test

Single fictional report written by the same author as the code; the generator makes tables clean (real scans and spanning tables are messier).
The scan is typed text at a 0.6 degree tilt, JPEG at 110 dpi, which the vision model reads perfectly.
