## Failure analysis, holdout set (`holdout_iter2`, current code before iteration 3, k=8)

13 questions on a different fictional document (Northmere Wind and Solar plc, 7 pages, **10 chunks**). Measured with the iteration 2
code, before any iteration 3 change. This is the holdout baseline.

**Caveat on this set:** the corpus has only 10 chunks, so top-8 retrieval returns most of the document and hit@8 is trivially
100%. The informative retrieval numbers are the first-gold-chunk rank and hit@1/recall@5. Answer metrics at k=8 mostly measure the
generator.

### w07 (synonym): wrongly refused. Failing stage: **retrieval** (table not in the top 5, but the rule chunk is rank 1)

- Question: "Which sites are underperforming enough to trigger a performance review?" The prose chunk `p4-x1` (the 92% rule) is rank 1;
  the site table `p4-t1` is not in the top 5, because the question shares no words with the table. The generator saw the rule
  and no per-site figures and refused (judge: partial). The same failure shape as Kirana h01. Oracle context answers it correctly.

### w04 (synonym): correct answer, but the gold table is retrieved at rank 8

- "Which site can generate the most electricity, and how much?" Top 5: p6-f1, p1-x1, p6-x1, p2-x1, p3-t1; the gold table `p4-t1` is
  rank 8, right at the edge of k=8. It was answered correctly only because the table fit in the context. This is the fragile case.

### w03, w09: gold chunk at rank 2 (fine). w05: cites a non-gold page (answer correct).

No other failure. Unanswerable w11, w12 refused correctly; false premise w13 answered correctly.
