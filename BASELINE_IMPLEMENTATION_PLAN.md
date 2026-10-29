# Baseline Implementation Plan: A1 Document Intelligence

Assignment: devx AI Labs take-home A1. Customer: Kirana Logistics Group (fictional), investor relations team.
Goal of THIS plan: a working, measured, end-to-end baseline (ingest -> ask -> eval) with honest numbers.
Improvements (hybrid search, reranking, etc.) are a separate step, done AFTER the baseline numbers are committed, so the
git history shows the loop: baseline -> measure -> fix the weakest part -> measure again.

Source documents (gitignored, in repo root): `Kirana_Logistics_Annual_Report_2025.pdf` (13 pages), `devx_FDE_A1_Brief.pdf`.

## 1. Hard requirements from the brief

1. Ingest the whole PDF; justify the method per content type; say so if a type is not handled.
2. A way to ask questions (CLI).
3. Every answer cites the page at minimum, ideally the table, figure or passage.
4. Honest refusals when the document does not support an answer.
5. 15-20 question eval set with expected answers and supporting pages, multiple content types, at least 3 unanswerable.
6. Retrieval quality measured SEPARATELY from answer quality. Show failures and likely causes.
7. **Works on a new PDF from the same company with no code changes** (demo round). Nothing may hard-code Kirana text, page numbers, table names or figure numbers.
8. Never commit API keys. README: run in 5 commands or fewer, architecture, decisions and trade-offs, limitations, "another week", one paragraph on AI tool use.

## 2. Environment facts (verified, do not re-litigate)

- Python 3.12, `uv` available. PyMuPDF imports fine. **No** poppler, **no** tesseract. 22 CPUs, 15 GB RAM.
- Credentials are in `.env.local` (gitignored). Keys: `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`. **Never print, log or commit the values.** `.env.example` documents all variables.
- **Text LLM**: `glm-5.3` at `LLM_BASE_URL` = `https://api.z.ai/api/anthropic` (Anthropic Messages API: `POST {base}/v1/messages`, headers `x-api-key`, `anthropic-version: 2023-06-01`).
  - It is a reasoning model. Send `"thinking": {"type": "disabled"}` for answering and judging (verified: cuts a 50-token reply from truncated to 10 tokens). Otherwise `max_tokens` must be large (>= 2000) or the reply is all thinking.
  - Responses contain `thinking` blocks and `text` blocks; read only `type == "text"`.
- **`glm-5.3` cannot see images.** The native endpoint rejects image content; the Anthropic-compatible route accepts an image but returns wrong, confident numbers (it said 96 for a chart whose true value is 89.7). Never use it for vision.
- **Vision LLM**: `glm-4.6v` at `https://api.z.ai/api/coding/paas/v4` (OpenAI-style `POST /chat/completions`, `Authorization: Bearer`, content part `{"type":"image_url","image_url":{"url":"data:image/png;base64,..."}}`). Verified: read the November OTD chart value correctly (89.7). Config: `VISION_BASE_URL`, `VISION_MODEL`, same `LLM_API_KEY`. The `https://api.z.ai/api/paas/v4` route has no balance, do not use it.
- **No embeddings endpoint** is available (`embedding-3` rejected on both routes). Therefore the baseline retriever is **BM25**. Dense embeddings (local, e.g. `fastembed` + `BAAI/bge-small-en-v1.5`) are the first improvement step, not part of the baseline.
- The API returns HTTP 429 under load. All calls go through one client with retry + exponential backoff, concurrency <= 2, and an on-disk response cache keyed by hash of (model, prompt, image bytes) so re-runs are free and deterministic.
- Do not use `OPENAI_API_KEY` from the shell environment. The user chose GLM.

## 3. What is in the Kirana report (drives design and eval)

| Page | Content | Facts live in |
|---|---|---|
| 1, 2, 4, 6, 10, 11, 12 | prose | text layer |
| 4, 7-8, 9, 10 | tables (Table 2 spans p7-p8, header repeated on p8) | text layer, parse as tables |
| 3 | KPI cards (NPS 52 vs 47, 566,000 sqm, 6,850 employees) | **image only** |
| 5 | Fig 1 revenue by quarter, Fig 2 revenue share by country | **image only** |
| 6 | Fig 5 on-time delivery by month | **image only** |
| 7 | Fig 3 line-haul network diagram | **image only** (caption is text) |
| 9 | Fig 4 emissions intensity per parcel | **image only** (caption is in the image) |
| 13 | scanned tariff, no text layer, slightly rotated | **scan** |

Known traps: CEO letter (p2) says 96 electric trucks added, errata (p12) and fleet section (p9) say 82: the conflict must be surfaced, errata is authoritative. Table 2 lists 23 of 37 warehouses. The tariff excludes 7% VAT. Schedule C (volume discounts) is explicitly not in the report.

## 4. Architecture

```
PDF --> ingest ---------------------------------------------> .cache/<doc_id>/
        per page:                                              pages.jsonl   (raw page records)
        1. text blocks (PyMuPDF)          -> prose chunks      chunks.jsonl  (all chunks + metadata)
        2. tables (page.find_tables)      -> table chunks      vision/*.png  (crops sent to the VLM)
        3. embedded images / scans        -> VLM transcript -> figure/scan chunks
        4. merge continued tables across pages

question --> retrieve (BM25, top-k) --> answer (glm-5.3, JSON) --> verify citations --> CLI output
                                          status: answered | refused | conflict
eval:  questions.yaml --> retrieval metrics (no LLM) + answer metrics (deterministic + LLM judge) --> RESULTS.md
```

### 4.1 Ingestion: method per content type (document this choice in the README)

| Content | Method | Why |
|---|---|---|
| Prose | PyMuPDF `get_text("blocks")`, reading order, drop repeated header/footer lines (a line repeating on >= 50% of pages) | Exact, free, fast. Headers/footers are noise that would pollute BM25. |
| Tables with text layer | PyMuPDF `page.find_tables()` -> markdown with caption | Keeps rows/columns aligned; numbers exact. A VLM would add risk of digit errors. |
| Charts, KPI cards, diagrams, scans | Crop the image region (`page.get_image_info` / `get_image_rects`, render at ~200 DPI) -> `glm-4.6v` transcription | These facts do not exist in the text layer. One mechanism covers charts AND the scanned page (no separate OCR engine; tesseract is not installed). |

Details:
- **Trigger for vision is generic**: an embedded image covering >= 3% of the page area (skip logos/icons), or a page with < 150 text chars and any image. A full-page scan is cropped to the full page. Never key off page numbers or figure names.
- **Vision prompt** (one prompt for all image types): transcribe every visible title, axis label, legend entry, data label, table cell and annotation, exactly as printed; for charts give a markdown table of series -> value; for diagrams list each node and each labelled edge as `A -- label --> B`; for scans transcribe the full text and table; do not estimate values that are not printed; if unreadable write `[unreadable]`. Output markdown only.
- **Figure caption linking**: find a caption in the page text matching `^(Figure|Fig\.|Chart|Table)\s*\d+` nearest to the image bbox (above or below) and add it to the figure chunk header. If the vision text starts with its own title, keep that too.
- **Table continuation**: if a table at the bottom of page N and a table at the top of page N+1 have the same column count and the same header row, merge into one table chunk with `pages=[N, N+1]`. Report-agnostic (no "Table 2" literal). If the header is identical, drop the duplicate header row.
- Pages with nothing extractable are recorded with a warning in the ingest summary, never silently dropped.
- Ingest prints a per-page summary table: page, #text chunks, #tables, #images sent to VLM, VLM tokens, warnings.
- Idempotent: `doc_id = <stem-slug>-<sha256[:8]>`; re-ingest hits the cache.

### 4.2 Chunking (justify in README, then check it against eval)

- Page-aware: a chunk never crosses a page boundary except merged tables.
- Prose: split on paragraph/heading boundaries, target ~250-350 tokens (approximate tokens as words * 1.3), hard max 450, overlap ~40 tokens ONLY when a single paragraph group had to be split. Reason: the report is short, most pages are < 400 tokens, so the natural unit is the page section; larger chunks dilute BM25 scores, smaller ones cut a fact from its subject.
- Tables: never split. Row count is small (<= 25). One chunk = caption + markdown table.
- Figure/scan: one chunk per image.
- Every chunk gets a context header baked into the indexed text: `[<doc title> | p<page> | <type>: <caption or section heading>]`, and a metadata dict:
  `chunk_id` (`p7-t1`, `p5-f2`, `p4-x1`), `doc_id`, `pages`, `type` in {text, table, figure, scan}, `section`, `caption`, `bbox`, `text`.
- Section heading detection: the last line with a font size >= 1.2x the median body size above the chunk (generic, from PyMuPDF spans).

### 4.3 Retrieval (baseline)

- BM25 (`rank_bm25`, BM25Okapi) over header+text. Tokenizer: lowercase, strip thousands separators in numbers (`8,420` -> `8420`), alnum tokens, a small English stopword list, no stemming (record "no stemming" as a hypothesis for failures, e.g. `utilisation` vs `utilization`).
- Top-k default **5**. `-k` flag for k sweeps. The whole report is ~30-40 chunks, so top-5 is ~15% of the corpus; eval reports hit@1/3/5/8 so the k choice is evidence-based.
- Index is in memory, rebuilt from `chunks.jsonl` on each run (milliseconds). No vector DB: unjustified for 40 chunks.
- Multi-document: `ask --doc <id>` searches one document, default searches every ingested document in `.cache/` (chunk ids carry `doc_id`). Nice-to-have, but keep the data model ready from day one.

### 4.4 Answering and grounding

- Model: `glm-5.3`, thinking disabled, temperature 0, `max_tokens` ~800.
- Context: the top-k chunks, each labelled `[chunk_id | doc | pages | type | caption]`.
- System prompt rules (write them out in `prompts.py`, they are part of the deliverable):
  1. Answer ONLY from the provided excerpts.
  2. If the excerpts do not contain the answer, return status `refused` and say what is missing. If a nearby fact exists but does not answer the question, say so (do not stretch it).
  3. If excerpts disagree, return status `conflict`, state each version with its page, and say which one the document itself marks as authoritative (e.g. an errata) if any.
  4. For arithmetic, show the inputs and the calculation. Numbers copied from a chart or scan come from the transcript; say the source is a figure/scan.
  5. Cite every claim: `{chunk_id, page, quote}` where `quote` is a verbatim span (<= 25 words) from that chunk.
  6. Reply with JSON only: `{"status": "answered|refused|conflict", "answer": "...", "citations": [...]}`.
- Parse JSON robustly (strip fences, one repair retry). A parse failure is reported as an error, not as an answer.
- **Citation verifier (code, not LLM)**: for each citation, check `chunk_id` is among the retrieved chunks, `page` is in that chunk's pages, and the normalised quote (lowercase, collapsed whitespace, commas/markdown pipes removed) is a substring of the normalised chunk text. Output `verified: true/false` per citation. Unverified citations are shown with a warning marker and counted in eval.
- CLI output: status, answer, citations with page + type + caption + quote, `verified` flags, retrieved chunk ids with scores, latency (retrieval / LLM ms), tokens in/out, and estimated cost line (price config in `config.py`, "unknown" if no price known). `--json` for machine output.
- No hard retrieval-score threshold in the baseline. Measure refusal behaviour first, add a threshold only if eval shows it helps.

### 4.5 Evaluation (the most graded part: build it carefully)

Test set: `eval/questions.yaml`, 20 questions (see Appendix A for the draft). Schema:

```yaml
- id: q03
  type: table            # prose | table | table_crossref | chart | kpi | diagram | scan | conflict | multihop | unanswerable | false_premise
  question: "..."
  expected_answer: "..."          # human-readable
  must_contain: ["2,310", "1.71"] # normalised strings that a correct answer includes (deterministic check). Any-of groups: [["82"], ["96"]]
  gold_pages: [4]                 # page(s) that support the answer; hit if ANY retrieved chunk covers one gold page
  expected_status: answered       # answered | refused | conflict
  notes: "why this question exists"
```

**Retrieval metrics (no LLM involved):** per question and per type: hit@1/3/5/8 on `gold_pages` (a hit is a retrieved chunk whose `pages` intersects gold_pages), MRR, and "gold chunk type retrieved" (did the figure chunk come back for a chart question?). Unanswerable questions are excluded from recall and reported separately (top score, what came back).

**Answer metrics (retrieval held at the baseline k):**
- `status_correct`: matches `expected_status`.
- `facts_correct`: deterministic `must_contain` check on the answer text.
- `judge_correct`: `glm-5.3` as judge (thinking off, temp 0) given question, expected answer, model answer; returns `correct | partial | wrong` plus one sentence. The judge never sees the retrieved context. Disagreements between `facts_correct` and `judge_correct` are listed for manual review. Do not hide them.
- `citation_page_ok`: at least one cited page is in `gold_pages`; `citations_verified`: share of citations that pass the verifier.
- Refusal precision/recall over the unanswerable set; false-refusal rate over the answerable set.
- Cost and latency: mean/p50/p95 per question, total tokens.

**Isolating retrieval from generation:** also run an "oracle" pass where the gold-page chunks are fed directly to the generator. Answer accuracy under oracle context vs retrieved context tells you whether a failure is a retrieval problem or a generation problem. This is the key evidence for the failure analysis.

**Outputs:** `eval/results/<tag>.json` (per-question raw records, committed) and `eval/RESULTS.md` (regenerated: summary table by metric and by type, per-question table, failure list). The failure analysis section is written by hand after reading the failures: for each failing question state the stage that failed (ingestion / chunking / retrieval / generation / judge), the evidence, and the proposed fix. No failure may be dropped or reworded to look better. If everything passes, say the test set is probably too easy and add harder questions.

Run tag: baseline = `--tag baseline`. Later runs use new tags, `RESULTS.md` shows baseline vs latest side by side.

### 4.6 Repository layout

```
pyproject.toml              # uv project, entry point `kirana`
.env.example  .gitignore
README.md                   # written at the end (see Phase 6)
BASELINE_IMPLEMENTATION_PLAN.md
src/kirana_rag/
  config.py                 # env loading (.env.local), paths, thresholds, price table
  llm.py                    # text client (Anthropic Messages) + vision client (OpenAI-style), retry, cache, usage accounting
  ingest/
    pdf.py                  # page records, header/footer stripping, headings
    tables.py               # find_tables -> markdown, cross-page merge
    images.py               # image regions, crops, VLM transcription, caption linking
    chunk.py                # prose chunking, chunk dataclass
    pipeline.py             # ingest(pdf_path) -> doc_id, writes .cache
  retrieve.py               # tokenizer, BM25 index, search
  answer.py                 # prompt build, call, JSON parse, citation verifier
  prompts.py
  cli.py                    # typer: ingest, ask, eval
  eval/
    metrics.py  runner.py  judge.py  report.py
eval/questions.yaml  eval/results/  eval/RESULTS.md
tests/                      # pytest, LLM mocked
```

Dependencies: `pymupdf`, `httpx`, `rank-bm25`, `typer`, `pyyaml`, `python-dotenv`, `rich`, `pytest`, `ruff`. Nothing heavy in the baseline.

## 5. Phases and acceptance criteria

Commit locally after each phase (conventional commits, e.g. `feat(ingest): ...`). **Do not push.** Never `git add` the PDFs or any `.env*` except `.env.example`.

**Phase 0: scaffold (15 min).** `uv init` style project, deps, `config.py`, `llm.py` with caching and retry, and a smoke command that makes one text call and one vision call on a crop of p6 and prints the answer. Accept: smoke prints `89.7` from the vision call (as a transcript value, not an assumption) and a text reply; second run is served from the cache.

**Phase 1: ingestion (90 min).** Implement 4.1 and 4.2. Accept: `uv run kirana ingest Kirana_Logistics_Annual_Report_2025.pdf` processes all 13 pages with a per-page summary; Table 2 is ONE chunk with 23 rows and pages [7, 8]; p3, p5 (x2), p6, p7, p9 and p13 each produce figure/scan chunks whose transcripts contain the key numbers (spot-check by eye and write what you saw into `docs/ingestion_notes.md`, including VLM mistakes); p1 logo/background image does not create a junk chunk or, if it does, it is flagged. Unit tests for table merge, header/footer stripping, caption linking, with synthetic PDFs built via PyMuPDF.

**Phase 2: retrieval (30 min).** Implement 4.3. Accept: `uv run python -m kirana_rag.retrieve "<q>"` debug path prints top-k with scores; tests on tokenizer (numbers, commas) and ranking on a toy corpus.

**Phase 3: answering and CLI (60 min).** Implement 4.4. Accept: `kirana ask "..."` works for an answerable, an unanswerable and the 96 vs 82 conflict question; citations print with `verified` flags; `--json` valid. Tests for JSON parsing/repair, the citation verifier (verbatim quote, altered quote, wrong page, unknown chunk id) with a mocked LLM.

**Phase 4: eval set and runner (75 min).** Review/finish Appendix A into `eval/questions.yaml` (`must_contain` per question). Implement 4.5, including the oracle pass. Accept: `kirana eval --tag baseline` runs all 20 questions end to end, writes `eval/results/baseline.json` and `eval/RESULTS.md`; metric functions unit-tested on hand-made inputs.

**Phase 5: baseline analysis (45 min).** Read every failure. Write the failure analysis into `eval/RESULTS.md` (by hand, with the stage that failed). Run k in {3, 5, 8} and record hit@k. End with a short "weakest part" paragraph and the ordered list of next improvements (expected: stemming/synonyms, dense hybrid, VLM verification, refusal threshold). Do NOT implement them in this session.

**Phase 6: generality and packaging (30 min).**
- Generality proof: add `scripts/make_subset_pdf.py` that builds a second PDF from pages 7-9 plus 13 of the report, ingest it and ask a question with no code changes. Add a test (or CI-style check) that greps `src/` for Kirana-specific literals (`Kirana`, `Table 2`, `THB`, `Hat Yai`) and fails if found.
- `README.md` with: run in <= 5 commands (`uv sync`, `cp .env.example .env.local`, `uv run kirana ingest <pdf>`, `uv run kirana ask "..."`, `uv run kirana eval`), architecture diagram, key decisions and trade-offs (include the glm-5.3 text-only finding and why BM25 first), ingestion table from 4.1, known limitations (honest), "what I would do with another week", and an "AI tools" paragraph (stub it factually: built with Claude Code; the author reviews and can explain all code; GLM-5.3 and GLM-4.6V used at runtime).
- `docs/customer_summary.md` is NOT written in this session (needs final numbers).
- Run `ruff check`, `pytest`; both clean.

## 6. Rules for the implementing session

- Follow this plan; if you must deviate, write the reason in `docs/decisions.md` (one line per decision, dated).
- Be honest in all numbers. Never tune the eval set to make the system pass; if a question is wrong, fix it and say so in the notes with the reason.
- Never print, log, commit or paste the API key. Do not read `.env.local` into any file that is tracked.
- Keep it simple and readable: small functions, type hints, short docstrings, no framework beyond what is listed. The author must be able to explain every line in an interview.
- LLM calls cost real quota: always use the response cache; do not loop over the full eval repeatedly while debugging (use `--only q03,q09`).
- When done, print a summary: phases completed, test status, baseline metrics table, top 3 failures, open questions for the author. Mark the eval set as `DRAFT: needs author review` in `eval/questions.yaml` header comment until they confirm.

## Appendix A: draft eval set (author reviews and edits; answers checked against the PDF)

| id | type | question | expected answer | gold pages | status |
|---|---|---|---|---|---|
| q01 | prose | What was Kirana's revenue in 2025 and by how much did it grow? | THB 8,420 million, up 10.0% | 2, 4 (3) | answered |
| q02 | table | What was net profit in 2024? | THB 468 million | 4 | answered |
| q03 | multihop | Is net debt at end of 2025 within the company's internal limit? | Net debt THB 2,310m vs EBITDA 1,347m = 1.71x, within the 2.0x limit | 4 | answered |
| q04 | table_crossref | What was the 2025 utilisation of the Cibitung cold store? | 96% (Table 2, on the continuation page) | 8 | answered |
| q05 | table_crossref | How many of the major facilities are cold-chain sites? | 6 (Bang Na, Rayong, Cibitung, Denpasar, Thu Duc, Johor Bahru) | 7, 8 | answered |
| q06 | table_crossref | Which major facilities are above 92% utilisation, the expansion-study trigger? | Laem Chabang 93%, Cikarang 94%, Cibitung 96% (Thu Duc is exactly 92%, not above) | 7, 8 | answered |
| q07 | table | How many electric light trucks does Indonesia have? | 44 | 9 | answered |
| q08 | conflict | How many electric trucks did Kirana add in 2025? | 82 per fleet section and errata; CEO letter says 96, the errata corrects it | 2, 9, 12 | conflict |
| q09 | chart | What was revenue in the third quarter of 2025? | THB 2,105 million | 5 | answered |
| q10 | chart | What share of 2025 revenue came from Indonesia? | 31% | 5 | answered |
| q11 | chart | In which month was on-time delivery lowest in 2025 and what was it? | November, 89.7% | 6 | answered |
| q12 | multihop | What was emissions intensity per parcel in 2025 and what level would the 30% reduction target from the 2023 baseline imply? | 2.40 g CO2e per parcel in 2025; 2023 was 2.71 so target is about 1.90 | 9 | answered |
| q13 | kpi | What was the customer NPS in 2025 and in 2024? | 52 in 2025, 47 in 2024 | 3 | answered |
| q14 | diagram | How many trucks per day run on the Hat Yai to Shah Alam cross-border lane? | 18 trucks/day | 7 | answered |
| q15 | scan | What is the 2026 tariff for cold-chain pallet storage? | THB 780.00 per pallet per month, excluding 7% VAT | 13 | answered |
| q16 | scan | What does last-mile delivery of a 2 kg parcel cost including VAT under the 2026 tariff? | THB 38.00 + 7% VAT = THB 40.66 | 13 | answered |
| q17 | unanswerable | What volume discount applies to a customer storing 500 pallets? | Not in the report; Schedule C is referenced but not included | (13 hint) | refused |
| q18 | unanswerable | What is the net profit forecast for 2026? | Not given; only revenue growth 11-13% and capex ~THB 1,050m | (11 hint) | refused |
| q19 | unanswerable | Who is the Chief Financial Officer? | Not in the report (only the CEO is named) | none | refused |
| q20 | false_premise | Which new country will Kirana enter in 2026? | None: the report says no new country is planned | 11 | answered |

Notes: q05 and q06 are answerable only by reading the whole merged table. q16 needs a scan transcription plus a calculation. q20 checks that the system answers "none" instead of refusing or inventing a country. Add 0-1 more questions only if the author wants them (cap is 20).

## Appendix B: baseline expected weak spots (hypotheses to test, not to pre-fix)

- BM25 without stemming/synonyms on conceptual questions (`flood`, `consolidation`, `utilisation`).
- Figure chunks have little prose vocabulary, so chart questions may rank low in BM25. Check chunk-type recall by question type.
- VLM transcription errors on small chart labels or the rotated scan; check figure transcripts against the images by eye.
- The generator stretching evidence on unanswerable questions (q17, q18).
- The conflict question: retrieval must return both p2 and p12 chunks at k=5.
