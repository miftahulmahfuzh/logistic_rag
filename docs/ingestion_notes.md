# Ingestion notes (Kirana annual report, 13 pages)

Result of `uv run kirana ingest Kirana_Logistics_Annual_Report_2025.pdf`: 28 chunks. Page images sent to the VLM:
p1 (banner), p3 (KPI cards), p5 (two charts), p6, p7, p9, p13 (scan) = 8 images, about 17k VLM tokens in total.

## Checks against the page images (eyeballed by the implementer)

| Page | Chunk | Transcript vs image |
|---|---|---|
| 3 | p3-s1 | KPI cards: all six values correct (8,420 m, 41.6 million, 1,240, 37 / 566,000 sqm, NPS 52 with 2024: 47, 6,850). Typed `scan` (text layer is < 150 chars, so the page counts as text-less). |
| 4 | p4-t1 | Text-layer table, 6 data rows, numbers exact. |
| 5 | p5-f1, p5-f2 | Revenue by quarter 1,962 / 2,048 / 2,105 / 2,305 correct. Country shares 46 / 31 / 14 / 9 correct. First run omitted the title of Figure 2 (see decisions.md); fixed by one generic prompt sentence. |
| 6 | p6-f1 | All 12 months correct, Nov = 89.7. |
| 7 | p7-f1 | **VLM mistake.** The diagram has Hat Yai -- 18 trucks/day (cross-border) --> Shah Alam. The committed run attached that edge to Lat Krabang instead of Hat Yai ("Lat Krabang -- 18 trucks/day (cross-border) --> Shah Alam"). An earlier run of an older prompt got it right, so the VLM is non-deterministic on graph topology. I kept the transcript the pipeline produced and did not re-roll. The number 18 is right, the node is wrong. Expect this to bite eval question q14. |
| 7-8 | p7-t1 | Table 2 is ONE chunk, pages [7, 8], 23 data rows, repeated header dropped. |
| 9 | p9-t1, p9-t2, p9-f1 | Two text tables exact. Emissions intensity 3.05 / 2.88 / 2.71 / 2.58 / 2.40 correct, title kept. |
| 10 | p10-t1 | Text table exact. |
| 13 | p13-s1 | Tariff table: all 7 rates correct, "Rates exclude 7% VAT", Schedule C note, "Certified true copy". The stamp text "KIRANA" is captured as a stray word. |

## p1 banner

The cover banner (decorative image with the slogan baked into the pixels) passes the generic >= 3% area rule, so it
produced a chunk, `p1-f1`, containing only the slogan. It is flagged in the ingest summary ("short transcript with no
numbers: possibly decorative") rather than silently dropped. It is harmless for retrieval; a stricter filter (e.g.
dropping low-entropy images) is a possible improvement.

## Known weaknesses seen at ingest time

- Reading order is a plain top-to-bottom, left-to-right sort of text blocks; multi-column layouts would interleave.
- Section assignment is the nearest heading above on the same page, else the previous page's heading (tables only).
- A figure caption that sits inside the image pixels (Fig 1, 2, 4, 5) is only available through the VLM transcript, not
  as separate caption metadata.
