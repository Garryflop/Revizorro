"""Split Markdown into anchored blocks (headings, paragraphs, list items, table rows, code)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from markdown_it import MarkdownIt
from markdown_it.token import Token

from revizorro.domain.models import Block, BlockKind

EMPTY_CELL = "(пусто)"


@dataclass
class _Raw:
    kind: BlockKind
    text: str
    line_start: int
    line_end: int
    section: list[str]
    order: int
    heading_level: int | None = None
    table_header: list[str] | None = None


@dataclass
class _ListCollector:
    line_start: int
    line_end: int
    parts: list[str] = field(default_factory=list)


def inline_text(token: Token) -> str:
    """Plain text of an inline token: strips emphasis, keeps code and link text."""
    out: list[str] = []
    for child in token.children or []:
        if child.type == "html_inline":
            out.append(" " if child.content.lower().startswith("<br") else child.content)
        elif child.type in ("text", "code_inline"):
            out.append(child.content)
        elif child.type in ("softbreak", "hardbreak"):
            out.append(" ")
        elif child.type == "image":
            out.append(child.content or "")
    return " ".join("".join(out).split())


def _map(token: Token) -> tuple[int, int]:
    if token.map:
        return token.map[0] + 1, max(token.map[0] + 1, token.map[1])
    return 0, 0


_SENTENCE_END = tuple(".!?:;»)]")


def _join_broken_paragraphs(raws: list[_Raw]) -> list[_Raw]:
    """PDF extraction may split one paragraph at a line or page break; glue such pieces back."""
    out: list[_Raw] = []
    for r in raws:
        prev = out[-1] if out else None
        if (
            prev is not None
            and prev.kind == r.kind == "paragraph"
            and prev.section == r.section
            and not prev.text.endswith(_SENTENCE_END)
            and r.text[:1].islower()
        ):
            prev.text = f"{prev.text} {r.text}"
            prev.line_end = r.line_end
            continue
        out.append(r)
    return out


def parse_markdown(markdown: str, page_of_line: Callable[[int], int | None] | None = None) -> list[Block]:
    md = MarkdownIt("commonmark").enable("table")
    tokens = md.parse(markdown)

    raws: list[_Raw] = []
    headings: list[tuple[int, str]] = []  # (level, text) stack
    lists: list[_ListCollector] = []
    order = 0

    def section() -> list[str]:
        return [t for _, t in headings]

    def emit(kind: BlockKind, text: str, start: int, end: int, **extra: object) -> None:
        nonlocal order
        text = " ".join(text.split())
        if not text:
            return
        order += 1
        raws.append(_Raw(kind, text, start, end, section(), order, **extra))  # type: ignore[arg-type]

    i = 0
    table_header: list[str] | None = None
    in_thead = False
    while i < len(tokens):
        tok = tokens[i]
        if tok.type == "heading_open":
            level = int(tok.tag[1:])
            text = inline_text(tokens[i + 1])
            start, end = _map(tok)
            while headings and headings[-1][0] >= level:
                headings.pop()
            emit("heading", text, start, end, heading_level=level)
            headings.append((level, text))
            i += 3
            continue
        if tok.type == "list_item_open":
            start, end = _map(tok)
            lists.append(_ListCollector(start, end))
        elif tok.type == "list_item_close":
            item = lists.pop()
            emit("list_item", " ".join(item.parts), item.line_start, item.line_end)
        elif tok.type == "inline" and lists and tokens[i - 1].type == "paragraph_open":
            item = lists[-1]
            start, end = _map(tokens[i - 1])  # paragraph range excludes trailing blank lines
            if not item.parts:
                item.line_start = start
            item.line_end = end
            item.parts.append(inline_text(tok))
        elif tok.type == "paragraph_open" and not lists:
            start, end = _map(tok)
            emit("paragraph", inline_text(tokens[i + 1]), start, end)
            i += 3
            continue
        elif tok.type == "thead_open":
            in_thead = True
        elif tok.type == "thead_close":
            in_thead = False
        elif tok.type == "table_close":
            table_header = None
        elif tok.type == "tr_open":
            start, end = _map(tok)
            cells: list[str] = []
            j = i + 1
            while tokens[j].type != "tr_close":
                if tokens[j].type == "inline":
                    cells.append(inline_text(tokens[j]) or EMPTY_CELL)
                j += 1
            if in_thead:
                table_header = cells
                emit("table_header", " | ".join(cells), start, end)
            else:
                emit("table_row", " | ".join(cells), start, end, table_header=table_header)
            i = j + 1
            continue
        elif tok.type in ("fence", "code_block"):
            start, end = _map(tok)
            emit("code", tok.content, start, end)
        i += 1

    raws.sort(key=lambda r: (r.line_start, r.order))
    raws = _join_broken_paragraphs(raws)
    width = max(3, len(str(len(raws))))
    blocks: list[Block] = []
    for n, r in enumerate(raws, start=1):
        blocks.append(
            Block(
                id=f"B{n:0{width}d}",
                kind=r.kind,
                text=r.text,
                section=r.section,
                line_start=r.line_start,
                line_end=r.line_end,
                page=page_of_line(r.line_start) if page_of_line else None,
                heading_level=r.heading_level,
                table_header=r.table_header,
            )
        )
    return blocks
