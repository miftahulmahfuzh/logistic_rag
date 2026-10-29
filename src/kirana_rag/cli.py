"""Command line interface: smoke, ingest, ask, eval."""

import typer

app = typer.Typer(add_completion=False, help="Document intelligence over annual-report PDFs.")


@app.callback()
def _main() -> None:
    """Kirana document intelligence."""


@app.command()
def smoke(pdf: str = "Kirana_Logistics_Annual_Report_2025.pdf", page: int = 6) -> None:
    """One text call and one vision call (crop of the largest image on a page)."""
    import pymupdf

    from . import llm

    t = llm.complete("Reply with exactly: pong", max_tokens=50)
    typer.echo(f"text  : {t.text.strip()!r} cached={t.cached} {t.tokens_in}/{t.tokens_out} tok")

    doc = pymupdf.open(pdf)
    pg = doc[page - 1]
    info = max(pg.get_image_info(), key=lambda i: (i["bbox"][2] - i["bbox"][0]) * (i["bbox"][3] - i["bbox"][1]))
    png = pg.get_pixmap(dpi=200, clip=pymupdf.Rect(info["bbox"])).tobytes("png")
    v = llm.describe_image(png, "Transcribe every data label of this chart as a markdown table.")
    typer.echo(f"vision: cached={v.cached} {v.tokens_in}/{v.tokens_out} tok\n{v.text}")


if __name__ == "__main__":
    app()
