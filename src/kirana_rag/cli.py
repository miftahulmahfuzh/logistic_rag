"""Command line interface: smoke, ingest, ask, eval."""

from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

console = Console()

app = typer.Typer(add_completion=False, help="Document intelligence over annual-report PDFs.")


def _pages(pages: list[int]) -> str:
    return f"p{pages[0]}" if len(pages) == 1 else f"p{pages[0]}-{pages[-1]}"


@app.callback()
def _main() -> None:
    """Kirana document intelligence."""


@app.command()
def smoke(pdf: str, page: int = 6) -> None:
    """One text call and one vision call (crop of the largest image on a page)."""
    import pymupdf

    from . import llm

    t = llm.complete("Reply with exactly: pong", max_tokens=50)
    typer.echo(f"text  : {t.text.strip()!r} cached={t.cached} {t.tokens_in}/{t.tokens_out} tok")

    doc = pymupdf.open(pdf)
    pg = doc[page - 1]
    info = max(
        pg.get_image_info(),
        key=lambda i: (i["bbox"][2] - i["bbox"][0]) * (i["bbox"][3] - i["bbox"][1]),
    )
    png = pg.get_pixmap(dpi=200, clip=pymupdf.Rect(info["bbox"])).tobytes("png")
    v = llm.describe_image(png, "Transcribe every data label of this chart as a markdown table.")
    typer.echo(f"vision: cached={v.cached} {v.tokens_in}/{v.tokens_out} tok\n{v.text}")


@app.command()
def ingest(
    pdf: Path = typer.Argument(..., exists=True, dir_okay=False),
    force: bool = typer.Option(False, help="Ignore the cache and re-ingest."),
) -> None:
    """Ingest a PDF into .cache/<doc_id>/ and print a per-page summary."""
    from .ingest.pipeline import ingest as run_ingest

    res = run_ingest(pdf, force=force)
    t = Table(title=f"{res.title}  [{res.doc_id}]" + ("  (cached)" if res.cached else ""))
    for col in ("page", "text", "tables", "images->VLM", "VLM tokens", "warnings"):
        t.add_column(col, justify="left" if col == "warnings" else "right")
    for s in res.summary:
        t.add_row(
            str(s.page),
            str(s.text_chunks),
            str(s.tables),
            str(s.images),
            str(s.vlm_tokens),
            "; ".join(s.warnings),
        )
    console.print(t)
    console.print(f"{len(res.chunks)} chunks written to .cache/{res.doc_id}/chunks.jsonl")


@app.command()
def ask(
    question: str = typer.Argument(..., help="Question about the ingested document(s)."),
    doc: str = typer.Option(None, "--doc", help="Search one doc_id only (default: all ingested)."),
    k: int = typer.Option(5, "-k", help="Number of chunks to retrieve."),
    as_json: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Ask a question; prints status, answer, verified citations, retrieval and cost info."""
    import json

    from . import config
    from .answer import ask as run_ask
    from .retrieve import load_index

    index = load_index(doc)
    if not index.chunks:
        typer.echo("No ingested documents. Run `kirana ingest <pdf>` first.", err=True)
        raise typer.Exit(1)
    ans = run_ask(question, index, k)
    if as_json:
        out = {
            "question": ans.question,
            "status": ans.status,
            "answer": ans.answer,
            "error": ans.error,
            "citations": [c.__dict__ for c in ans.citations],
            "retrieved": [
                {
                    "chunk_id": h.chunk.chunk_id,
                    "doc_id": h.chunk.doc_id,
                    "pages": h.chunk.pages,
                    "type": h.chunk.type,
                    "score": round(h.score, 4),
                }
                for h in ans.hits
            ],
            "latency_ms": {"retrieval": round(ans.retrieval_ms, 1), "llm": round(ans.llm_ms, 1)},
            "tokens": {"in": ans.tokens_in, "out": ans.tokens_out},
            "cost_usd": ans.cost,
        }
        typer.echo(json.dumps(out, indent=2))
        raise typer.Exit(0 if not ans.error else 2)
    if ans.error:
        console.print(f"[red]ERROR:[/red] {ans.error}")
        raise typer.Exit(2)
    colour = {"answered": "green", "refused": "yellow", "conflict": "magenta"}[ans.status]
    console.print(f"[bold {colour}]{ans.status.upper()}[/bold {colour}]")
    console.print(ans.answer)
    if ans.citations:
        console.print("\n[bold]Citations[/bold]")
    by_id = {h.chunk.chunk_id: h.chunk for h in ans.hits}
    for c in ans.citations:
        ch = by_id.get(c.chunk_id)
        what = f"{ch.type}: {ch.caption or ch.section}" if ch else "unknown chunk"
        mark = (
            "[green]verified[/green]"
            if c.verified
            else f"[red]NOT VERIFIED[/red] ({escape(c.reason)})"
        )
        console.print(
            f"  p{c.page}  {c.chunk_id}  ({escape(what)})  {mark}", markup=True, highlight=False
        )
        console.print(f'     "{c.quote}"', highlight=False, markup=False)
    console.print("\n[bold]Retrieved[/bold]")
    for h in ans.hits:
        console.print(
            f"  {h.rank}. {h.chunk.chunk_id:8} {_pages(h.chunk.pages):6} {h.score:7.3f}",
            highlight=False,
        )
    cost = "unknown (no price configured)" if ans.cost is None else f"${ans.cost:.5f}"
    console.print(
        f"\nlatency: retrieval {ans.retrieval_ms:.1f} ms, llm {ans.llm_ms:.0f} ms | "
        f"tokens: {ans.tokens_in} in / {ans.tokens_out} out | est. cost: {cost} "
        f"| model: {config.settings().model}"
    )


if __name__ == "__main__":
    app()
