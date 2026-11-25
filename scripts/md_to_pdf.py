"""Render a Markdown requirements file to an A4 PDF to test PDF ingestion.

Usage: uv run --project backend python scripts/md_to_pdf.py examples/requirements.md examples/requirements.pdf
"""

import sys
from pathlib import Path

import pymupdf
from markdown_it import MarkdownIt

src, dst = Path(sys.argv[1]), Path(sys.argv[2])
html = MarkdownIt("commonmark").enable("table").render(src.read_text(encoding="utf-8"))
css = """
body { font-family: sans-serif; font-size: 10pt; }
h1 { font-size: 16pt; } h2 { font-size: 14pt; } h3 { font-size: 12pt; } h4 { font-size: 11pt; }
table { border-collapse: collapse; } td, th { border: 1px solid #888; padding: 2px 4px; font-size: 9pt; }
code, pre { font-family: monospace; font-size: 8.5pt; }
"""
story = pymupdf.Story(html=html, user_css=css)
writer = pymupdf.DocumentWriter(str(dst))
mediabox = pymupdf.paper_rect("a4")
where = mediabox + (50, 50, -50, -50)  # noqa: RUF005 - pymupdf Rect arithmetic, not tuple concat
more = True
while more:
    device = writer.begin_page(mediabox)
    more, _ = story.place(where)
    story.draw(device)
    writer.end_page()
writer.close()
print("pages:", pymupdf.open(str(dst)).page_count)
