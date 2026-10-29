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
