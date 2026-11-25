"""Rule-based signals passed to agents as hints and shown in the report appendix."""

from __future__ import annotations

import re

from revizorro.domain.models import Block, Document, Finding, LinterSignal, Location, Requirement

EMPTY_MARK = "(пусто)"  # how the Markdown parser renders an empty table cell

_VAGUE = [
    r"быстр\w*",
    r"своевременн\w*",
    r"удобн\w*",
    r"оптимальн\w*",
    r"эффективн\w*",
    r"достаточн\w*",
    r"приемлем\w*",
    r"интуитивн\w*",
    r"гибк\w*",
    r"над[её]жн\w*",
    r"легко",
    r"мгновенн\w*",
    r"в кратчайш\w*",
    r"в момент\b",
    r"как правило",
    r"обычно",
    r"при необходимости",
    r"по возможности",
    r"и/или",
    r"некотор\w*",
    r"различн\w*",
    r"соответствующ\w*",
    r"корректн\w*",
    r"неверно",
]
_VAGUE_RE = re.compile(r"(?<![\w-])(" + "|".join(_VAGUE) + r")", re.IGNORECASE)

_OPEN_LIST_RE = re.compile(
    r"(?<![\w-])(и далее|и т\.\s?[дп]\.?|и др\.|и тому подобн\w*|и прочее)", re.IGNORECASE
)

_PLACEHOLDER_RE = re.compile(
    r"(\bTBD\b|\bTODO\b|\?\?\?|заполня\w+ \w+|не заполнен\w*|не указан\w*)", re.IGNORECASE
)
_UNCHECKED = "Да / Нет"  # checklist options left as printed in the template
_DASH_RE = re.compile(r"(^—$|: —|Prod: —)")
# The document explains how tiyn and tenge relate: a conversion verb next to a unit, or "1 тенге = 100 тиынов".
_CONVERSION_RE = re.compile(
    r"(пересч[её]т\w*|пересчит\w*|конверт\w*|перевод\w*)[^.]{0,40}(тиын|тенге)"
    r"|1 ?тенге ?= ?100|100 ?тиын\w* ?= ?1|[/×*] ?100\b",
    re.IGNORECASE,
)

_MONEY_UNITS = {
    "тиын": re.compile(r"тиын\w*", re.IGNORECASE),
    "тенге": re.compile(r"тенге|₸|\bKZT\b", re.IGNORECASE),
}


def lint(doc: Document) -> list[LinterSignal]:
    signals: list[LinterSignal] = []
    for b in doc.blocks:
        if b.kind == "heading":
            continue
        for m in _VAGUE_RE.finditer(b.text):
            signals.append(
                LinterSignal(
                    block_id=b.id,
                    rule="vague",
                    message="размытое или неизмеримое слово",
                    fragment=m.group(0),
                )
            )
        for m in _PLACEHOLDER_RE.finditer(b.text):
            signals.append(
                LinterSignal(
                    block_id=b.id, rule="placeholder", message="заглушка вместо текста", fragment=m.group(0)
                )
            )
        if _UNCHECKED in b.text:
            signals.append(
                LinterSignal(
                    block_id=b.id,
                    rule="unchecked",
                    message="пункт чек-листа не отмечен",
                    fragment=_UNCHECKED,
                )
            )
        cells = [c.strip() for c in b.text.split(" | ")] if b.kind == "table_row" else []
        if cells and all(c == EMPTY_MARK for c in cells):
            signals.append(
                LinterSignal(
                    block_id=b.id, rule="empty_row", message="пустая строка таблицы", fragment=EMPTY_MARK
                )
            )
        # A dash may mean "not applicable", so it is only a hint for the agents, never a finding by itself.
        if any(c == "—" for c in cells) or _DASH_RE.search(b.text):
            signals.append(
                LinterSignal(
                    block_id=b.id, rule="dash", message="вместо значения стоит прочерк", fragment="—"
                )
            )

    # Sections with a heading but no content before the next heading of the same or higher level.
    for i, b in enumerate(doc.blocks):
        if b.kind != "heading":
            continue
        nxt = doc.blocks[i + 1] if i + 1 < len(doc.blocks) else None
        if nxt is None or (nxt.kind == "heading" and (nxt.heading_level or 9) <= (b.heading_level or 9)):
            signals.append(
                LinterSignal(block_id=b.id, rule="empty_section", message="пустой раздел", fragment=b.text)
            )

    # One quantity in several units (money is the usual suspect in fintech specs).
    used = {unit: [b for b in doc.blocks if rx.search(b.text)] for unit, rx in _MONEY_UNITS.items()}
    if all(used.values()):
        for b in used["тиын"]:
            signals.append(
                LinterSignal(
                    block_id=b.id,
                    rule="mixed_units",
                    message="денежные величины в документе заданы и в тенге, и в тиынах",
                    fragment=_MONEY_UNITS["тиын"].search(b.text).group(0),  # type: ignore[union-attr]
                )
            )

    for b in doc.blocks:
        if b.kind == "heading":
            continue
        for m in _OPEN_LIST_RE.finditer(b.text):
            signals.append(
                LinterSignal(
                    block_id=b.id, rule="open_list", message="открытый перечень", fragment=m.group(0)
                )
            )

    # One signal per (block, rule, fragment).
    seen: set[tuple[str, str, str]] = set()
    unique: list[LinterSignal] = []
    for s in signals:
        key = (s.block_id, s.rule, s.fragment.lower())
        if key not in seen:
            seen.add(key)
            unique.append(s)
    return unique


def _quote_around(text: str, fragment: str, limit: int = 160) -> str:
    """Verbatim quote for a rule hit: the whole block if short, else a window around the fragment."""
    if len(text) <= limit:
        return text
    at = text.lower().find(fragment.lower())
    if at < 0:
        return text[:limit]
    start = max(0, at - limit // 2)
    end = min(len(text), at + len(fragment) + limit // 2)
    if start > 0:  # snap to word boundaries so the quote does not start or end mid-word
        start = text.find(" ", start) + 1
    if end < len(text):
        end = text.rfind(" ", 0, end)
    return text[start:end].strip()


def _row_quote(text: str, fragment: str) -> str:
    """Contiguous non-empty cells of a table row around the fragment (our empty-cell mark is never quoted)."""
    runs: list[list[str]] = [[]]
    for cell in text.split(" | "):
        if cell.strip() == EMPTY_MARK:
            runs.append([])
        else:
            runs[-1].append(cell)
    joined = [" | ".join(r) for r in runs if r]
    return next((q for q in joined if fragment in q), joined[0] if joined else text)


def _section_heading(doc: Document, block_id: str) -> Block | None:
    """Nearest heading above a block."""
    idx = next((i for i, b in enumerate(doc.blocks) if b.id == block_id), None)
    if idx is None:
        return None
    for b in reversed(doc.blocks[: idx + 1]):
        if b.kind == "heading":
            return b
    return None


def _unique(locs: list[Location]) -> list[Location]:
    seen: set[tuple[str, str]] = set()
    out: list[Location] = []
    for loc in locs:
        key = (loc.block_id, loc.quote)
        if key not in seen:
            seen.add(key)
            out.append(loc)
    return out


def rule_findings(doc: Document, signals: list[LinterSignal], reqs: list[Requirement]) -> list[Finding]:
    """Turn reliable rule hits into findings; the critic reviews them like any other."""
    rid_of = {b: r.rid for r in reqs for b in r.block_ids}
    out: list[Finding] = []

    def loc(s: LinterSignal) -> Location:
        b = doc.block(s.block_id)
        if s.fragment == EMPTY_MARK:
            # An empty cell has no text to quote: cite the heading of its section instead of our markup.
            heading = _section_heading(doc, s.block_id)
            if heading is not None:
                return Location(block_id=heading.id, quote=heading.text)
        text = b.text if b else s.fragment
        if b is not None and b.kind == "table_row":
            text = _row_quote(text, s.fragment)
        return Location(block_id=s.block_id, quote=_quote_around(text, s.fragment))

    mixed = [s for s in signals if s.rule == "mixed_units"]
    if mixed and not any(_CONVERSION_RE.search(b.text) for b in doc.blocks):
        tiyn_blocks = {s.block_id for s in mixed}
        locations = [loc(s) for s in mixed[:2]]
        tenge = next(
            (
                b
                for b in doc.blocks
                if b.kind != "heading"
                and b.id not in tiyn_blocks
                and re.search(r"тенге", b.text, re.IGNORECASE)
            ),
            None,
        )
        if tenge is not None:
            text = _row_quote(tenge.text, "тенге") if tenge.kind == "table_row" else tenge.text
            locations.append(Location(block_id=tenge.id, quote=_quote_around(text, "тенге")))
        involved = tiyn_blocks | ({tenge.id} if tenge else set())
        out.append(
            Finding(
                fid="",
                scope="set",
                related_rids=sorted({rid_of[b] for b in involved if b in rid_of}),
                criterion="set_consistent",
                severity="major",
                title="Денежные суммы заданы в двух единицах: в тиынах и в тенге",
                problem="В документе одни денежные суммы заданы в тиынах, другие — в тенге (₸, KZT). "
                "Где и как выполняется пересчёт между ними и как округляется результат, документ не описывает.",
                impact="Если сумму в тиынах сравнить или сложить с суммой в тенге без пересчёта, результат "
                "будет неверным в 100 раз. Тестировщику неясно, в каких единицах проверять значения "
                "в хранилище, API и уведомлениях.",
                suggestion="Выбрать одну единицу для хранения и передачи сумм или описать правило пересчёта "
                "и округления; указать единицу у каждого денежного поля.",
                locations=locations,
                source_agent="linter",
            )
        )

    for s in signals:
        if s.rule != "open_list":
            continue
        rid = rid_of.get(s.block_id)
        out.append(
            Finding(
                fid="",
                scope="requirement" if rid else "set",
                rid=rid,
                criterion="unambiguous" if rid else "set_comprehensible",
                severity="minor",
                title=f"Открытый перечень «{s.fragment}»",
                problem=f"Перечень заканчивается словами «{s.fragment}»: неизвестно, какие ещё элементы в него входят.",
                impact="Разработчик и тестировщик по-разному определят границы перечня; полный набор тестов составить нельзя.",
                suggestion="Перечислить все элементы явно или задать правило, по которому элемент входит в перечень.",
                locations=[loc(s)],
                source_agent="linter",
            )
        )

    blank_rules = {
        "empty_section": ("пустых разделов", "раздел с заголовком, но без содержимого"),
        "placeholder": ("заглушек вместо текста", "заглушка вместо текста"),
        "unchecked": ("неотмеченных пунктов чек-листа («Да / Нет»)", "пункт чек-листа не отмечен"),
        "empty_row": ("пустых строк таблиц", "пустая строка таблицы"),
    }
    blanks = [s for s in signals if s.rule in blank_rules]
    if blanks:
        counts = {rule: len({s.block_id for s in blanks if s.rule == rule}) for rule in blank_rules}
        parts = "; ".join(f"{blank_rules[rule][0]} — {n}" for rule, n in counts.items() if n)
        picked: list[LinterSignal] = []
        seen_groups: set[tuple[str, str]] = set()
        for s in blanks:  # one location per rule and section keeps the finding readable
            b = doc.block(s.block_id)
            # An empty section is its own group; other hits are grouped by the section they sit in.
            section = s.block_id if b is None or b.kind == "heading" else " › ".join(b.section)
            if (s.rule, section) not in seen_groups:
                seen_groups.add((s.rule, section))
                picked.append(s)
        out.append(
            Finding(
                fid="",
                scope="set",
                criterion="set_complete",
                severity="minor",
                title="Незаполненные разделы и поля шаблона",
                problem=f"В документе остались незаполненные элементы шаблона: {parts}.",
                impact="По документу нельзя понять, проведены ли ревью, согласование и тестирование требований.",
                suggestion="Заполнить эти разделы и поля или явно пометить их как неприменимые с указанием причины.",
                locations=_unique([loc(s) for s in picked])[:6],
                source_agent="linter",
            )
        )
    return out


def signals_for_prompt(signals: list[LinterSignal], block_ids: set[str] | None = None) -> str:
    rows = [s for s in signals if block_ids is None or s.block_id in block_ids]
    if not rows:
        return "(сигналов нет)"
    return "\n".join(f"- [{s.block_id}] {s.message}: «{s.fragment}»" for s in rows)
