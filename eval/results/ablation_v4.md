<!-- uv run python scripts/retrieval_ablation.py --retriever bm25,hybrid --normalise none,spelling,full --rule --detail --holdout2-questions questions_holdout2_v2chunks.yaml ; retrieval only, no LLM, after the iteration 4 ingest; holdout v2 labels from eval/questions_holdout2_v2chunks.yaml -->
| retriever | normalise | set | n | mean first-gold rank | hit@1 | recall@5 |
|---|---|---|---|---|---|---|
| bm25 | none | core | 17 | 1.47 | 71% | 96% |
| bm25 | none | hard | 15 | 2.00 | 40% | 90% |
| bm25 | none | holdout | 11 | 1.55 | 73% | 95% |
| bm25 | none | holdout2 | 23 | 3.74 | 65% | 74% |
| bm25 | none | Kirana (core+hard) | 32 | 1.72 | 56% | 93% |
| bm25 | spelling | core | 17 | 1.47 | 71% | 96% |
| bm25 | spelling | hard | 15 | 2.20 | 40% | 83% |
| bm25 | spelling | holdout | 11 | 1.55 | 73% | 95% |
| bm25 | spelling | holdout2 | 23 | 3.74 | 65% | 74% |
| bm25 | spelling | Kirana (core+hard) | 32 | 1.81 | 56% | 90% |
| bm25 | full | core | 17 | 1.41 | 82% | 94% |
| bm25 | full | hard | 15 | 2.47 | 47% | 73% |
| bm25 | full | holdout | 11 | 1.82 | 73% | 86% |
| bm25 | full | holdout2 | 23 | 4.04 | 65% | 76% |
| bm25 | full | Kirana (core+hard) | 32 | 1.91 | 66% | 84% |
| hybrid | none | core | 17 | 1.47 | 71% | 98% |
| hybrid | none | hard | 15 | 1.27 | 73% | 93% |
| hybrid | none | holdout | 11 | 1.45 | 73% | 100% |
| hybrid | none | holdout2 | 23 | 2.26 | 52% | 91% |
| hybrid | none | Kirana (core+hard) | 32 | 1.38 | 72% | 96% |
| hybrid | spelling | core | 17 | 1.47 | 71% | 98% |
| hybrid | spelling | hard | 15 | 1.33 | 73% | 93% |
| hybrid | spelling | holdout | 11 | 1.45 | 73% | 100% |
| hybrid | spelling | holdout2 | 23 | 2.26 | 52% | 91% |
| hybrid | spelling | Kirana (core+hard) | 32 | 1.41 | 72% | 96% |
| hybrid | full | core | 17 | 1.29 | 76% | 98% |
| hybrid | full | hard | 15 | 1.53 | 67% | 93% |
| hybrid | full | holdout | 11 | 1.36 | 82% | 100% |
| hybrid | full | holdout2 | 23 | 2.52 | 52% | 91% |
| hybrid | full | Kirana (core+hard) | 32 | 1.41 | 72% | 96% |

First-gold rank per question (holdout sets):

holdout: w01 w02 w03 w04 w05 w06 w07 w08 w09 w10 w13
bm25    none        1   1   2   5   1   1   1   1   2   1   1
bm25    spelling    1   1   2   5   1   1   1   1   2   1   1
bm25    full        1   1   2   8   1   1   1   1   2   1   1
hybrid  none        1   1   2   4   2   1   1   1   1   1   1
hybrid  spelling    1   1   2   4   2   1   1   1   1   1   1
hybrid  full        1   1   2   4   1   1   1   1   1   1   1

holdout2: v01 v02 v03 v04 v05 v06 v07 v08 v09 v10 v11 v12 v13 v14 v15 v16 v17 v18 v19 v20 v21 v27 v28
bm25    none        9   1   1   1   1   1   1   2   6   1   2   6   7   1  37   1   1   2   1   1   1   1   1
bm25    spelling    9   1   1   1   1   1   1   2   6   1   2   6   7   1  37   1   1   2   1   1   1   1   1
bm25    full        9   1   1   1   1   1   1   2   9   1   2   6   8   1  40   1   1   2   1   1   1   1   1
hybrid  none        4   1   1   1   1   3   3   2   4   2   2   4   2   1  11   1   1   3   1   1   1   1   1
hybrid  spelling    4   1   1   1   1   3   3   2   4   2   2   4   2   1  11   1   1   3   1   1   1   1   1
hybrid  full        4   1   1   1   1   3   4   3   5   2   2   4   4   1  12   1   1   3   1   1   1   1   1

| comparison (candidate vs reference) | Kirana | holdout | holdout2 | verdict |
|---|---|---|---|---|---|
| Snowball: hybrid full vs hybrid spelling (primary) | 1.41 vs 1.41 | 1.36 vs 1.45 | 2.52 vs 2.26 | FAILS |
| Snowball: bm25 full vs bm25 spelling (secondary) | 1.91 vs 1.81 | 1.82 vs 1.55 | 4.04 vs 3.74 | FAILS |
| Spelling pass: hybrid spelling vs hybrid none | 1.41 vs 1.38 | 1.45 vs 1.45 | 2.26 vs 2.26 | FAILS |
| Spelling pass: bm25 spelling vs bm25 none | 1.81 vs 1.72 | 1.55 vs 1.55 | 3.74 vs 3.74 | FAILS |
| Retriever: hybrid vs bm25, spelling | 1.41 vs 1.81 | 1.45 vs 1.55 | 2.26 vs 3.74 | passes, gain somewhere |
| Retriever: hybrid vs bm25, none | 1.38 vs 1.72 | 1.45 vs 1.55 | 2.26 vs 3.74 | passes, gain somewhere |
| Retriever: hybrid vs bm25, full | 1.41 vs 1.91 | 1.36 vs 1.82 | 2.52 vs 4.04 | passes, gain somewhere |
