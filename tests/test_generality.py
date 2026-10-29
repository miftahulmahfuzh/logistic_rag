"""Guards the 'new PDF, no code changes' requirement: nothing document-specific in src/."""

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
# Case-sensitive literals that would mean the code was fitted to one report. The package and
# command name `kirana` (lower case) is the product name, not document content.
FORBIDDEN = ["Kirana", "Table 2", "THB", "Hat Yai", "Shah Alam", "Figure 3", "Schedule C"]
FORBIDDEN += [
    "Northmere",
    "Dunmere",
    "Brannock",
    "Fenwick",
    "Westerleigh",
    "Greyfell",
    "Appendix B",
    "GWh",
]
FORBIDDEN += [
    "Halbrook",
    "Alderbank",
    "Quillfield",
    "Marrowdene",
    "Brackenmoor",
    "Wystan",
    "Wexcombe",
    "Appendix D",
    "never event",
    "MWh",
    "GmbH",
    "Ward 6E",
]
FORBIDDEN += ["Tessellate", "Ombra", "Vellum", "Quorrin"]  # words of the synthetic layout tests


def test_src_has_no_document_specific_literals():
    offenders = []
    for path in SRC.rglob("*.py"):
        for n, line in enumerate(path.read_text().splitlines(), 1):
            for word in FORBIDDEN:
                if word in line:
                    offenders.append(f"{path.relative_to(SRC)}:{n}: {word}")
    assert not offenders, "document-specific literals in src/:\n" + "\n".join(offenders)
