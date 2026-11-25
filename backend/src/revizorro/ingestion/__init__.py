"""Load a requirements document of any supported format into a block-anchored Document."""

from __future__ import annotations

import bisect
import hashlib
from pathlib import Path

from revizorro.domain.models import Document
from revizorro.ingestion.markdown import parse_markdown

SUPPORTED = {".md", ".markdown", ".txt", ".pdf", ".docx"}


class UnsupportedFormatError(ValueError):
    pass


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp1251"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _pdf_to_markdown(path: Path) -> tuple[str, list[int]]:
    """Return markdown and the first line number of each page (1-based)."""
    import pymupdf
    import pymupdf4llm

    with pymupdf.open(str(path)) as pdf:
        has_text = any(str(page.get_text("text")).strip() for page in pdf)
    if not has_text:
        raise ValueError(f"В PDF нет текстового слоя (скан?): {path}. Нужен PDF с текстом.")
    chunks = pymupdf4llm.to_markdown(str(path), page_chunks=True, show_progress=False, use_ocr=False)
    parts: list[str] = []
    page_starts: list[int] = []
    line = 1
    for chunk in chunks:
        text = (chunk.get("text") if isinstance(chunk, dict) else str(chunk)) or ""
        page_starts.append(line)
        parts.append(text.rstrip() + "\n\n")
        line += text.rstrip().count("\n") + 2
    return "".join(parts), page_starts


def _docx_to_markdown(path: Path) -> str:
    """Convert DOCX paragraphs and tables (in body order) to Markdown."""
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    document = docx.Document(str(path))
    out: list[str] = []
    for element in document.element.body.iterchildren():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag == "p":
            par = Paragraph(element, document)
            text = " ".join(par.text.split())
            if not text:
                continue
            style = (par.style.name if par.style is not None else "") or ""
            level = None
            for prefix in ("Heading", "Заголовок", "Title"):
                if style.startswith(prefix):
                    digits = "".join(ch for ch in style if ch.isdigit())
                    level = int(digits) if digits else 1
            is_list = (
                "List" in style
                or "Спис" in style
                or (element.pPr is not None and element.pPr.numPr is not None)
            )
            if level:
                out.append(f"{'#' * min(level, 6)} {text}\n")
            elif is_list:
                out.append(f"- {text}")
            else:
                out.append(f"\n{text}\n")
        elif tag == "tbl":
            table = Table(element, document)
            rows = [[" ".join(c.text.split()).replace("|", "/") for c in r.cells] for r in table.rows]
            if not rows:
                continue
            width = max(len(r) for r in rows)
            rows = [r + [""] * (width - len(r)) for r in rows]
            out.append("")
            out.append("| " + " | ".join(rows[0]) + " |")
            out.append("|" + " --- |" * width)
            out.extend("| " + " | ".join(r) + " |" for r in rows[1:])
            out.append("")
    return "\n".join(out) + "\n"


def load_document(path: str | Path) -> Document:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Файл не найден: {path}")
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED:
        raise UnsupportedFormatError(
            f"Формат {suffix or '(без расширения)'} не поддерживается. Поддерживаются: {', '.join(sorted(SUPPORTED))}"
        )

    page_starts: list[int] | None = None
    if suffix == ".pdf":
        markdown, page_starts = _pdf_to_markdown(path)
        fmt = "pdf"
    elif suffix == ".docx":
        markdown = _docx_to_markdown(path)
        fmt = "docx"
    else:
        markdown = _read_text(path)
        fmt = "markdown" if suffix in (".md", ".markdown") else "text"

    def page_of_line(line: int) -> int | None:
        if not page_starts:
            return None
        return bisect.bisect_right(page_starts, line)

    blocks = parse_markdown(markdown, page_of_line if page_starts else None)
    if not blocks:
        raise ValueError(f"В документе не найден текст: {path}")
    title = next((b.text for b in blocks if b.kind == "heading"), path.stem)
    return Document(
        title=title,
        source_path=str(path),
        source_format=fmt,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        markdown=markdown,
        blocks=blocks,
    )
