"""Generate holdout v2: the annual report of a fictional regional hospital group (about 30 pages).

Deliberately unlike the Kirana and Northmere reports: two-column prose with sentences that run across the column
break, a table of contents, notes to the accounts with footnotes, a glossary, a table that spans three pages, a table
with merged header cells, a table without ruling lines, two charts, one scanned page, one landscape page, UK and US
spelling in different sections, and numbers in several formats (1,234.5 and 1.234,5 in one table).

The PDF is generated, not committed. The retrieval code is never tuned on it; see eval/questions_holdout2.yaml.
Usage: uv run python scripts/make_holdout2_pdf.py [out.pdf]
"""

import itertools
import random
import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
COMPANY = "Halbrook Regional Health Group"
HEADER = f"{COMPANY} | Annual Report 2025"
LEFT, RIGHT = 57.0, 538.0
BODY = 9.5
HEAD = 16
SUB = 12
COL_GAP = 20.0

# ---------------------------------------------------------------- data

HOSPITALS = [
    # name, kind, beds, bed occupancy 2025 (%), emergency admissions 2025 (thousands)
    ("Alderbank General Hospital", "an acute teaching hospital", 612, 91.3, 48.2),
    ("St Wystan's Hospital", "an acute district hospital", 430, 88.7, 31.7),
    ("Pennine Orthopaedic Centre", "an elective surgery centre", 148, 94.0, 0.9),
    ("Marrowdene Community Hospital", "a community hospital", 96, 82.5, 6.4),
    ("Quillfield Women's and Children's Hospital", "a specialist hospital", 210, 85.9, 19.8),
    ("Brackenmoor Mental Health Unit", "an inpatient mental health unit", 120, 89.2, 3.9),
]
ACTIVITY = [  # elective, day case, first outpatient, follow-up outpatient (thousands), 2025
    ("Alderbank General", 21.4, 33.8, 96.2, 181.7),
    ("St Wystan's", 15.9, 26.1, 71.5, 140.3),
    ("Pennine Orthopaedic", 11.2, 14.6, 22.9, 45.8),
    ("Marrowdene Community", 1.8, 5.2, 18.4, 29.6),
    ("Quillfield", 6.3, 9.7, 44.0, 83.1),
    ("Brackenmoor", 0.6, 1.1, 9.8, 38.7),
]
FINANCIALS = [
    ["Measure", "2024", "2025"],
    ["Income", "1,201.3", "1,284.6"],
    ["Operating surplus", "18.9", "23.4"],
    ["Net surplus", "9.7", "14.8"],
    ["Staff costs", "741.5", "782.1"],
    ["Agency spend", "78.9", "61.2"],
    ["Capital expenditure", "71.0", "96.4"],
    ["Cash and cash equivalents", "120.3", "142.7"],
]
WAITS_Q = [
    ("Q1", 14.8),
    ("Q2", 13.5),
    ("Q3", 12.4),
    ("Q4", 11.6),
]  # median elective wait, weeks, 2025
WARD_SPECIALTIES = [
    "Cardiology", "Respiratory", "General surgery", "Elderly care", "Stroke", "Oncology",
    "Orthopaedics", "Paediatrics", "Maternity", "Renal", "Gastroenterology", "Acute medicine",
]  # fmt: skip
OCCUPANCY_BY_TYPE = [  # near-identical rows across years: ward type, year, occupancy (%), length of stay (days)
    ("Medical", 2023, 87.4, 6.1), ("Medical", 2024, 87.9, 6.0), ("Medical", 2025, 88.3, 6.0),
    ("Surgical", 2023, 83.2, 3.4), ("Surgical", 2024, 83.6, 3.3), ("Surgical", 2025, 84.1, 3.3),
    ("Maternity", 2023, 79.8, 2.2), ("Maternity", 2024, 80.1, 2.2), ("Maternity", 2025, 80.4, 2.1),
    ("Paediatric", 2023, 72.5, 2.9), ("Paediatric", 2024, 73.0, 2.9), ("Paediatric", 2025, 73.2, 2.8),
]  # fmt: skip
WAITING_LIST = [  # specialty, patients waiting (thousands), median wait (weeks), waiting over 18 weeks (%)
    ("Cardiology", "6.8", "10.9", "42"),
    ("Orthopaedics", "11.3", "14.2", "58"),
    ("Ophthalmology", "7.5", "12.7", "51"),
    ("Gastroenterology", "5.2", "9.8", "37"),
    ("Urology", "4.1", "10.4", "40"),
    ("Dermatology", "3.9", "8.6", "29"),
    ("Ear, nose and throat", "2.7", "9.1", "33"),
    ("All specialties", "41.5", "11.6", "46"),
]
CAPITAL = [  # project, hospital, start, completion, budget, to 2024, 2025, remaining, status (GBP million)
    ("Theatre complex", "Pennine Orthopaedic", "2023", "2025", "62.0", "30.5", "31.5", "0.0", "Complete"),
    ("Emergency department", "St Wystan's", "2024", "2026", "58.4", "9.2", "24.7", "24.5", "On programme"),
    ("Neonatal unit", "Quillfield", "2024", "2026", "29.8", "6.4", "12.6", "10.8", "On programme"),
    ("MRI replacement", "Alderbank General", "2025", "2025", "9.8", "0.0", "9.8", "0.0", "Complete"),
    ("Diagnostic hub", "Marrowdene Community", "2025", "2027", "21.0", "0.0", "8.3", "12.7", "Delayed"),
    ("Electronic records", "Group wide", "2024", "2027", "34.6", "11.3", "9.5", "13.8", "On programme"),
]  # fmt: skip
CASHFLOW = [
    ["Cash flow item", "2025"],
    ["Net cash from operating activities", "118.6"],
    ["Capital expenditure", "(96.4)"],
    ["Interest received", "3.1"],
    ["Interest paid", "(2.9)"],
    ["Net increase in cash", "22.4"],
    ["Cash at start of year", "120.3"],
    ["Cash at end of year", "142.7"],
]
FIVE_YEAR = [
    ["Year", "Income", "Operating surplus", "Capital expenditure"],
    ["2021", "1,022.4", "9.1", "48.3"],
    ["2022", "1,078.9", "11.8", "55.7"],
    ["2023", "1,139.7", "14.2", "63.2"],
    ["2024", "1,201.3", "18.9", "71.0"],
    ["2025", "1,284.6", "23.4", "96.4"],
]
EURO = [  # continental number format on purpose: 1.234,5
    ["EUR thousand", "2024", "2025"],
    ["Revenue", "45.870,1", "48.213,5"],
    ["Operating costs", "39.402,8", "41.309,3"],
    ["EBITDA", "6.467,3", "6.904,2"],
    ["EBITDA margin (%)", "14,1", "14,3"],
    ["Net assets", "29.880,4", "31.557,0"],
]
ATTENDANCE = [
    ("Dr Imogen Falk", "Chair", 12),
    ("Ravi Thandani", "Chief executive", 12),
    ("Moira Gallacher", "Finance director", 11),
    ("Prof. Anselm Okoro", "Non-executive director", 9),
    ("Sunniva Berg", "Non-executive director", 10),
    ("Tomasz Lindqvist", "Medical director", 11),
]
RISKS = [
    ("Workforce availability", "high", "recruitment of nurses and the use of agency staff"),
    ("Cyber security", "high", "the electronic records programme and ageing medical devices"),
    ("Capital delivery", "medium", "the emergency department rebuild and the diagnostic hub"),
    ("Clinical safety", "medium", "never events and medication errors"),
    ("Regulatory compliance", "low", "inspection outcomes and registration conditions"),
    ("Financial resilience", "medium", "inflation in drug and energy costs"),
]


def ward_rows() -> list[list[str]]:
    """48 wards, deterministic; the occupancy of every ward is a number between 70 and 98."""
    rng = random.Random(2025)
    names = ["Alderbank", "St Wystan's", "Pennine", "Marrowdene", "Quillfield"]
    rows = []
    for i in range(48):
        hosp = names[i % 5]
        spec = WARD_SPECIALTIES[(i * 5 + i // 5) % len(WARD_SPECIALTIES)]
        rows.append([f"Ward {1 + i // 6}{'ABCDEF'[i % 6]}", hosp, spec, str(rng.randrange(12, 37)),
                     f"{rng.uniform(70, 98):.1f}"])  # fmt: skip
    return rows


# ---------------------------------------------------------------- drawing helpers


def text_width(text: str, size: float, font: str = "helv") -> float:
    return pymupdf.get_text_length(text, fontname=font, fontsize=size)


def wrap(text: str, width: float, size: float, font: str = "helv") -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if cur and text_width(trial, size, font) > width:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


FLOWS: list["Flow"] = []


class Flow:
    """Pour paragraphs into one or two columns; a sentence may run from the bottom of one column to the top of the next.

    Text is buffered and drawn by render(), so that two-column text can be balanced between the columns.
    """

    def __init__(self, page: pymupdf.Page, top: float, bottom: float, two_col: bool, size=BODY):
        width = RIGHT - LEFT
        if two_col:
            w = (width - COL_GAP) / 2
            self.cols = [(LEFT, w), (LEFT + w + COL_GAP, w)]
        else:
            self.cols = [(LEFT, width)]
        self.page_no, self.top, self.bottom, self.size = page.number, top, bottom, size
        self.lines: list[tuple[str, float, str, float]] = []  # text, size, font, gap before
        FLOWS.append(self)

    def para(self, text: str, size: float | None = None, font: str = "helv", gap: float = 5.0):
        size = size or self.size
        for i, line in enumerate(wrap(text, self.cols[0][1], size, font)):
            self.lines.append((line, size, font, gap if i == 0 else 0.0))
        return self

    def sub(self, text: str):
        return self.para(text, SUB, "hebo", gap=9.0)

    def render(self, doc: pymupdf.Document) -> None:
        page = doc[self.page_no]
        total = sum(g + s * 1.3 for _, s, _, g in self.lines)
        limit = self.top + total / 2 + 14 if len(self.cols) == 2 else self.bottom
        col, y = 0, self.top
        for text, size, font, gap in self.lines:
            lh = size * 1.3
            if y == self.top:
                gap = 0.0
            if y + gap + lh > min(limit, self.bottom):
                col += 1
                if col >= len(self.cols):
                    raise ValueError(f"text overflows the page: {text[:50]!r}")
                y, gap = self.top, 0.0
            y += gap + lh
            page.insert_text(
                (self.cols[col][0], y - size * 0.28), text, fontsize=size, fontname=font
            )


class Report:
    def __init__(self) -> None:
        self.doc = pymupdf.open()
        self.toc: list[tuple[str, int]] = []

    def page(
        self,
        title: str | None = None,
        landscape: bool = False,
        toc: bool = True,
        frame: bool = True,
    ):
        w, h = (842, 595) if landscape else (595, 842)
        page = self.doc.new_page(width=w, height=h)
        n = self.doc.page_count
        if frame:
            page.insert_text((LEFT, 35), HEADER, fontsize=8)
            page.insert_text((LEFT, h - 22), f"{COMPANY}  Annual Report 2025  Page {n}", fontsize=8)
        if title:
            page.insert_text((LEFT, 76), title, fontsize=HEAD, fontname="hebo")
            if toc:
                self.toc.append((title, n))
        return page


def ruled_table(page, x, y, rows, widths, h=18.0, size=9.0, spans=None) -> float:
    """Ruled table. `spans` maps (row, col) -> number of columns the cell covers (merged header cells)."""
    spans = spans or {}
    for r, row in enumerate(rows):
        c = 0
        while c < len(row):
            span = spans.get((r, c), 1)
            x0 = x + sum(widths[:c])
            rect = pymupdf.Rect(x0, y + r * h, x0 + sum(widths[c : c + span]), y + (r + 1) * h)
            page.draw_rect(rect, color=(0, 0, 0), width=0.8)
            page.insert_text((rect.x0 + 4, rect.y1 - 6), row[c], fontsize=size)
            c += span
    return y + len(rows) * h


def footnote(page, marker: str, text: str, y: float = 752) -> None:
    page.draw_line((LEFT, y - 8), (LEFT + 120, y - 8), width=0.5)
    page.insert_text((LEFT, y), f"{marker} {text}", fontsize=7.5)


def png_chart(draw) -> bytes:
    scratch = pymupdf.open()
    page = scratch.new_page(width=440, height=250)
    draw(page)
    return page.get_pixmap(dpi=200).tobytes("png")


def bar_chart(page) -> None:
    page.insert_text((14, 22), "Emergency admissions by hospital, 2025", fontsize=12)
    page.insert_text((14, 38), "Thousands of admissions", fontsize=9)
    base, top = 205, 60
    peak = max(h[4] for h in HOSPITALS)
    for i, (name, _, _, _, emerg) in enumerate(HOSPITALS):
        x0 = 28 + i * 67
        height = emerg / peak * (base - top)
        page.draw_rect(
            pymupdf.Rect(x0, base - height, x0 + 44, base), color=None, fill=(0.2, 0.4, 0.65)
        )
        page.insert_text((x0 + 8, base - height - 5), f"{emerg:.1f}", fontsize=9)
        page.insert_text((x0 - 2, base + 14), name.replace("St ", "").split()[0][:11], fontsize=7)
    page.draw_line((20, base), (430, base), width=0.8)


def line_chart(page) -> None:
    page.insert_text((14, 22), "Median wait for elective treatment, 2025", fontsize=12)
    page.insert_text((14, 38), "Weeks, by quarter", fontsize=9)
    base, top, lo, hi = 205, 60, 10.0, 16.0
    points = []
    for i, (q, value) in enumerate(WAITS_Q):
        x = 60 + i * 110
        y = base - (value - lo) / (hi - lo) * (base - top)
        points.append(pymupdf.Point(x, y))
        page.insert_text((x - 6, base + 14), q, fontsize=9)
    for a, b in itertools.pairwise(points):
        page.draw_line(a, b, color=(0.75, 0.25, 0.2), width=2)
    for p, (_, value) in zip(points, WAITS_Q):
        page.draw_circle(p, 3, color=(0.75, 0.25, 0.2), fill=(0.75, 0.25, 0.2))
        page.insert_text((p.x - 8, p.y - 8), f"{value:.1f}", fontsize=9)
    page.draw_line((30, base), (420, base), width=0.8)


def scanned_page() -> bytes:
    """A page of typed text and a table, drawn slightly tilted, rasterised to a grey JPEG: no text layer."""
    scratch = pymupdf.open()
    page = scratch.new_page(width=595, height=842)
    tilt = (pymupdf.Point(297, 421), pymupdf.Matrix(1, 1).prerotate(0.6))
    page.insert_text((LEFT, 90), "Statement of board attendance, 2025", fontsize=15, morph=tilt)
    intro = (
        "The board met twelve times during 2025. The table records the number of meetings each member "
        "attended. Members who joined or left part way through the year are not shown separately. "
        "The external audit fee for the year was 0.42 million pounds."
    )
    for i, line in enumerate(wrap(intro, 480, 10)):
        page.insert_text((LEFT, 125 + i * 14), line, fontsize=10, morph=tilt)
    y = 215
    for r, row in enumerate([("Member", "Role", "Meetings attended (of 12)"), *ATTENDANCE]):
        for c, (text, x, w) in enumerate(zip(row, (LEFT, 190, 360), (133, 170, 140))):
            rect = pymupdf.Rect(x, y + r * 22, x + w, y + (r + 1) * 22)
            page.draw_rect(rect, color=(0, 0, 0), width=0.8, morph=tilt)
            page.insert_text((x + 4, rect.y1 - 7), str(text), fontsize=9.5, morph=tilt)
    page.insert_text(
        (LEFT, 430), "Signed on behalf of the board, 24 March 2026.", fontsize=10, morph=tilt
    )
    pix = page.get_pixmap(dpi=110, colorspace=pymupdf.csGRAY)
    return pix.tobytes("jpeg", jpg_quality=55)


# ---------------------------------------------------------------- the report


def hospital_profile(name, kind, beds, occ, emerg) -> str:
    return (
        f"{name} is {kind} with {beds} beds. Bed occupancy at {name} averaged {occ:.1f}% in 2025."
    )


def build(path: Path) -> None:
    rep = Report()
    doc = rep.doc

    # 1. cover
    p = rep.page()
    p.insert_text((LEFT, 230), COMPANY, fontsize=26, fontname="hebo")
    p.insert_text((LEFT, 270), "Annual Report and Accounts 2025", fontsize=18)
    Flow(p, 320, 420, False).para(
        "This is a fictional organisation and document written for a software test. Any resemblance to a "
        "real hospital group is coincidental."
    )

    # 2. contents (filled at the end, when the page numbers are known)
    contents = rep.page("Contents", toc=False)

    # 3. about the group (UK spelling)
    p = rep.page("About the group")
    f = Flow(p, 96, 790, True)
    f.para(
        f"{COMPANY} provides hospital care to about 2.1 million people across the north of England. The group was "
        "founded in 1998 and its registered office is in Wexcombe. It runs six hospitals with a combined 1,616 beds "
        "and one rehabilitation clinic in Germany, Halbrook Rehabilitation GmbH. The group is a charitable organisation "
        "and any surplus is reinvested in patient services."
    )
    f.sub("Our hospitals")
    for h in HOSPITALS:
        f.para(hospital_profile(*h))
    f.sub("Our values")
    f.para(
        "Four values guide the organisation: respect for every patient, safety before speed, openness about mistakes "
        "and the wise use of public money. Each hospital reports against them every quarter, and the programme of "
        "colour-coded wristbands introduced in 2023 now covers all inpatient wards."
    )
    f.para(
        "The group employs 17,940 colleagues. Its largest single site is Alderbank General Hospital, which also "
        "hosts the medical school's clinical teaching programme. Pennine Orthopaedic Centre carries out most of "
        "the group's elective hip and knee replacements, while Quillfield Women's and Children's Hospital "
        "delivers about 9,800 babies a year."
    )
    f.para(
        "Marrowdene Community Hospital provides rehabilitation beds, a minor injuries unit and outpatient clinics "
        "for a rural population. Brackenmoor Mental Health Unit offers acute and rehabilitation care for adults "
        "and works closely with community teams in four local authority areas."
    )

    # 4. chair's review (UK)
    p = rep.page("Chair's review")
    f = Flow(p, 96, 790, True)
    f.para("Dear colleagues and partners,")
    f.para(
        "2025 was a year of recovery and delivery for the group. Income rose to 1,284.6 million pounds, an increase of "
        "6.9% on the 1,201.3 million recorded in 2024, and we achieved an operating surplus of 23.4 million pounds "
        "against 18.9 million pounds the year before. The net surplus was 14.8 million pounds."
    )
    f.para(
        "Our most important financial achievement was to bring down the cost of temporary staffing. Spending on "
        "agency staff fell by 22.4% to 61.2 million pounds, because more of our vacancies were filled by "
        "permanent colleagues and because the new staff bank offered flexible shifts at fair rates. The money saved "
        "was used to open additional beds and to extend evening clinics."
    )
    f.para(
        "Capital expenditure reached 96.4 million pounds, up from 71.0 million pounds in 2024. The largest projects "
        "were the new theatre complex at Pennine Orthopaedic Centre, which opened on schedule in the autumn, the "
        "rebuilding of the emergency department at St Wystan's Hospital and the replacement of the MRI scanners at "
        "Alderbank General Hospital. Each is described in the capital programme table later in this report."
    )
    f.para(
        "The board spent considerable time on safety. We recorded two never events in 2025, one fewer than in 2024, "
        "and we continue to treat every one of them as a failure of the system, not of an individual. I would like "
        "to thank every colleague for the care they gave, often under heavy pressure, during the winter months."
    )
    f.para(
        "There were changes in the boardroom. Prof. Anselm Okoro joined as a non-executive director and Sunniva Berg "
        "was reappointed for a second term. On behalf of the board I thank Ravi Thandani and his executive team "
        "for their leadership throughout the year."
    )
    f.para("Dr Imogen Falk, Chair", font="hebo")

    # 5. chief executive's report (UK); a sentence runs across the column break
    p = rep.page("Chief executive's report")
    f = Flow(p, 96, 790, True)
    f.para(
        "I am pleased to report that patients waited less time for planned treatment in 2025 than in any of the "
        "last five years. The median wait for elective treatment fell to 11.2 weeks at the end of December, "
        "compared with 18.1 weeks at the end of 2024."
    )
    f.sub("Urgent and emergency care")
    f.para(
        "Emergency departments across the group saw 110.9 thousand emergency admissions in 2025. The rebuilt "
        "emergency department at St Wystan's will open in 2026 and is expected to reduce the time ambulances "
        "spend waiting outside by about a third. In the meantime we opened a same-day emergency care unit at "
        "Alderbank General Hospital that treats patients who would otherwise be admitted overnight, and the "
        "average length of stay on its medical wards fell by a further two tenths of a day."
    )
    f.sub("Planned care")
    f.para(
        "Pennine Orthopaedic Centre completed 11.2 thousand elective procedures. The opening of its new theatre "
        "complex gave us four additional operating theatres. Because the complex is also used for day cases "
        "from St Wystan's, the number of patients waiting more than eighteen months for a joint replacement fell to "
        "zero before the end of the year, which is a first for the group since records began in 2009. The group also "
        "reduced the proportion of operations cancelled on the day for non-clinical reasons to 1.9%."
    )
    f.sub("Digital")
    f.para(
        "The electronic records programme moved from design to delivery. St Wystan's and Marrowdene went live "
        "in November and the programme is on budget. The remaining hospitals follow in 2026 and 2027. We "
        "have also invested in cyber security after the national alerts of the spring, and we passed an external "
        "penetration test in the autumn."
    )
    f.para("Ravi Thandani, Chief Executive", font="hebo")

    # 6. clinical quality (US spelling)
    p = rep.page("Clinical quality")
    f = Flow(p, 96, 790, True)
    f.para(
        "Patient safety is the first priority of our organization. In 2025 the group reported two never events, "
        "compared with three in 2024. A never event is a serious incident that is wholly preventable. Both "
        "events were investigated by an independent panel and the program of staff training that followed has been "
        "completed in all six hospitals."
    )
    f.sub("Mortality and harm")
    f.para(
        "The hospital standardized mortality ratio for the group was 0.97, which means that fewer patients died "
        "than would be expected given the severity of their conditions. The ratio was 1.02 in 2024. The rate of "
        "inpatient falls fell to 4.6 per 1,000 bed days from 5.1, and hospital-acquired pressure ulcers fell by "
        "14% to 212 cases."
    )
    f.sub("Infection prevention")
    f.para(
        "Hand hygiene audits showed compliance of 97% across all wards. The group recorded 38 cases of MRSA "
        "bloodstream infection or Clostridioides difficile attributed to its hospitals, against a ceiling of 46. "
        "Our Safer Wards program uses a color-coded checklist at the bedside so that a nurse can see within "
        "seconds which precautions apply to a patient."
    )
    f.sub("Medication safety")
    f.para(
        "Medication incidents that reached a patient fell to 3.2 per 1,000 bed days. The pharmacy teams at "
        "Alderbank General and St Wystan's introduced barcode scanning at the bedside and plan to extend it to "
        "the three smaller hospitals. A review of high-risk drugs found that insulin and anticoagulants account "
        "for almost half of all harm from medication."
    )
    f.sub("Clinical audit")
    f.para(
        "The group completed 214 clinical audits in 2025. Of these, 176 reported that practice met the standard "
        "set by the relevant professional body, 31 found that improvement was needed and 7 found serious "
        "shortcomings that were escalated to the board's quality committee."
    )

    # 7. patient experience (US spelling): near-identical paragraphs per hospital
    p = rep.page("Patient experience")
    f = Flow(p, 96, 790, True)
    f.para(
        "More patients told us what they thought of their care. The response rate to the annual patient survey "
        "rose from 31% to 38%, the highest since the survey began. Overall, 91% of respondents rated their care "
        "as good or very good, and 94% said they would recommend the hospital to family and friends."
    )
    ratings = [92, 90, 96, 93, 95, 84]
    for h, r in zip(HOSPITALS, ratings):
        f.para(
            f"At {h[0]}, {r}% of respondents rated their care as good or very good. Patients praised the "
            f"friendliness of staff and the cleanliness of the building. The most common complaint concerned "
            f"waiting times for the first appointment."
        )
    f.sub("Complaints")
    f.para(
        "The group received 1,142 formal complaints in 2025, down from 1,287 in 2024. The median time to "
        "resolve a complaint was 19 working days, within the target of 25. About one complaint in five was "
        "upheld in full. We now publish a short summary of lessons learned on every ward, and nurses read it at "
        "the start of each shift."
    )
    f.para(
        "A volunteer program of 1,350 people supports patients at all six hospitals. Volunteers help patients "
        "find their way around, read to older patients and run the hospital radio station at Marrowdene."
    )

    # 8. our people (UK) with a footnote
    p = rep.page("Our people")
    f = Flow(p, 96, 725, True)
    f.para(
        "At the end of 2025 the group employed 17,940 colleagues¹, an increase of 4.1% on the previous "
        "year. This is equal to 15,210 whole-time equivalent posts. Nursing and midwifery staff are the largest "
        "group, followed by support services and allied health professionals."
    )
    f.para(
        "Staff turnover fell from 13.4% to 11.8%, and sickness absence from 4.9% to 4.4%. The vacancy rate for "
        "registered nurses stood at 7.9% at the year end, down from 10.2%. Our international recruitment programme "
        "welcomed 212 nurses from overseas, most of whom joined Alderbank General Hospital and St Wystan's."
    )
    f.sub("Training and development")
    f.para(
        "Every new colleague completes a three-day induction. Mandatory training compliance averaged 93%, "
        "against a target of 90%. The group trained 148 apprentices, about twice as many as in 2022, and opened "
        "a clinical simulation centre at Alderbank General Hospital."
    )
    f.sub("Pay and reward")
    f.para(
        "Staff costs rose to 782.1 million pounds. A national pay award of 5.5% took effect in April. The group "
        "also introduced a cost of living support payment of 300 pounds for colleagues on the lowest pay bands. "
        "Gender pay data shows that women are paid on average 14.2% less than men per hour, mostly because "
        "they are under-represented in senior medical posts."
    )
    f.sub("Wellbeing")
    f.para(
        "More than 4,000 colleagues used the confidential counselling service. Each hospital now has a "
        "wellbeing champion on every ward, and the quiet rooms opened in 2024 are used, on average, by "
        "about 600 colleagues a month."
    )
    footnote(
        p,
        "¹",
        "Headcount excludes Halbrook Rehabilitation GmbH, which employs a further 612 people in Germany.",
    )

    # 9. financial review (UK) with a ruled table and a footnote
    p = rep.page("Financial review")
    f = Flow(p, 96, 140, False)
    f.para("Table 1: Financial summary (GBP million unless stated)")
    y = ruled_table(p, LEFT, 118, FINANCIALS, [180, 90, 90])
    f = Flow(p, y + 14, 725, True)
    f.para(
        "Income grew by 6.9%, driven by higher volumes of planned care and a 4.2% uplift in the national tariff. "
        "Operating expenses rose by 5.8%. The operating surplus is stated before the one-off gain from the "
        "sale of the former Marrowdene site¹."
    )
    f.para(
        "Agency spend fell to 61.2 million pounds from 78.9 million pounds. Staff costs, which include agency "
        "spend, were 782.1 million pounds and represent 60.9% of income. The group's lenders set a gearing "
        "ceiling of 45% and gearing at the year end was 31%."
    )
    f.para(
        "Cash at the year end stood at 142.7 million pounds, an increase of 22.4 million pounds. The "
        "group has agreed a revolving credit facility of 75 million pounds, which was undrawn at the year end."
    )
    f.para(
        "Drug and energy costs were the main sources of pressure. Spending on drugs rose by 8.3% and the energy "
        "bill by 11.0%, although the group has fixed 70% of its gas and electricity requirement for 2026 at "
        "lower prices than those paid in 2025."
    )
    footnote(
        p,
        "¹",
        "The one-off gain from the site sale was 4.6 million pounds and is excluded from the operating surplus.",
    )

    # 10. operations: chart 1
    p = rep.page("Hospital activity")
    f = Flow(p, 96, 140, False)
    f.para(
        "Emergency admissions are concentrated at the two acute hospitals. The chart shows admissions in each "
        "hospital in 2025; the group total was 110.9 thousand."
    )
    rect = pymupdf.Rect(LEFT, 150, LEFT + 440, 150 + 250)
    p.insert_image(rect, stream=png_chart(bar_chart))
    Flow(p, 410, 440, False).para("Figure 1: Emergency admissions by hospital, 2025 (thousands)")
    Flow(p, 450, 790, True).para(
        "Admissions at Quillfield are almost entirely children and expectant mothers. Pennine Orthopaedic Centre "
        "admits few emergencies because it treats patients who have been referred for planned surgery, and "
        "most of its emergency admissions are people who become unwell after an operation."
    )

    # 11. chart 2
    p = rep.page("Waiting times")
    f = Flow(p, 96, 140, False)
    f.para(
        "The median wait for elective treatment fell in every quarter of 2025. The chart shows the median "
        "number of weeks patients had waited at the end of each quarter."
    )
    rect = pymupdf.Rect(LEFT, 150, LEFT + 440, 150 + 250)
    p.insert_image(rect, stream=png_chart(line_chart))
    Flow(p, 410, 440, False).para(
        "Figure 2: Median wait for elective treatment by quarter, 2025 (weeks)"
    )
    Flow(p, 450, 790, True).para(
        "Waiting lists are not spread evenly. Orthopaedics and ophthalmology have the longest queues and are the "
        "focus of extra evening and weekend sessions in 2026. A detailed breakdown by specialty is given in the "
        "table that follows the ward register."
    )

    # 12. merged-header table
    p = rep.page("Activity by hospital")
    f = Flow(p, 96, 140, False)
    f.para("Table 2: Inpatient and outpatient activity by hospital, 2025 (thousands)")
    rows = [
        ["Hospital", "Inpatient", "", "Outpatient", ""],
        ["", "Elective", "Day case", "First", "Follow-up"],
        *[[n, *[f"{v:.1f}" for v in vals]] for n, *vals in ACTIVITY],
    ]
    spans = {(0, 1): 2, (0, 3): 2}
    y = ruled_table(p, LEFT, 118, rows, [140, 80, 80, 80, 80], spans=spans)
    f = Flow(p, y + 16, 790, True)
    f.para(
        "Outpatient follow-up attendances outnumber first attendances at every hospital, by almost two to one "
        "at Alderbank General and by almost four to one at Brackenmoor, where patients return regularly for "
        "review. Day cases exceed elective inpatient admissions everywhere except Brackenmoor, which does not "
        "run day surgery."
    )
    for h in HOSPITALS:
        f.para(
            f"Bed occupancy at {h[0]} averaged {h[3]:.1f}% in 2025. The hospital has {h[2]} beds, "
            f"and a typical patient stays for {2 + h[2] % 7} nights."
        )

    # 13-15. a table that spans three pages (header repeated on each page)
    wards = ward_rows()
    header = ["Ward", "Hospital", "Specialty", "Beds", "Occupancy 2025 (%)"]
    widths = [60, 120, 110, 50, 110]
    p = rep.page("Ward register")
    f = Flow(p, 96, 420, False)
    f.para(
        "The ward register lists every general ward in the five largest hospitals with its number of beds and its "
        "average occupancy during 2025. Brackenmoor is excluded because its wards are managed under a separate "
        "mental health contract. The register runs across three pages."
    )
    f.para("Table 3: Ward register, beds and average occupancy, 2025", gap=10.0)
    ruled_table(p, LEFT, 480, [header, *wards[:16]], widths, h=17.0)
    p = rep.page()
    ruled_table(p, LEFT, 70, [header, *wards[16:33]], widths, h=17.0)
    p = rep.page()
    y = ruled_table(p, LEFT, 70, [header, *wards[33:]], widths, h=17.0)
    f = Flow(p, y + 20, 790, False)
    f.para(
        "Occupancy above 90% is regarded as a risk to patient flow, because there is no space for a patient who "
        "needs to move between wards. Wards above that level are reviewed weekly by the site operations team."
    )

    # 16. near-identical rows across years
    p = rep.page("Occupancy and length of stay")
    f = Flow(p, 96, 140, False)
    f.para("Table 4: Average bed occupancy and length of stay by type of ward")
    rows = [["Ward type", "Year", "Occupancy (%)", "Length of stay (days)"]]
    rows += [[t, str(y_), f"{o:.1f}", f"{ls:.1f}"] for t, y_, o, ls in OCCUPANCY_BY_TYPE]
    y = ruled_table(p, LEFT, 118, rows, [110, 80, 110, 130])
    Flow(p, y + 16, 790, True).para(
        "Occupancy has risen slowly on every type of ward for three years while the average length of stay has "
        "barely moved. Paediatric wards run with the most spare capacity because demand for them is seasonal."
    ).para(
        "Length of stay is the average number of nights between admission and discharge. The group aims to "
        "reduce it where this is safe, because each night saved frees a bed for the next patient."
    )

    # 17. unruled table + the conflicting median wait
    p = rep.page("Waiting list by specialty")
    f = Flow(p, 96, 140, False)
    f.para("Table 5: Referral-to-treatment waiting list at 31 December 2025")
    cols = [LEFT, 230, 350, 450]
    head = ["Specialty", "Patients waiting (000s)", "Median wait (weeks)", "Over 18 weeks (%)"]
    y = 130
    for x, text in zip(cols, head):
        p.insert_text((x, y), text, fontsize=9, fontname="hebo")
    for row in WAITING_LIST:
        y += 17
        for x, text in zip(cols, row):
            p.insert_text((x, y), text, fontsize=9)
    Flow(p, y + 24, 790, True).para(
        "The waiting list contained 41.5 thousand patients at the end of December. The median wait across all "
        "specialties was 11.6 weeks, and 46% of patients had waited more than eighteen weeks. Orthopaedics has "
        "both the largest list and the highest share of long waiters."
    ).para(
        "The numbers in this table come from the patient administration system on 31 December and have not been "
        "adjusted for patients who were removed from the list in January."
    )

    # 18. landscape capital programme
    p = rep.page("Capital programme", landscape=True)
    Flow(p, 90, 120, False).para("Table 6: Capital programme by project (GBP million)")
    head = [
        "Project",
        "Hospital",
        "Start",
        "Complete",
        "Budget",
        "Spend to 2024",
        "Spend 2025",
        "Remaining",
        "Status",
    ]
    y = ruled_table(
        p,
        LEFT,
        105,
        [head, *[list(r) for r in CAPITAL]],
        [112, 130, 50, 62, 62, 90, 80, 74, 90],
        h=22,
    )
    Flow(p, y + 24, 520, False).para(
        "Spending on the programme in 2025 totalled 96.4 million pounds. The diagnostic hub at Marrowdene is "
        "running six months late because of a delay in the supply of imaging equipment. Options for the "
        "redevelopment of Brackenmoor Mental Health Unit are under review and no budget has been approved."
    )

    # 19-22. notes to the accounts (UK), single column, footnotes
    p = rep.page("Notes to the accounts (1): basis of preparation")
    f = Flow(p, 96, 725, False)
    f.sub("Note 1: Accounting policies")
    f.para(
        "The accounts have been prepared in accordance with the accounting manual issued for the sector and on the "
        "going concern basis. Amounts are stated in pounds sterling, rounded to the nearest hundred thousand "
        "pounds, unless otherwise indicated."
    )
    f.para(
        "Property, plant and equipment is stated at cost less depreciation. Buildings are depreciated over 40 "
        "years. Medical and other equipment is depreciated over 5 to 10 years according to its expected "
        "useful life. Assets under construction are not depreciated until they are brought into use. Leased "
        "assets are depreciated over the shorter of the lease term and their useful life, which is normally 3 to 5 "
        "years."
    )
    f.sub("Note 2: Income")
    f.para(
        "Income from patient care activities was 1,168.9 million pounds, or 91.0% of the total. The remainder "
        "was education and training (58.3 million pounds), research (21.7 million pounds), and other "
        "operating income (35.7 million pounds). Income from the commissioner for the Alderbank "
        "region was 612.4 million pounds, which is the largest single source of funds."
    )
    f.para(
        "Income is recognised when the service is provided. Payments received in advance for training "
        "contracts are held as deferred income and released as the training is delivered. At the year end "
        "deferred income amounted to 12.6 million pounds²."
    )
    f.sub("Note 3: Staff numbers")
    f.para(
        "The average number of staff during the year was 17,640 on a headcount basis. At the year end the "
        "group employed 6,420 nursing and midwifery staff, 2,310 medical and dental staff, 2,980 allied health "
        "professionals, 4,100 support staff and 2,130 administrative and management staff, a total of 17,940."
    )
    f.para(
        "Staff costs of 782.1 million pounds include agency spend of 61.2 million pounds. Employer pension "
        "contributions were 112.9 million pounds. The highest paid director received total remuneration "
        "of 0.31 million pounds, which was 9.6 times the median pay of the group's staff."
    )
    footnote(
        p,
        "²",
        "Deferred income is shown within other liabilities in the statement of financial position.",
    )

    p = rep.page("Notes to the accounts (2): assets and liabilities")
    f = Flow(p, 96, 140, False)
    f.sub("Note 4: Property, plant and equipment")
    rows = [
        ["GBP million", "Cost 1 Jan", "Additions", "Disposals", "Cost 31 Dec"],
        ["Land and buildings", "1,482.7", "52.3", "(9.4)", "1,525.6"],
        ["Equipment", "466.1", "31.8", "(14.2)", "483.7"],
        ["Assets under construction", "47.5", "12.3", "0.0", "59.8"],
    ]
    y = ruled_table(p, LEFT, 125, rows, [150, 80, 80, 80, 90])
    f = Flow(p, y + 16, 790, False)
    f.para(
        "Additions during the year totalled 96.4 million pounds, which agrees with the capital expenditure "
        "in the cash flow statement. The sale of the former Marrowdene site accounts for most of the "
        "disposals of land and buildings."
    )
    f.sub("Note 5: Provisions")
    f.para(
        "The group holds provisions of 71.6 million pounds. Of this, 38.2 million pounds relates to clinical "
        "negligence claims that the group expects to settle within five years, 21.0 million pounds to "
        "early retirement costs and 12.4 million pounds to legal and other claims. Provisions for clinical "
        "negligence are estimated by the group's legal advisers for each claim above 50 thousand pounds and by "
        "statistical modelling for smaller ones."
    )
    f.sub("Note 6: Borrowings")
    f.para(
        "Net borrowings are measured after deducting cash and cash equivalents. The group borrowed 8.0 million "
        "pounds during 2025 and repaid 11.5 million pounds. The weighted average interest rate on "
        "borrowings was 4.3% and loans mature between 2027 and 2041."
    )

    p = rep.page("Notes to the accounts (3): other disclosures")
    f = Flow(p, 96, 790, False)
    f.sub("Note 7: Pensions")
    f.para(
        "Most colleagues are members of the national health service pension scheme, which is an unfunded "
        "defined benefit scheme. The group accounts for it as if it were a defined contribution scheme, "
        "because the group cannot identify its share of the underlying assets and liabilities. The actuarial "
        "valuation of the scheme, including the funding position, is reported in Appendix D."
    )
    f.sub("Note 8: Related party transactions")
    f.para(
        "During the year the group purchased services of 2.4 million pounds from the university that "
        "operates the medical school at Alderbank General Hospital. Prof. Anselm Okoro is a professor at "
        "the university. He took no part in any decision about the contract. The group made no loans to "
        "directors."
    )
    f.sub("Note 9: Events after the reporting period")
    f.para(
        "No adjusting events have occurred since the year end. On 12 February 2026 the board approved a "
        "business case for the replacement of the pharmacy robots at Alderbank General Hospital at a cost "
        "of 6.2 million pounds. The expenditure will be incurred in 2026 and does not affect the 2025 accounts."
    )
    f.sub("Note 10: Contingent liabilities")
    f.para(
        "The group is defending two claims for which the likelihood of loss is considered possible but not "
        "probable. The combined amount claimed is 14.5 million pounds. No provision has been made. The "
        "group's insurers have been informed of both claims and have confirmed cover for the first."
    )
    f.sub("Note 11: Leases")
    f.para(
        "The group leases buildings, vehicles and medical equipment. The total charge for leases in the year "
        "was 17.9 million pounds. Future minimum lease payments are 15.3 million pounds within one year, "
        "40.2 million pounds between two and five years and 22.8 million pounds after more than five years."
    )

    # 23. euro-denominated subsidiary, continental number format
    p = rep.page("Overseas subsidiary")
    f = Flow(p, 96, 160, False)
    f.para(
        "Halbrook Rehabilitation GmbH is based in Germany and reports in euro using continental number "
        "formatting, in which a full stop separates thousands and a comma marks the decimal. Table 7 is "
        "reproduced in the format of the subsidiary's own accounts."
    )
    Flow(p, 168, 190, False).para(
        "Table 7: Halbrook Rehabilitation GmbH, summary results (EUR thousand)"
    )
    y = ruled_table(p, LEFT, 195, EURO, [160, 100, 100])
    Flow(p, y + 18, 790, True).para(
        "The clinic provides neurological rehabilitation to patients referred from Germany and Austria. It has "
        "88 beds. Revenue grew by 5.1% in 2025 and the operating margin improved slightly. The group has no "
        "plans to open a second clinic in Germany or elsewhere outside the United Kingdom."
    ).para(
        "Results are translated into sterling at the average exchange rate for the year, 1.17 euro to the pound. "
        "The subsidiary is included in the group's income, but its headcount is shown separately."
    )

    # 24. glossary
    p = rep.page("Glossary")
    f = Flow(p, 96, 790, True)
    terms = [
        ("Agency staff", "Temporary workers supplied by an external employer, used to fill gaps in rotas."),
        ("Bed occupancy", "The share of available beds that are filled by patients, averaged over the year."),
        ("Case mix", "The mixture of patients treated by a hospital, grouped by the complexity of their conditions."),
        ("Day case", "A patient who is admitted for treatment and goes home on the same day without staying overnight."),
        ("EBITDA", "Earnings before interest, tax, depreciation and amortisation, used here for the German subsidiary."),
        ("Length of stay", "The average number of nights a patient spends in hospital between admission and discharge."),
        ("Never event", "A serious patient-safety incident that is wholly preventable because national guidance exists to stop it."),
        ("Referral to treatment", "The time between a patient's referral by their doctor and the start of treatment."),
        ("Standardized mortality ratio", "Actual deaths divided by the number expected given the patients' conditions; below 1.00 is better than expected."),
        ("Whole-time equivalent", "A measure of staffing in which one full-time post counts as 1.0, and a half-time post as 0.5."),
    ]  # fmt: skip
    for term, definition in terms:
        f.para(term, font="hebo", gap=7.0)
        f.para(definition, gap=1.0)

    # 25. governance and risk (US spelling)
    p = rep.page("Governance and risk")
    f = Flow(p, 96, 790, True)
    f.para(
        "The board is responsible for the group's system of internal control and for reviewing its effectiveness. "
        "The audit committee met five times in 2025 and reviewed the principal risks at each meeting. The "
        "committee is chaired by Sunniva Berg, a non-executive director, and none of its members is an "
        "employee of the organization."
    )
    f.sub("Principal risks")
    for name, rating, driver in RISKS:
        f.para(
            f"{name}. The residual rating of this risk at the year end was {rating}. The risk is "
            f"driven mainly by {driver}. The executive owner reports on mitigation to the audit committee every "
            f"quarter, and the board reviews it twice a year."
        )
    f.sub("Whistleblowing and speaking up")
    f.para(
        "Staff raised 96 concerns through the speaking up service in 2025, compared with 71 the year before. "
        "About a third related to staffing levels. The freedom to speak up guardian reports directly to the "
        "chair and no case was closed without a response to the person who raised it."
    )

    # 26. scanned page
    p = rep.page(toc=False, frame=False)
    p.insert_image(p.rect, stream=scanned_page())
    rep.toc.append(("Board attendance (scanned page)", doc.page_count))

    # 27. outlook (US spelling)
    p = rep.page("Outlook for 2026")
    f = Flow(p, 96, 790, True)
    f.para(
        "For 2026 we expect income growth of 5% to 6% and capital expenditure of about 110 million pounds, "
        "most of it on the emergency department at St Wystan's, the neonatal unit at Quillfield and the "
        "electronic records programme. The emergency department will open in the second half of the year."
    )
    f.para(
        "Quillfield Women's and Children's Hospital will add six neonatal cots when the new unit opens, "
        "bringing the total to 24. The maternity unit at Quillfield remained open throughout 2025 and there "
        "are no plans to close it."
    )
    f.para(
        "We do not plan to open a second clinic in Germany. Our focus abroad is on raising the occupancy "
        "of the existing one. At home, options for Brackenmoor Mental Health Unit are under review; we will "
        "consult staff and patients before any decision is taken."
    )
    f.para(
        "The principal uncertainties are the pay award for 2026, the price of energy and the speed at which "
        "the delayed diagnostic hub at Marrowdene can be recovered. The group will publish its operating plan "
        "once the national funding settlement is confirmed."
    )
    f.para(
        "Our priorities are to cut the median elective wait below ten weeks, to reduce agency spend again "
        "and to complete the roll-out of the electronic records programme to the remaining hospitals. The "
        "pension scheme valuation is explained in Appendix D."
    )

    # 28. sustainability (US spelling)
    p = rep.page("Sustainability")
    f = Flow(p, 96, 790, True)
    f.para(
        "The group used 241,300 MWh of energy in 2025, 3.6% less than in 2024. Carbon emissions from energy "
        "use fell to 58.4 thousand tonnes of carbon dioxide equivalent, from 63.1 thousand tonnes. About 41% "
        "of our electricity now comes from renewable sources, and the group has signed a ten-year supply "
        "contract with a wind farm in the north of England."
    )
    f.sub("Travel and transport")
    f.para(
        "The group runs a fleet of 212 vehicles, of which 38 are electric. A cycle-to-work scheme was used by "
        "1,720 colleagues. The shuttle bus between Alderbank General Hospital and the railway station carried "
        "310 thousand passengers."
    )
    f.sub("Waste")
    f.para(
        "The group generated 11,800 tonnes of waste, of which 46% was recycled. Single-use plastic in "
        "catering was reduced by a third. Clinical waste, which must be incinerated, rose by 2% in line with "
        "activity. We plan to replace single-use surgical gowns with reusable ones at Pennine Orthopaedic Centre in 2026."
    )
    f.sub("Water")
    f.para(
        "Water consumption was 1.9 million cubic meters, a fall of 2.3%. Leaks were found and fixed in "
        "the Alderbank heating system, which saved enough water to fill 40 swimming pools."
    )

    # 29. cash flow
    p = rep.page("Statement of cash flows")
    f = Flow(p, 96, 140, False)
    f.para("Table 8: Summary statement of cash flows, 2025 (GBP million)")
    y = ruled_table(p, LEFT, 118, CASHFLOW, [230, 100])
    Flow(p, y + 18, 790, True).para(
        "Cash generated by operations covered the capital programme in full, with 22.2 million pounds to spare "
        "before net interest. The group did not draw on its revolving credit facility."
    ).para(
        "Working capital improved because of faster payment by commissioners, which reduced the number of "
        "days of income held in receivables from 38 to 33."
    )

    # 30. five-year summary
    p = rep.page("Five-year summary")
    f = Flow(p, 96, 140, False)
    f.para("Table 9: Five-year summary (GBP million)")
    y = ruled_table(p, LEFT, 118, FIVE_YEAR, [80, 100, 130, 140])
    Flow(p, y + 18, 790, True).para(
        "Income has grown every year since 2021 and the operating surplus has risen in each of the last four "
        "years. Capital expenditure was held back during the pandemic and has been increasing since 2022."
    ).para(
        "The five-year summary is unaudited. Figures for 2021 to 2023 have not been restated for the "
        "change in accounting policy for leases."
    )

    # 31. registered details
    p = rep.page("Company information")
    f = Flow(p, 96, 790, False)
    f.para(
        f"{COMPANY}. Registered charity. Registered office: 1 Hospital Road, Wexcombe, England. Auditors: "
        "Penhallow Maddox LLP. Bankers: the northern regional bank. Legal advisers: Strand and Moor. The "
        "annual general meeting will be held on 30 June 2026."
    )
    f.para(
        "Appendices A to C are available on request. Appendix D is published separately with the group's pension disclosures."
    )

    # contents page
    for flow in FLOWS:
        flow.render(doc)
    contents = doc[1]  # re-fetch: the page object created at the start is stale by now
    y = 100
    for title, n in rep.toc:
        contents.insert_text((LEFT, y), title, fontsize=10)
        dots = "." * int((380 - text_width(title, 10)) / text_width(".", 10))
        contents.insert_text((LEFT + text_width(title, 10) + 4, y), dots, fontsize=10)
        contents.insert_text((500, y), str(n), fontsize=10)
        y += 19

    print(f"{doc.page_count} pages")
    doc.set_metadata({"title": "Halbrook Regional Health Group Annual Report 2025"})
    doc.save(path)


if __name__ == "__main__":
    out = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else ROOT / "Halbrook_Health_Group_Annual_Report_2025.pdf"
    )
    build(out)
    print(out)
