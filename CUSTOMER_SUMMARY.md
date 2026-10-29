# Annual-report assistant for Kirana Logistics Investor Relations

*A one-page summary for the Head of Investor Relations.*

## What we built
A tool your team can ask questions about the annual report, in plain English. Each answer comes with the page it was taken from and the exact words that support it, and a check in code confirms those words really are on that page. If the report does not say, the tool says so instead of guessing. If two parts of the report disagree, it points out both. It reads text, tables, charts, the infographic, the diagram and the scanned tariff page. A new report can be loaded without any change to the software.

## How well it works
We tested it on 79 questions we wrote ourselves, across three reports (yours and two other fictional companies, to check it is not tuned to one document), and repeated each test three times because the language model does not give the identical answer every time.

- **Your report, the standard 20 questions: 95% of answers fully correct** (range 90 to 100% over three runs). A harder set of 18 questions (rephrased, near-duplicate figures, questions the report cannot answer): **98%**.
- **Every citation was checked and correct.** Every question the report cannot answer was declined, never invented.
- **Other companies' reports: 95 to 100%**, including a 30-page report with two-column pages, footnotes and a scanned page.
- **Speed and cost:** about 2.5 seconds per answer and roughly $0.002 per question at list prices.

## What it cannot do yet
- **Numbers that exist only in an image** (charts, the diagram, the scan) are read by a vision model that is occasionally wrong. In one test it attached "18 trucks a day" to the wrong hub in the network diagram, so a correct question was refused. These answers deserve a quick look at the cited page.
- **Small facts in footnotes** can be missed: one footnote answer was still incomplete.
- **Arithmetic** is done by the language model and can slip on rounding.
- **Occasionally too cautious:** on one fictional report it declined one answerable question every time.
- It has been tested on 13 to 30 page reports, not a 200-page filing, and on English only. Results move by up to about 10 points from run to run, so small differences are not meaningful.

## What we recommend next
1. **Pilot with your team for two weeks** on the questions analysts really ask, with the cited page shown next to every answer so a person can confirm it in seconds. Add the questions that fail to the test set.
2. **Add a second check on chart and diagram readings** (read each image twice and flag disagreements) before anyone quotes those numbers externally.
3. **Add a calculator step** for growth rates and totals, so arithmetic is exact.
4. **Test on two or three of your own past reports**, including a long one, before widening access.

Evidence and every failure are in the repository: `README.md`, `eval/ITERATIONS.md` and `eval/failure_analysis*.md`.
