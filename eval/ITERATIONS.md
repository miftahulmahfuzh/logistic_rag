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
