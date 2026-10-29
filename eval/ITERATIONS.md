# Iterations: baseline vs iteration 2

Same two question sets, unchanged. Baseline = `baseline` / `hard_baseline` (k=5).

## Baseline (k=5)

| metric | core (20) | hard (18) |
|---|---|---|
| retrieval hit@1 / hit@5 (page) | 76% / 100% | 53% / 93% |
| chunk-level recall@5 | 96% | 83% |
| status / facts / judge correct | 95% / 100% / 95% | 94% / 87% / 89% |
| false-refusal rate | 6% | 7% |
| oracle judge correct | 95% | 100% |
| corpus | 28 chunks | 28 chunks |

## Iteration 2 changes

- A: fix the merged-table duplicate chunk (`p8-x1`) in ingestion.
- B: BM25 tokenizer normalisation (UK to US spelling, Snowball stemming, digit tokens untouched).
- C: default k from 5 to 8.

## Pre-registered predictions (written before running the eval)

- A: corpus drops from 28 to 27 chunks; `p8-x1` no longer exists; Table 2 stays one chunk with 23 rows on pages [7, 8].
  Retrieval for q04, q05, q06, h06, h15 changes slightly. Expect h04 to improve.
- B: h05 table rank improves or stays; no regression on number-heavy questions.
- C: false-refusal rate falls toward 0% on core; hit@8 unchanged (already 100%); cost rises about 40-60%;
  risk: more context may make the generator stretch on unanswerable questions (watch refusal recall) and add unverified citations.
- Overall: hard judge-correct up by about 1 question (h04); h01 still fails; core stays at or near 95-100%.

## Results (runs on disk: `iter2`, `hard_iter2` at k=8; `iter2_k5`, `hard_iter2_k5` at k=5)

The k=5 runs isolate A+B from C. Judge and generator are LLMs: one run per setting, so a one-question swing is within
noise (core and hard have 20 and 18 questions).

### Metrics: baseline vs iteration 2 (k=8), predicted vs actual

| metric | baseline core / hard | iter2 core / hard | iter2 at k=5 (A+B only) core / hard | prediction | verdict |
|---|---|---|---|---|---|
| corpus chunks | 28 / 28 | 27 / 27 | 27 / 27 | 28 to 27, `p8-x1` gone, Table 2 one chunk, 23 rows, pages [7, 8] | **right** |
| hit@1 (page) | 76% / 53% | 88% / 60% | n/a (retrieval is the same at any k) | not predicted | up |
| hit@5 / hit@8 (page) | 100% / 93% and 100% / 100% | 100% / 93% and 100% / 100% | same | hit@8 unchanged | **right** |
| chunk recall@5 | 96% / 83% | 94% / 73% | same | "retrieval changes slightly" | **worse** on hard (-10 pts) |
| status correct | 95% / 94% | 95% / 94% | 85% / 83% | core stays ~95-100% | right |
| facts correct | 100% / 87% | 94% / 93% | 94% / 80% | not predicted | core down 1 question (q03, see below) |
| judge correct | 95% / 89% | 95% / 94% | 90% / 83% | hard +1 question (h04), core 95-100% | **right** (hard +1) |
| oracle judge correct | 95% / 100% | 89% / 100% | not rerun at k5 | not predicted | core -1 question (q06 partial, oracle generator slip: the oracle context lost the duplicate chunk only) |
| false-refusal rate | 6% / 7% | 6% / 7% | 12% / 20% | "falls toward 0% on core" | **wrong**: still q14 (core) and h01 (hard); both are the expected unchanged failures |
| refusal recall | 100% / 100% | 100% / 100% | 100% / 100% | watch for stretching | **no stretching observed** |
| answer-call cost (list price) | $0.0475 / $0.0402 | $0.0573 / $0.0515 | $0.0472 / $0.0391 | +40-60% | **wrong**: +21% core, +28% hard (the cost is the k=8 context; A+B at k=5 is flat) |
| citations verified by code | 100% / 100% | 100% / 100% | 100% / 100% | possible unverified citations | no unverified citation seen |
| h05 table rank (B) | 3 | 6 | 6 | "improves or stays" | **wrong**: worse (see below) |

### Questions whose outcome changed

Judged on the LLM judge plus status, baseline to iter2 (k=8):

| question | baseline | iter2 | cause |
|---|---|---|---|
| h04 (largest warehouse) | wrong (answered from the partial duplicate) | **correct** | A (duplicate gone) plus C (table is rank 7, only inside k=8). At k=5 it is refused (`hard_iter2_k5`). |
| q03 (net debt/EBITDA) | correct, facts ok | judge correct, facts **fail** | generator arithmetic wording: 1.71-1.72x vs expected "1.71". Model arithmetic noise, not retrieval. |
| q14 (diagram) | wrong (refused) | wrong (refused) | unchanged: the committed transcript attaches the 18 trucks/day edge to the wrong node. |
| h01 (underused warehouses) | wrong (refused) | wrong (refused) | unchanged, as predicted: no word overlap, needs meaning-based retrieval. |
| q06 (oracle only) | correct | partial | oracle generator misread a utilisation figure; not caused by A. |
| everything else | same status and judge | same | |

At k=5 (A+B alone) the picture is worse than baseline: q01 refused (partial), h04 and h05 refused (wrong), q08 status
answered instead of conflict. That is the retrieval change B shifting ranks, with k=5 too shallow to absorb it.

### Which change did what

- **A (duplicate)**: did what it said. Corpus 27, no `p8-x1`. The duplicate no longer competes; h04's table moved up to rank 5 under A alone.
- **B (stemming and spelling)**: **mixed, net slightly negative on the ranks, kept for the reason below.** Retrieval-only comparison on all 32
  questions with gold chunks (A alone vs A+B, no LLM): better for q07 (3 to 1), q08 (2 to 1), h10 (3 to 1); worse for q01 (4 to 6),
  h03 (3 to 4), h04 (5 to 7), h05 (3 to 6), h12 (2 to 5). Mean first-gold-chunk rank 1.72 to 1.91. Stemming makes common stems
  ("warehous", "utiliz", "revenu") match many more chunks, which flattens the discriminating keywords. My pre-registered B prediction
  (h05 improves or stays) was wrong.
- **C (k=8)**: the one that moved the answer metrics. At k=5 A+B gives judge 90% / 83%, at k=8 95% / 94%; false refusals 12% / 20% at k=5 vs 6% / 7% at k=8.
  Cost +21-28%. The core set false-refusal rate did not reach 0% because q14 (vision) remains.

### Honest reading

Improvements: h04 fixed, hit@1 up (76 to 88% core, 53 to 60% hard), hard judge-correct 89 to 94%. Not improved: h01, q14 (as predicted), core
false-refusal rate. Worse: chunk recall@5 on the hard set (83 to 73%), q03 facts, core oracle (-1 question, generator noise), and the
cost rise is lower than predicted. The gain is almost entirely from the deeper context (C) fixing a retrieval order that got **worse**
under B; that is a depth workaround, not a ranking improvement. With 38 questions and single runs, this is directional only.

---

# Iteration 3: meaning-based retrieval, a stemmer decision, and a generality holdout

Plan: `THIRD_ITERATION_IMPLEMENTATION_PLAN.md`. Everything in this section down to "Predictions" was written **before any
iteration 3 eval was run**. Questions in `questions.yaml` and `questions_hard.yaml` are unchanged.

## Baseline to beat (iteration 2, k=8)

| metric | core (20) | hard (18) |
|---|---|---|
| hit@1 / hit@5 (page) | 88% / 100% | 60% / 93% |
| chunk-level hit@1 / recall@5 | 82% / 94% | 47% / 73% |
| status / facts / judge correct | 95% / 94% / 95% | 94% / 93% / 94% |
| false-refusal rate | 6% | 7% |
| mean first-gold-chunk rank (retrieval only, 32 questions) | 1.91 (A+B), 1.72 (A only) | |
| corpus | 27 chunks | 27 chunks |

## Fixed in advance (not tuned on any eval)

- Dense model: `BAAI/bge-small-en-v1.5` via `fastembed`. Chunks are embedded as `header + text`; queries get the model's query prefix.
- Fusion: reciprocal rank fusion of the BM25 and dense rankings, constant 60, equal weights, over the full ranking.
- Default `k` stays 8.
- Stemmer rule: keep Snowball only if it does not lower the mean first-gold-chunk rank on **both** Kirana (core + hard) and holdout
  retrieval-only metrics; otherwise keep only the UK/US spelling pass.
- A holdout document (different fictional company) and about 12 questions are written in Step A, before retrieval changes. They are
  reported, never used to pick a setting. If a change helps Kirana and hurts the holdout it is overfit and is not kept.

## Predictions (to be marked right or wrong afterwards)

- Hybrid raises chunk recall@5 on hard from 73% toward 85% or more, and moves h04, h05, h12 up. h01 may be fixed (zero word overlap); if not, say so.
- Hit@8 stays 100%. Core judge-correct stays at 95% or above.
- Cost per question is unchanged or slightly lower; index build adds a one-time model download and a few seconds of embedding.
- Holdout: hybrid is not worse than BM25-only on holdout retrieval-only metrics. If it is, the iteration is reported as overfit.
- Risk: dense retrieval may promote vaguely related chunks over exact-number matches (e.g. "1.71x"). Watch number-heavy questions.

## Step B: normalisation ablation (retrieval only, no LLM, BM25)

Chunk-level, over the full ranking (so a gold chunk is always ranked), `scripts/retrieval_ablation.py`. `none` is iteration 2 change A
alone, `full` is A+B as shipped in iteration 2, `spelling` is the UK/US pass without Snowball. n = questions with gold chunks.

| normalise | set | n | mean first-gold rank | hit@1 | recall@5 |
|---|---|---|---|---|---|
| none | core | 17 | 1.47 | 71% | 96% |
| none | hard | 15 | 2.00 | 40% | 90% |
| none | holdout | 11 | 1.55 | 73% | 95% |
| spelling | core | 17 | 1.47 | 71% | 96% |
| spelling | hard | 15 | 2.20 | 40% | 83% |
| spelling | holdout | 11 | 1.55 | 73% | 95% |
| full | core | 17 | 1.41 | 82% | 94% |
| full | hard | 15 | 2.47 | 47% | 73% |
| full | holdout | 11 | 1.82 | 73% | 86% |

Kirana core+hard combined mean rank (32 questions): none 1.72, spelling 1.81, full 1.91 (the 1.72 and 1.91 match the iteration 2 analysis).

**Decision, by the pre-registered rule:** Snowball (`full`) worsens the mean first-gold rank on Kirana (1.81 to 1.91) and on the holdout
(1.55 to 1.82), so it is dropped; the default is `spelling`. Note that `none` is slightly better than `spelling` on Kirana hard (2.00 vs
2.20) and identical on the holdout; the rule says keep the spelling pass, so I kept it, but the UK/US pass has not earned itself on
these two documents (it matters only when the query and the text use different spellings, which no question here tests beyond h05).
Full Snowball does buy hit@1 on core (71% to 82%), which is the part of iteration 2 that looked like a gain. The switch
`KIRANA_NORMALISE` stays because it is one line and keeps the ablation reproducible.

## Step C and D: hybrid retrieval, measured

Runs on disk: `iter3`, `hard_iter3`, `holdout_iter3` (hybrid, k=8, `spelling` normalisation); `iter3_bm25`, `hard_iter3_bm25`,
`holdout_iter3_bm25` (BM25 only, same normalisation, the separation runs); `holdout_iter2` (holdout baseline, iteration 2 code).
Single runs, response cache on (`.cache/llm`, vision transcripts unchanged). Judge and generator are LLMs: a one-question swing is
noise (20, 18 and 13 questions).

### Retrieval only (no LLM), first-gold-chunk rank over the full ranking (`scripts/retrieval_ablation.py`)

| retriever / normalisation | core mean rank | hard mean rank | Kirana 32-question mean | holdout mean rank | hard recall@5 | holdout recall@5 |
|---|---|---|---|---|---|---|
| BM25, none (iteration 2, change A only) | 1.47 | 2.00 | 1.72 | 1.55 | 90% | 95% |
| BM25, full (iteration 2 as shipped) | 1.41 | 2.47 | 1.91 | 1.82 | 73% | 86% |
| BM25, spelling (Step B decision) | 1.47 | 2.20 | 1.81 | 1.55 | 83% | 95% |
| **hybrid, spelling (iteration 3)** | **1.47** | **1.33** | **1.41** | **1.45** | **93%** | **100%** |

### Answer metrics, three suites

| metric | core it2 | core it3 | core it3 bm25 | hard it2 | hard it3 | hard it3 bm25 | holdout it2 | holdout it3 | holdout it3 bm25 |
|---|---|---|---|---|---|---|---|---|---|
| hit@1 / hit@5 (page) | 88 / 100 | 82 / 100 | 76 / 100 | 60 / 93 | 87 / 100 | 53 / 100 | 82 / 91 | 82 / 100 | 82 / 100 |
| hit@8 (page) | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| chunk hit@1 / recall@5 | 82 / 94 | 71 / 98 | 71 / 96 | 47 / 73 | 73 / 93 | 40 / 83 | 73 / 86 | 73 / 100 | 73 / 95 |
| status / facts / judge correct | 95 / 94 / 95 | 95 / 94 / 95 | 95 / 94 / 95 | 94 / 93 / 94 | 100 / 100 / 94 | 94 / 93 / 89 | 92 / 91 / 92 | 92 / 91 / 92 | 92 / 100 / 100 |
| oracle judge correct | 89 | 89 | 89 | 100 | 100 | 100 | 100 | 100 | 100 |
| false-refusal / refusal recall | 6 / 100 | 6 / 100 | 6 / 100 | 7 / 100 | 0 / 100 | 7 / 100 | 9 / 100 | 9 / 100 | 9 / 100 |
| answer-call cost (list price, USD) | 0.0573 | 0.0594 | 0.0571 | 0.0515 | 0.0526 | 0.0512 | 0.0312 | 0.0304 | 0.0325 |
| corpus chunks | 27 | 27 | 27 | 27 | 27 | 27 | 10 | 10 | 10 |

All values are percentages except cost. Hit@1 and the chunk metrics count answerable questions only (17 core, 15 hard, 11 holdout).

### Predictions vs actual

| prediction | actual | verdict |
|---|---|---|
| Hybrid raises hard chunk recall@5 from 73% toward 85%+ | 73% to **93%** (mean first-gold rank 2.47 to 1.33) | **right** |
| h04, h05, h12 move up | h04 7 to 2, h05 6 to 3, h12 5 to 1 | **right** |
| h01 may be fixed | **fixed** (retrieval rank 1, answered correctly, no word overlap) | right |
| Hit@8 stays 100% | 100% on all three suites | **right** |
| Core judge-correct stays at or above 95% | 95% | **right** (but see below: page hit@1 fell) |
| Cost unchanged or slightly lower | core +3.7%, hard +2.1%, holdout -2.6% vs iteration 2 | **wrong on Kirana** (slightly higher, tokens in +1.6% / +1.1%); holdout lower |
| Index build adds a one-time download and a few seconds | model download about 25 s once; embedding the 27 Kirana chunks takes about 2.3 s (model load 0.4 s once cached) | right |
| Holdout: hybrid not worse than BM25-only on retrieval-only metrics | mean rank 1.45 vs 1.55, recall@5 100% vs 95%, hit@1 equal | **right** (not overfit by the plan's test) |
| Risk: dense promotes vague chunks over exact-number matches | core q07 (an exact-label table lookup) first-gold rank 3 (BM25) to 4 (hybrid), and q13 1 to 2; q01 improved 4 to 3 | **partly seen**, small, no answer failure |

### Questions whose outcome changed (iteration 2 to iteration 3 hybrid, answer level)

| question | it2 | it3 | cause |
|---|---|---|---|
| h01 | wrong (refused) | **correct** | hybrid (dense match, zero shared words); the BM25-only separation run still refuses |
| h09 | correct | partial | not retrieval: the gold chunk is rank 1 in all runs. The generator answered "Yes ... NOT above" after seeing the same figures in a different context order. Generator noise. |
| q14 | wrong | partial | transcript unchanged (cache); the judge rewarded a partly right answer. Still an image-transcription failure. |
| w07 (holdout) | partial (refused) | partial (refused) | unchanged; the BM25-only run was judged correct. Both runs contain the table and the rule in the context, so the difference is generator phrasing (hybrid's answer omitted one of the three sites). Noise. |
| everything else | same | same | |

### Which step caused what

- **Step B (drop Snowball, keep spelling)** made BM25-only retrieval worse on the sets where Snowball had helped: core hit@1 88% to 76% (page), chunk hit@1 82% to 71%
  (q07 table 1 to 3, q08 1 to 2), hard judge 94% to 89% (h09 is generator noise, see above). This is the cost of following the pre-registered rule; it was
  decided on first-gold rank, where Snowball lost on both documents, not on hit@1.
- **Step C (hybrid)** recovered and exceeded it: core page hit@1 76% to 82%, hard hit@1 53% to 87%, hard chunk recall@5 83% to 93%, holdout chunk recall@5 95% to 100%.
  Net against iteration 2: hard up a lot on retrieval, core page hit@1 down 6 points (one question, q07 and q13 sit one or two ranks lower), holdout neutral on answers.

### Honest reading

Retrieval clearly improved on the hard set (the set built to expose missing meaning matching) and did not get worse on the unseen holdout, so the
mechanism transfers at least in direction. Answer-level gains are small: hard judge-correct is 94% in both iteration 2 and 3, because a fixed h01 was offset by generator
noise on h09 and a partial q14. The holdout cannot show retrieval gains at the answer level: its corpus is 10 chunks, so k=8 returns most of the document
whatever the ranker does. The core set did not improve (its page hit@1 is lower than iteration 2's 88%, still within one or two questions).
No setting was tuned on any set: model, RRF constant, weights, k were fixed in advance; the only data-driven choice was the stemmer, by the stated rule.
The holdout is 13 questions and one fictional document written by the same author as the code, so it is a weak test of generality, not a proof.

## Follow-up (after the iteration 3 report): normalisation re-checked under hybrid retrieval

Retrieval only, no LLM, `scripts/retrieval_ablation.py --retriever hybrid`. This was run **after** seeing the iteration 3 results, at the author's
request, so it is post hoc: the default was **not** changed because of it.

| normalise (hybrid) | core mean rank | hard mean rank | Kirana 32 mean | holdout mean rank | holdout hit@1 |
|---|---|---|---|---|---|
| none | 1.47 | 1.27 | 1.37 | 1.45 | 73% |
| spelling (current default) | 1.47 | 1.33 | 1.41 | 1.45 | 73% |
| full (Snowball) | 1.29 | 1.53 | 1.40 | 1.36 | 82% |

- Spelling vs none: identical except one hard question (1.27 vs 1.33). Under hybrid the spelling pass earns nothing measurable; the dense model already absorbs UK/US variants. It is kept only as cheap, low-risk insurance.
- Snowball under hybrid is no longer clearly bad: it is best on core and holdout, worst on hard, and its Kirana mean (1.40) is level with spelling (1.41). The Step B rule was
  stated on BM25-only results, where Snowball lost on both documents; under hybrid, applying the same rule would keep it. Switching now would be re-deciding after seeing the
  results, so the default stays `spelling` and the difference is reported as an open question. A proper decision needs the larger holdout in `HOLDOUT_V2_PLAN.md`.

---

# Holdout v2: a larger, less Kirana-like document, and a decision rule for normalisation

Plan: `HOLDOUT_V2_PLAN.md`. Everything in this section down to "Predictions" is written and committed **before any eval is run on the new
document** (the document does not exist yet when this is committed; it is generated from `scripts/make_holdout2_pdf.py` afterwards). The
questions in `questions.yaml`, `questions_hard.yaml` and `questions_holdout.yaml` stay untouched. No setting is changed in this work.

## What is measured

- Document: a third fictional company (a regional hospital group), 25 to 40 pages, deliberately unlike Kirana and Northmere (see the plan, section 1).
- Questions (about 25) are written and frozen in a commit **before the current code is run on the document**. Gold chunk ids come from the
  ingest of the document, assigned mechanically by matching a verbatim snippet recorded in each question (`gold_text`) against the chunk text,
  never by looking at what retrieval returns. A snippet that no chunk contains is an ingestion loss: the question loses its chunk labels, is
  listed in the failure analysis, and still counts at the answer level.
- Retrieval-only ablation (no LLM, full ranking so a gold chunk is always ranked): normalisation `none|spelling|full` x retriever `bm25|hybrid`
  on four question sets: core (17 questions with chunk labels), hard (15), holdout v1 (11), holdout v2 (n, see results). "Kirana" is core
  and hard pooled (32), as in iteration 3. Metric: mean first-gold-chunk rank; hit@1 and recall@5 alongside.
- Answer level: the default code (hybrid, `spelling`, k=8) on holdout v2 (`holdout2_baseline`) and the BM25-only separation run (`holdout2_bm25`).
  No other answer runs: the normalisation ablation is retrieval only.

## Decision rule (fixed now, applied mechanically)

A candidate setting C replaces the reference R only if its mean first-gold-chunk rank, rounded to two decimals, is **less than or equal to**
R's on all three of: Kirana pooled (32), holdout v1, holdout v2. Equal counts as "not worsened". If C passes with no improvement anywhere, that
is reported as "passes, no gain". If it fails on any set it is rejected.

- Snowball: C = hybrid + `full`, R = hybrid + `spelling` (the current default). The same comparison under BM25 is reported as a secondary
  row, because the iteration 3 rule was stated on BM25 results.
- Spelling pass: C = `spelling`, R = `none`, under each retriever, to ask whether the pass earns its place.
- Retriever: hybrid is kept only if its mean rank is <= BM25's with the same normalisation on all three.
- The rule's verdict is reported, but **the default is not changed in this work**: the switch is left to the author. Nothing is tuned on any
  holdout; the settings compared are the three that already exist.

## Predictions (to be marked right or wrong afterwards)

1. Corpus: 55 to 90 chunks (target 60+ met).
2. Ingestion pitfalls, recorded and not fixed: (a) the three-page table is merged only across its first two pages (the merge loop folds a table
   into the next page once, so the third page stays a separate chunk); (b) two-column pages come out in the wrong reading order or interleaved,
   because blocks are sorted by y then x; (c) the table with merged header cells has a mangled or empty header row; (d) the table without
   ruling lines is not detected as a table and ends up as prose; (e) footnote text lands inside prose chunks. The chart and scan pages are
   transcribed by the vision model; at least one number from them is wrong or missing.
3. Retrieval, holdout v2: hybrid is not worse than BM25 on mean first-gold-chunk rank for the same normalisation, and is better by at
   least 0.3 rank in the default normalisation. Mean rank for hybrid + `spelling` is between 2 and 4 (a 60+ chunk corpus lifts ranks
   against holdout v1's 1.45).
4. Snowball verdict: hybrid + `full` **fails** the rule (worse than hybrid + `spelling` on at least one of the three sets). Confidence is low;
   under hybrid the differences on Kirana and holdout v1 were within 0.1 in the follow-up.
5. Spelling vs `none` under hybrid: within 0.1 rank on all three sets (no measurable gain).
6. Answer level, holdout v2: page hit@8 on answerable questions is below 100% for the first time (85 to 95%); overall judge-correct is between 60% and
   80%, well under Kirana's 95%, and most failures trace to ingestion (tables, reading order, scan/chart transcripts), not to retrieval.
7. Hybrid vs BM25 on answers: hybrid has at least as many judge-correct answers as BM25-only, by one to three questions. This is the first set where a
   retrieval difference should be visible in answers; a difference of one question is noise (single LLM runs).
8. Unanswerable and false premise: at least 3 of the 4 near-miss questions are refused; at least 1 of the 2 false-premise questions is answered correctly;
   the conflict question is the most likely of the three kinds to get the wrong status.

## Holdout v2: results

Document: Halbrook Regional Health Group report, 30 pages, **68 chunks** (holdout v1: 10, Kirana: 27). 28 questions, 23 with gold chunks (v22 to v26
unanswerable). Runs on disk: `holdout2_baseline` (hybrid, `spelling`, k=8, the default code), `holdout2_bm25` (same, `--retriever bm25`). Ablation output:
`eval/results/ablation_v2.md`. Failure analysis: `eval/failure_analysis_holdout2.md`. Single runs; one question is 3.6 points.

### Retrieval only (no LLM), full ranking, mean first-gold-chunk rank (hit@1 / recall@5 in brackets for holdout v2)

| retriever | normalise | core (17) | hard (15) | Kirana pooled (32) | holdout v1 (11) | holdout v2 (23) |
|---|---|---|---|---|---|---|
| bm25 | none | 1.47 | 2.00 | 1.72 | 1.55 | 3.57 (52% / 78%) |
| bm25 | spelling | 1.47 | 2.20 | 1.81 | 1.55 | 3.57 (52% / 78%) |
| bm25 | full | 1.41 | 2.47 | 1.91 | 1.82 | 2.61 (61% / 80%) |
| hybrid | none | 1.47 | 1.27 | 1.38 | 1.45 | 2.70 (57% / 85%) |
| **hybrid** | **spelling (default)** | 1.47 | 1.33 | **1.41** | **1.45** | **2.70 (57% / 85%)** |
| hybrid | full (Snowball) | 1.29 | 1.53 | 1.41 | 1.36 | 2.39 (57% / 89%) |

The first five columns for Kirana and holdout v1 reproduce iteration 3 and its follow-up exactly (no code under `src/` changed).

### Decision rule, applied as pre-registered (candidate <= reference at two decimals on Kirana pooled, holdout v1 and holdout v2)

| comparison (candidate vs reference) | Kirana | holdout v1 | holdout v2 | verdict |
|---|---|---|---|---|
| **Snowball: hybrid full vs hybrid spelling (primary)** | 1.41 vs 1.41 | 1.36 vs 1.45 | 2.39 vs 2.70 | **passes, gain somewhere** |
| Snowball: bm25 full vs bm25 spelling (secondary) | 1.91 vs 1.81 | 1.82 vs 1.55 | 2.61 vs 3.57 | FAILS (Kirana, holdout v1) |
| Spelling pass: hybrid spelling vs hybrid none | 1.41 vs 1.38 | 1.45 vs 1.45 | 2.70 vs 2.70 | FAILS (Kirana by 0.03) |
| Spelling pass: bm25 spelling vs bm25 none | 1.81 vs 1.72 | 1.55 vs 1.55 | 3.57 vs 3.57 | FAILS (Kirana) |
| Retriever: hybrid vs bm25, spelling | 1.41 vs 1.81 | 1.45 vs 1.55 | 2.70 vs 3.57 | passes, gain on all three |
| Retriever: hybrid vs bm25, none | 1.38 vs 1.72 | 1.45 vs 1.55 | 2.70 vs 3.57 | passes, gain on all three |
| Retriever: hybrid vs bm25, full | 1.41 vs 1.91 | 1.36 vs 1.82 | 2.39 vs 2.61 | passes, gain on all three |

**What the rule says about Snowball:** under the default retriever it passes. The Kirana comparison is an exact tie (rank sums 45 and 45 over 32
questions), holdout v1 improves by 0.09 and holdout v2 by 0.31. By the rule as written, Snowball would be kept. **The default is not changed**: that decision
is the author's, and the reading below says why the pass is thinner than the numbers look.

- **Each gain is one question.** The whole holdout v2 gain is v15, the footnote question (hybrid rank 13 to 3, BM25 34 to 9; "colleagues" stems to the same
  token as "colleague" in the neighbouring training paragraph). The other four changed questions net out at +3 (v06 3 to 2, v07 3 to 5, v08 2 to 3, v09 4 to 5), so without v15 Snowball
  is worse on holdout v2. Holdout v1's gain is w05 (2 to 1). Hit@1 on holdout v2 is the same (57%) with and without it.
- The rule is stated on mean rank and counts a tie as a pass, so it cannot distinguish "level" from "better"; it also does not weigh the BM25-only result, where Snowball loses on
  Kirana and holdout v1 and only wins on holdout v2 (again through v15).
- The rule also says the **spelling pass fails** (hybrid: 1.41 vs 1.38 on Kirana, one hard question one rank lower; identical on both holdouts, including this document that mixes UK and US
  spelling). It earns nothing measurable. `none` is the simplest setting that passes everywhere; I leave that to the author too.
- Hybrid passes against BM25 on all three, with a gain on every set, for all three normalisations. This is now the best-supported retrieval conclusion: three documents, same direction.

### Answer metrics, holdout v2 (answerable = 23)

| metric | hybrid (`holdout2_baseline`) | BM25 (`holdout2_bm25`) |
|---|---|---|
| hit@1 / hit@5 / hit@8 (page) | 83 / 96 / 100 | 74 / 96 / 100 |
| chunk hit@1 / hit@8 / recall@5 | 57 / 91 / 85 | 52 / 91 / 78 |
| status / facts / judge correct | 96 / 91 / 89 | 100 / 96 / 93 |
| judge partial | 7 | 7 |
| oracle judge correct | 100 | 100 |
| false-refusal / refusal recall | 4 / 100 | 0 / 100 |
| answer-call cost (list price, USD) | 0.0925 | 0.0908 |
| corpus chunks | 68 | 68 |

Per-question: the only differences are v12 (hybrid wrong, BM25 partial: gold chunk at rank 9 vs 6) and v14 (hybrid partial, BM25 correct: same context, generator
and judge strictness). v15 is partial in both (footnote glued to a training paragraph). Everything else is correct in both, including the conflict, five unanswerable questions and both false premises.

### Predictions vs actual

| # | prediction | actual | verdict |
|---|---|---|---|
| 1 | 55 to 90 chunks | 68 | right |
| 2a | three-page table merged only across two pages | `p13-t1` pages 13-14, `p15-t1` separate | right |
| 2b | two-column reading order wrong | paragraphs of the two columns interleaved (`p4-x1`, `p9-x1`, `p23-x1`, ...) | right |
| 2c | merged-header table has a mangled or empty header row | header has an empty cell and the second header row becomes a data row; values intact | partly right |
| 2d | unruled table not detected | detected and extracted cleanly (`p17-t1`) | **wrong** |
| 2e | footnote text lands in prose chunks | yes (`p8-x4`); it caused the one failure that is purely ingestion | right |
| 2f | at least one chart or scan number wrong or missing | all values right (`p10-f1`, `p11-f1`, `p25-s1`) | **wrong** |
| - | not predicted | the table of contents became a 212-word table chunk; section labels drift on column-interleaved pages | new |
| 3 | hybrid not worse than BM25, better by >= 0.3 at the default; mean rank 2 to 4 | 2.70 vs 3.57 (0.87 better); 2.70 | right |
| 4 | Snowball (hybrid) fails the rule | **passes** (tie on Kirana, better on both holdouts), but each gain is one question | **wrong** |
| 5 | spelling vs none within 0.1 under hybrid | 0.03, 0.00, 0.00 | right |
| 6 | page hit@8 below 100% (85 to 95%); judge-correct 60 to 80%; failures mostly ingestion | hit@8 100%; judge 89% (hybrid), 93% (BM25); oracle 100%; the failures are retrieval (v12, v15), one ingestion-caused | **wrong** (the document is easier for the pipeline than predicted) |
| 7 | hybrid has >= as many judge-correct answers as BM25, by 1 to 3 | 25 vs 26 | **wrong** |
| 8 | >= 3 of 4 near-miss refused; >= 1 of 2 false premises right; conflict most likely wrong | 4/4 (5/5 with the appendix question); 2/2; conflict right | right on the first two, **wrong** on the third |

### Honest reading

- The larger, structurally different document did not break the pipeline: answers are as good as on Kirana. Ingestion damage is real (interleaved columns, a footnote
  attached to the wrong paragraph, a table split over two chunks) but the answers survive it because chunks still contain the facts and k=8 over 68 chunks covers about 12% of the document.
  The plan's expectation that ingestion failures would dominate was too pessimistic for this generator: its tables are clean and its scan is perfectly legible.
- It did make a retrieval error reach an answer (v12), which holdout v1 could not. Hybrid ranks better on average but, for v12, the dense ranking put the gold chunk
  at 14 (BM25 had it at 6) and fusion moved it to 9; that chunk opens with a paragraph about board changes (column interleave), which probably dilutes its embedding.
- Three documents now agree that hybrid beats BM25 on mean rank under every normalisation. They disagree about Snowball (hybrid: level, better, better; BM25: worse, worse, better),
  and the evidence for each is a handful of questions; a fourth document would be a better use of effort than tuning the stemmer.
- Not tuned: no setting was changed or chosen on any set; the three normalisation modes already existed and the rule was written before the document did.
- Limits: all three documents are synthetic and by the same author as the code; 23 questions with chunk labels; single LLM runs; one question is 3.6 points; the gold-chunk labels were assigned by
  matching strings against the ingested chunks, so a gold chunk can only be one that ingestion produced.

---

# Iteration 4: general ingestion fixes, measured with repeated runs

Plan: `FOURTH_ITERATION_IMPLEMENTATION_PLAN.md`. Everything in this section down to "Predictions" is written and committed **before any document is
re-ingested and before any eval is run in this iteration**. All four question files are frozen (no question, `must_contain`, `gold_text` or `gold_*` label is edited).
Default normalisation (`spelling`), retriever (hybrid) and k (8) do not change.

## Baselines this iteration is measured against

Retrieval only, hybrid + `spelling`, mean first-gold-chunk rank (`eval/results/ablation_v2.md`):

| set | mean first-gold rank |
|---|---|
| Kirana pooled (core + hard) | 1.41 |
| holdout v1 (Northmere) | 1.45 |
| holdout v2 (Halbrook) | 2.70 |

Answers, k=8, single runs: core 95% judge-correct, hard 94%, holdout v1 92%, holdout v2 89% (BM25-only 93%).
Corpus: Kirana 27 chunks, Northmere 10, Halbrook 68. The "before" chunk files are saved in `eval/results/chunks_before/<doc_id>.jsonl`.

## Fixed in advance (not tuned)

- **Columns:** a page is multi-column when its text blocks (excluding blocks wider than 70% of the page width: full-width headings, captions, tables) fall into 2 to 3 groups whose
  x-ranges overlap by less than 5% of the page width and each group holds at least 3 blocks. Read order: full-width blocks and column groups in top-to-bottom bands; inside a band,
  column by column, each top to bottom. Otherwise: the current order.
- **Footnotes:** a block in the bottom 25% of the page, set at most 85% of the page's body size, beginning with a marker (digit, superscript digit or symbol), becomes its own `text` chunk,
  section unchanged, marker kept, not merged with other prose.
- **Tables over N pages:** merge any run of consecutive pages where each continuation table has the same header row and column count, the previous one ends in the lower 60% of its page
  and the next starts in the upper 40% (existing thresholds), with no limit on the number of pages.
- **Table of contents:** a block group whose lines mostly (>= 60%) end in a run of dots or spaces followed by a page number is navigation: one `text` chunk, not `table`.
- **Merged header cells:** when the first two rows of a table are a header band (second row's first cell empty, or first row with empty cells between non-empty ones), fold them into one header row
  (`Inpatient / Elective`, ...). Otherwise unchanged.
- **Repeated runs:** N = 3 per answer-level comparison, response cache bypassed (salted) for answer and judge calls; vision transcripts stay cached. Report mean and min-max per metric.
  A difference is real only if the ranges do not overlap; otherwise "within noise".
- Detection uses layout (geometry, font size, position, dotted leaders), never words. Nothing document-specific in `src/`; `tests/test_generality.py` stays green.
- Regression contract: a page that is not special must come out exactly as before (checked with `scripts/chunk_diff.py` against `eval/results/chunks_before/`).

## Predictions (to be marked right or wrong afterwards)

1. Regression: re-ingesting Kirana and Northmere gives chunk text identical to the saved files except where a fix applies; every difference is listed and explained (expected: none on Northmere, none or a footnote/ToC difference on Kirana). Any other difference means the fix is not general and is reverted or narrowed.
2. Halbrook re-ingest: column pages read in order (`p4-x1` no longer jumps columns; the glossary starts at its first term), the footnote is its own chunk (v15 gold moves to it), the ward table is one chunk over pages 13 to 15, the contents page is a text chunk, `p12-t1` has one header row. Chunk count 66 to 80.
3. Retrieval only: holdout v2 mean first-gold rank is below 2.70 (with the relabelled gold chunks); Kirana pooled <= 1.41 and holdout v1 <= 1.45.
4. Answers (3 runs each): holdout v2 judge-correct mean at least as high as before and v15 correct in at least 2 of 3 runs. Kirana core, hard and holdout v1 means stay within the baseline's noise range. The v12 failure may persist (ranking issue).
5. Noise: the run-to-run range on holdout v2 judge-correct is at least 2 questions (7 points) wide.
6. Risk: the column detector misclassifies at least one page of Kirana or Northmere (for example a KPI-card page with several narrow blocks). If so, the page is recorded and the detector tightened from typography, not from that page's content.
7. Hybrid vs BM25 on holdout v2 after the fixes: within noise at answer level.

## Step 3 and 4: ingestion fixes and re-ingest

Fixes (one commit each, with synthetic-PDF tests on layouts none of the documents contain: three columns, two columns with a full-width heading and table, a footnote on a page without a table, a four-page table, a contents list without a table, a header band with numbers below it): A multi-column reading order, B footnotes as their own chunks, C tables over any number of pages, D contents lists, E merged header cells. Mechanism refinements are in `docs/decisions.md`; the numbers of the plan are unchanged. The same PDFs were re-ingested with `--force`, so the doc ids did not change; vision transcripts came from the cache (no vision call was made). Chunk files after the fixes: `eval/results/chunks_after/`; comparison with `scripts/chunk_diff.py <before> <after>`.

| document | chunks before | chunks after | difference |
|---|---|---|---|
| Kirana | 27 | 27 | none: the file is byte-identical to `chunks_before` |
| Northmere | 10 | 10 | none: byte-identical |
| Halbrook | 68 | 74 | 23 chunks replaced by 29, listed below |

Halbrook, what changed (every difference):
- Column pages now read in order and the chunk boundaries move with it: `p3` (three paragraphs, the "Our values" and "Our hospitals" chunks swap places), `p4-x1/x2` (the Chair's review is one continuous text, the sentence about the largest projects is now in `p4-x1`), `p5-x3/x4` (a signature is no longer glued to a cut-off sentence), `p6-x3`, `p7-x1..x3` (one chunk more), `p9-x1`, `p19-x3`, `p23-x1` (the glossary starts at its first term), `p24-x1..x4`, `p26-x1`, `p27-x2/x4` (the travel paragraph no longer carries the "Water" label).
- Footnotes are their own chunks: `p8-x5` (the "Headcount excludes ... GmbH" note), `p9-x2`, `p19-x4`. Their source prose chunks lost the footnote text.
- `p2-x1`: the contents list is a text chunk (was the table `p2-t1`).
- `p12-t1`: one header row (`Inpatient / Elective`, `Inpatient / Day case`, `Outpatient / First`, `Outpatient / Follow-up`).
- Not changed: the ward table is still `p13-t1` (pages 13 and 14) plus `p15-t1`. The page-14 part ends at 45% of the page height, so it fails the pre-registered "previous part ends in the lower 60%" bar; the threshold was not loosened (see `docs/decisions.md`).

Relabelling: `eval/questions_holdout2_v2chunks.yaml` is a copy of the frozen holdout v2 file with `gold_chunks` re-resolved by `scripts/resolve_gold_chunks.py` from the unchanged `gold_text`. All 23 questions with evidence resolved; every other field is identical to the frozen file. Five labels changed: v05 `p3-x3` to `p3-x2`, v12 `p4-x2` to `p4-x1`, v13 `p3-x3` to `p3-x2`, v14 `p4-x1` to `p4-x2`, v15 `p8-x4` to `p8-x5`. All gold chunk ids of the Kirana core and hard sets and of holdout v1 still exist (the chunk files are identical), so no relabelled copy was needed for them.

## Iteration 4: results

Runs on disk: `before_<suite>_r1..r3` (old ingest, default code) and `after_<suite>_r1..r3` (new ingest), suites `core`, `hard`, `holdout`, `holdout2`; `after_holdout2_bm25x_r1..r3` (BM25 only, new ingest). All hybrid + `spelling`, k=8, answer and judge calls re-asked per repeat (cache salt), no oracle pass (it was not needed for the comparison and doubles the cost; the iteration 2 to 3 oracle results stay as they were). Holdout v2 "after" runs use `eval/questions_holdout2_v2chunks.yaml`, so their chunk-level hit is measured against the new gold labels. Retrieval only: `eval/results/ablation_v4.md`. Summarise any set with `uv run kirana eval --summarise --tag after_holdout2`.

### Retrieval only (no LLM), mean first-gold-chunk rank, hybrid + `spelling` (default)

| set | before (`ablation_v2.md`) | after (`ablation_v4.md`) |
|---|---|---|
| Kirana pooled (32) | 1.41 | 1.41 |
| holdout v1 (11) | 1.45 | 1.45 |
| holdout v2 (23) | 2.70 | **2.26** |
| holdout v2, BM25 + `spelling` | 3.57 | 3.74 |

Retrieval is deterministic, so there is no range. Holdout v2 per question, hybrid: v01 8 to 4, v12 9 to 4, v15 13 to 11, v13 1 to 2 (the chunk labels moved with the chunking); hit@8 on chunk labels 21/23 to 22/23 (v15 is the one miss). Under the iteration 3 decision rule the Snowball/spelling verdicts on holdout v2 shift (hybrid + `full` is now 2.52 vs 2.26 for `spelling`, so it would fail the rule that it passed before); the default stays `spelling` and the rule is not re-opened here, because the chunking changed, not the question set.

### Answers, mean (min-max) over 3 runs

| set (n) | metric | before | after | reading |
|---|---|---|---|---|
| core (20) | judge correct | 92% (90-95) | 95% (90-100) | within noise (identical chunks) |
| | facts correct | 90% (88-94) | 90% (82-94) | within noise |
| | false refusal | 4% (0-6) | 2% (0-6) | within noise |
| hard (18) | judge correct | 98% (94-100) | 98% (94-100) | same |
| | status correct | 98% (94-100) | 100% (100-100) | within noise |
| holdout v1 (13) | judge correct | 100% (100-100) | 100% (100-100) | same (status 92% both: one question the same way every run) |
| holdout v2 (28) | judge correct | 92% (89-93) | 93% (93-93) | within noise (ranges overlap) |
| | facts correct | 96% (96-96) | 96% (96-96) | same |
| | chunk hit@8 (answerable) | 91% (91-91) | 96% (96-96) | ranges do not overlap, but the label sets differ and retrieval is deterministic; this is the retrieval change above |
| holdout v2, BM25 only (28) | judge correct | n/a | 93% (93-93) | equal to hybrid |

Questions whose outcome changed in a majority of runs:
- holdout v2 **v12** (why capex rose): partial in 3/3 runs before, correct in 3/3 after. Its evidence (the sentence naming the projects and the reasons) is now in one chunk (`p4-x1`) that no longer opens with a paragraph from the other column; hybrid rank 9 to 4. The one clear answer-level gain, and it is the column fix.
- holdout v2 **v14** (never events): correct 2/3 before, 0/3 after (partial each time: "two" without "one fewer than 2024"). The sentence is in context in both ingests (`p6-x1` rank 1; `p4-x2` rank 7 after); this is generator/judge strictness, same as the single-run analysis said, and it moved the wrong way by chance or because the chunk it sits in changed. Not a retrieval effect. Counted as "anything worse" below.
- holdout v2 **v15** (footnote): partial in 3/3 both before and after. The footnote is now its own chunk, `p8-x5`, but at hybrid rank 11 (BM25 37), outside k=8, so the answer still lacks "612". The fix made the evidence retrievable as a chunk of its own, not retrieved by this query.
- Kirana (chunks byte-identical, so everything here is LLM noise): q06 partial to correct, h01 partial in one run to correct, q14 partial/wrong/partial to wrong/partial/correct, h09 correct to partial in one run. These show what a 3-run range on 20 questions looks like (core judge range 90-100%, up to 2 questions).

### Predictions vs actual

| # | prediction | actual | verdict |
|---|---|---|---|
| 1 | Kirana and Northmere unchanged except listed, explained differences | byte-identical chunk files for both; every Halbrook difference listed above | right |
| 2 | Halbrook: column pages in order, footnote own chunk, ward table one chunk over 13 to 15, contents a text chunk, `p12-t1` one header row, 66 to 80 chunks | all true except the ward table: `p13-t1` still covers pages 13-14 and `p15-t1` stays separate (the page-14 part ends at 45% of the page height, below the pre-registered "lower 60%" bar, which was not loosened); 74 chunks | right except the ward table (**wrong** on that item) |
| 3 | holdout v2 rank below 2.70; Kirana <= 1.41, holdout v1 <= 1.45 | 2.26; 1.41; 1.45 | right |
| 4 | holdout v2 mean at least as high, v15 correct in >= 2 of 3; Kirana sets inside baseline noise; v12 may persist | 93% vs 92%; v15 correct in 0 of 3; core 95% (baseline range 90-95), hard 98%, holdout v1 100% all inside; v12 did not persist (3/3 correct) | right on means and Kirana, **wrong** on v15 (footnote chunk at rank 11); v12 better than hedged |
| 5 | run-to-run range on holdout v2 judge-correct at least 2 questions (7 points) | 89-93% before (1 question), 93-93% after (0). On the Kirana core set the range was 2 questions | **wrong** for holdout v2 (the noise there is smaller than predicted), right for core |
| 6 | the column detector misclassifies at least one Kirana or Northmere page | none: both chunk files are byte-identical (the detector found no 2-3 column page on those, including the KPI-card page, which is a vision chunk) | **wrong** |
| 7 | hybrid vs BM25 on holdout v2 after the fixes within noise at answer level | 93% (93-93) vs 93% (93-93) | right |

### Honest reading

- The ingestion fixes did what they were for on the document that had the problems, and changed nothing where they should not: Kirana and Northmere chunk files are byte-identical, so no Kirana number can have moved because of them. All Kirana movement above is LLM noise and is the scale to read everything else against.
- Answer level on holdout v2: 93% vs 92% is within noise. The single real gain is v12 (3/3 runs, from the column fix) and one loss of the same size is v14 (judge strictness); the net is zero, which fits the earlier reading that the answer layer on this document is limited by retrieval and generator wording, not ingestion damage.
- Retrieval level is where the fixes show: mean first-gold rank 2.70 to 2.26 on holdout v2, hit@8 21/23 to 22/23, no change on the other two sets.
- Not fixed or not enough: v15 (footnote retrievable but ranked 11th, a ranking issue: the chunk is a short sentence about a different topic than the question's words), the ward table's third page (threshold, see the decisions file), and everything in Section 6 of the plan.
- Limits: still synthetic documents by the same author, 28 questions, 3 runs per set; "within noise" means the ranges overlap, not that the true difference is zero. The vision transcripts were held fixed by the cache, so these runs do not measure vision noise. Gold chunk labels of holdout v2 were re-resolved by script after the re-ingest from the frozen `gold_text`; nothing was tuned on any holdout.

---

# Iteration 4b: two follow-up ingestion changes (author decision after the iteration 4 report)

Written and committed **before** the code change, the re-ingest or any eval. Both changes were motivated by looking at holdout v2, so they are post-hoc with respect to that document; this is stated, not hidden.
The baseline is the iteration 4 result (`after_*` runs, `ablation_v4.md`, `chunks_after/`).

Changes (the author's answers to the open questions of the iteration 4 report):
1. **Footnote-shaped blocks are left out of the column grouping** (same footnote test as before: bottom 25%, at most 85% of body size, opens with a marker). They are placed after the columns of their band. Aim: a footnote wider than a column no longer merges the column groups (holdout v2 `p8`, `p9`).
2. **Table continuation no longer requires the previous part to end in the lower 60% of its page.** Kept: same header row, same column count, the next part starts in the upper 40% of the next page. Added as a fail-safe (generality rule 4, and the reason the bottom bar existed: two different tables that share a header): the previous part is only continued if no other text block sits below it on its page, i.e. the table is the last thing on the page.

Predictions (to be marked right or wrong afterwards):
1. Kirana and Northmere re-ingest byte-identical again (no 2 to 3 column page, no continued table on them that the old bottom bar excluded).
2. Halbrook: `p8` and `p9` read column by column ("Staff turnover fell ..." leaves the "Pay and reward" chunk and joins "Our people"); the ward table becomes one chunk over pages 13 to 15; chunk count 72 to 76.
3. Retrieval only, holdout v2 hybrid + `spelling`: mean first-gold rank within +-0.3 of 2.26 (no direction predicted; v09 and v07 to v09 gold chunks move with the merge); Kirana pooled 1.41 and holdout v1 1.45 unchanged.
4. Answers (3 runs, holdout v2 only, since the other chunk files stay identical): judge-correct within noise of 93%; v15 still partial in 3 of 3 runs; v12 stays correct.
5. On the author's question whether change 2 improves generalisation: it cannot be shown with three documents. The expected evidence is only "no regression elsewhere"; the false-merge risk it adds (two unrelated tables with the same header, one ending high on a page) is reduced, not removed, by the no-text-below guard. Reported as such.

## Iteration 4b: results

Code: footnote-shaped blocks are out of the column grouping; a table continues when its last part ends in the lower 60% **or** nothing else sits below it (the old path is kept, so nothing that merged before stops merging). Re-ingested with `--force`: Kirana and Northmere chunk files byte-identical to `chunks_before` again; Halbrook 74 to 73 chunks (`chunks_after_4b/`). Changed chunks: `p8` re-split (`p8-x1` "Our people" now holds the left column in order, `p8-x3` "Pay and reward" no longer contains "Staff turnover ..."), and `p13-t1` now covers pages 13 to 15 (`p15-t1` is gone). `p9` chunks are unchanged. New gold labels in `eval/questions_holdout2_v3chunks.yaml` (a copy of the frozen file; only v08 and v09 changed, `p15-t1` to `p13-t1`). Because every other chunk file is identical, only holdout v2 was re-run: 3 repeats `after4b_holdout2_r1..r3`; retrieval in `ablation_v4b.md`.

| holdout v2 | iteration 4 | iteration 4b |
|---|---|---|
| retrieval, mean first-gold rank, hybrid + `spelling` | 2.26 | 2.39 |
| judge correct, 3 runs | 93% (93-93) | 95% (93-100) |
| chunk hit@8 | 96% | 96% |

Retrieval moved the wrong way slightly: the merged ward table is one large chunk and ranks lower for the ward questions (v07 3 to 4, v08 2 to 4, v09 4 to 5; v13 2 to 1). Kirana pooled 1.41 and holdout v1 1.45 are unchanged. Answers: within noise (ranges overlap). v15 now varies by run (partial, correct, wrong) although its footnote chunk is still at rank 11, outside k=8; one run got it right, so this is generator variance, not a fix. v14 partial, correct, partial (strictness noise as before). v12 correct in 3 of 3 again.

| # | prediction | actual | verdict |
|---|---|---|---|
| 1 | Kirana and Northmere byte-identical | identical | right |
| 2 | `p8` in order, ward table one chunk over 13 to 15, 72 to 76 chunks | all three; `p9` unchanged | right |
| 3 | holdout v2 rank within +-0.3 of 2.26; Kirana and holdout v1 unchanged | 2.39; 1.41; 1.45 | right |
| 4 | judge-correct within noise of 93%; v15 partial in 3 of 3; v12 stays correct | 95% (93-100); v15 partial/correct/wrong; v12 correct 3 of 3 | right on two, **wrong** on v15 |
| 5 | generalisation cannot be shown with three documents; evidence is non-regression only | non-regression only (Kirana, Northmere identical; holdout v2 within noise); the merged table cost a little retrieval rank | right |
