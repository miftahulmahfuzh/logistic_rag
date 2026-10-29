## Failure analysis, hard set (`hard_baseline`, k=5)

The hard set (18 questions, written before any improvement work) exists to make the "baseline, measure, fix, measure
again" loop visible. It does: **retrieval-limited, not generation-limited.** Given the gold pages directly (oracle) the
generator gets **100%** status, facts and judge; with retrieved context it gets 94% status, 87% facts, 89% judge.
Retrieval hit@1 is 53% (page-level) / 33% (chunk-level) against 76% on the core set.

### h01 (synonym): wrongly refused. Failing stage: **retrieval** (table chunk missing)

- Question: "Which warehouses are underused, below the level that triggers a closure review?" Top 5: p7-x1, p3-x1, p2-x2,
  p3-s1, p9-x1. The facilities table `p7-t1` is **not retrieved at all**: the question shares no words with the table
  header or rows. The prose chunk `p7-x1` (the 65% watch-list rule) is rank 1, so the generator saw the rule but no
  utilisation numbers and refused ("does not provide utilisation figures"). That is a correct refusal given its context.
- Oracle context: correct. Proposed fix: dense/hybrid retrieval, and expanding table chunks with a short natural-language
  description.
- Metric note: page-level hit@1 and chunk-level "any gold chunk" both score this question as a hit because the prose chunk
  is also a gold chunk. Chunk-level **recall@5** (83%) is the honest metric for multi-chunk questions.

### h04 (table): wrong answer. Failing stage: **retrieval ranking**

- "Which single warehouse has the largest floor area?" The table `p7-t1` ranks **6th** (score 1.01), outside k=5. The
  generator saw only the continuation-page prose chunk `p8-x1`, which holds the second half of Table 2 as flattened
  text (see below), so it answered Surabaya (33,500 sqm), the largest site on that half, with confidence, and said "per the
  facilities table". Wrong answer, correct-looking citation. Oracle context: correct.
- This is the dangerous failure type: not a refusal but a confident wrong answer, because the missing evidence was
  *partially* present. A "list partial evidence" rule or retrieving all chunks of a table together would help.
- **Ingestion defect found through this question (root cause confirmed in code and data):** the merged table chunk
  `p7-t1` (pages 7 and 8) is correct, but page 8's text-layer rows are **also** emitted as a flattened prose chunk
  `p8-x1` ("Code Location Country Type Area (sqm) Utilisation 2025 Opened ID-CBT Cibitung, Bekasi ..."). Cause:
  `pipeline.py` marks the table's text blocks as consumed only while processing the page where the table *starts*; after
  the cross-page merge the continuation table is removed from page 8's list, so page 8's blocks are never excluded from
  prose. The core set did not expose it (the duplicate usually helps there). I have **not** fixed it, because the baseline
  must stay as measured; it is the first item of the improvement list, and the fix should be visible as a delta.

### h15: not a system failure. A bad question (fixed, documented)

The first run marked facts wrong because `must_contain` required the city names; the answer listed the same sites by
code (ID-CKR, ID-CBT) and the LLM judge said correct. I corrected the question's `must_contain` to accept codes and
re-scored from the cached answer. Facts correct went 80% to 87%. I did not change any other question.

### Weaker signals

- Synonym questions rank poorly but still reach the top 5 (hit@1 25%, MRR 0.58), and conceptual questions rank their gold
  page 2nd. Hit@5 is 100% for those types, so k=5 hides the ranking problem; k=3 would not.
- `h05` (US spelling "utilization"): the table is rank 3 and the answer is right, because other terms (Cikarang) carried the
  match. The no-stemming hypothesis is real but was masked by a second keyword.
- Refusal: all three near-miss unanswerable questions (NPS 2023, salary, ransomware cost) are correctly refused. Refusal
  precision is 75% only because of h01.
- Citation page accuracy is 87% (vs 100% on the core set) because some answers cite pages outside the gold pages.

### What this set says about the next steps

Ordered by evidence: (1) fix the merged-table duplicate chunk (ingestion bug above, one function);
(2) dense/hybrid retrieval, expected to lift h01 and h04 and the synonym/conceptual ranking;
(3) stemming/spelling normalisation (cheap, helps h05-like cases); (4) table-aware retrieval (retrieve a whole table
or none); (5) re-run both sets and report the delta. Generation changes are
not justified by this data: oracle accuracy is already 100%.

## After iteration 2 (A table duplicate, B stemming, C k=8)

Still failing: **h01** ("underused warehouses": the table shares no words with the question; the model refuses). Needs
meaning-based retrieval. h04 is fixed (judge correct) but fragile: the table ranks 7th, so it is only answered because k=8 reaches it
(refused at k=5). Retrieval got worse for h04, h05 and h12 under stemming (see `eval/ITERATIONS.md`): chunk recall@5 fell from 83% to 73%.
The duplicate `p8-x1` no longer exists. Unanswerable questions are still all refused.

## After iteration 3 (`hard_iter3`, hybrid retrieval, k=8; separation run `hard_iter3_bm25`)

Retrieval is now the strongest part of the hard set: chunk recall@5 73% to 93%, hit@1 60% to 87%, status 100%, facts 100%, no false refusals.

- **h01 fixed.** The table chunk is retrieved (rank 1) although the question shares no words with it; the BM25-only run (`hard_iter3_bm25`) still refuses. Mechanism: the dense ranking.
- **Ranks that moved up:** h04 7 to 2, h05 6 to 3, h12 5 to 1, h03 4 to 1, h13 2 to 1. Down: h06 1 to 2.
- **h09 now `partial` (was correct).** Not a retrieval problem: the gold chunk is rank 1 in both runs. The generator answered "Yes" then "NOT above" (self-contradicting)
  with the same figures in a different context order; the BM25-only run gave "Yes" with a wrong conclusion (`wrong`). Generator noise on a comparison question; one run each.
- Judge correct stays at 94% (one fixed, one lost to generator noise).
