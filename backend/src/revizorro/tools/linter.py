"""Rule-based signals passed to agents as hints and shown in the report appendix."""

from __future__ import annotations

import re

from revizorro.domain.models import Document, Finding, LinterSignal, Location, Requirement

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
    r"(\bTBD\b|\bTODO\b|\?\?\?|заполня\w+ \w+|не заполнен\w*|\(пусто\)|Да / Нет|^—$|: —|\| — \||Prod: —)",
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
                    block_id=b.id,
                    rule="placeholder",
                    message="заглушка или незаполненное поле шаблона",
                    fragment=m.group(0).strip(" |:"),
                )
            )
        if b.kind == "table_row" and any(cell.strip() == "—" for cell in b.text.split(" | ")):
            signals.append(
                LinterSignal(
                    block_id=b.id, rule="placeholder", message="значение не указано («—»)", fragment="—"
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
    """The sentence containing the fragment, trimmed to a verbatim window if it is long."""
    at = text.lower().find(fragment.lower())
    if at < 0:
        return text[:limit]
    start = max(text.rfind(". ", 0, at) + 2, 0) if text.rfind(". ", 0, at) >= 0 else 0
    end = text.find(". ", at)
    end = len(text) if end < 0 else end + 1
    if end - start > limit:
        start, end = max(0, at - limit // 2), min(len(text), at + len(fragment) + limit // 2)
    return text[start:end].strip()


def rule_findings(doc: Document, signals: list[LinterSignal], reqs: list[Requirement]) -> list[Finding]:
    """Turn reliable rule hits into findings; the critic reviews them like any other."""
    rid_of = {b: r.rid for r in reqs for b in r.block_ids}
    out: list[Finding] = []

    def loc(s: LinterSignal) -> Location:
        b = doc.block(s.block_id)
        text = b.text if b else s.fragment
        return Location(block_id=s.block_id, quote=_quote_around(text, s.fragment))

    mixed = [s for s in signals if s.rule == "mixed_units"]
    if mixed:
        out.append(
            Finding(
                fid="",
                scope="set",
                related_rids=sorted({rid_of[s.block_id] for s in mixed if s.block_id in rid_of}),
                criterion="set_consistent",
                severity="major",
                title="Денежные величины заданы в разных единицах: тенге и тиыны",
                problem="Часть сумм в документе задана в тенге (₸, KZT), часть — в тиынах. Не определено, "
                "в каких единицах суммы хранятся, передаются и сравниваются, и где выполняется пересчёт.",
                impact="Возможна ошибка сравнения или суммирования в 100 раз; тестировщик не знает, в каких "
                "единицах проверять сохранённые и переданные значения.",
                suggestion="Зафиксировать одну единицу для хранения и передачи денежных сумм (например, тиыны "
                "целым числом) и правило пересчёта; указать единицу явно у каждого поля.",
                locations=[loc(s) for s in mixed[:4]],
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

    blanks = [s for s in signals if s.rule in ("placeholder", "empty_section")]
    if blanks:
        picked: list[LinterSignal] = []
        seen_sections: set[str] = set()
        for s in blanks:  # one location per section keeps the finding readable
            b = doc.block(s.block_id)
            section = " › ".join(b.section) if b else s.block_id
            if section not in seen_sections:
                seen_sections.add(section)
                picked.append(s)
        out.append(
            Finding(
                fid="",
                scope="set",
                criterion="set_complete",
                severity="minor",
                title="Незаполненные поля и разделы шаблона",
                problem=f"В документе {len({s.block_id for s in blanks})} незаполненных элементов шаблона: "
                "пустые разделы, заглушки, неотмеченные варианты «Да / Нет», прочерки вместо значений.",
                impact="Не видно, проведены ли ревью, согласования и тестирование требований; часть значений, "
                "нужных для реализации, отсутствует.",
                suggestion="Заполнить разделы или явно пометить их как неприменимые с причиной.",
                locations=[loc(s) for s in picked[:6]],
                source_agent="linter",
            )
        )
    return out


def signals_for_prompt(signals: list[LinterSignal], block_ids: set[str] | None = None) -> str:
    rows = [s for s in signals if block_ids is None or s.block_id in block_ids]
    if not rows:
        return "(сигналов нет)"
    return "\n".join(f"- [{s.block_id}] {s.message}: «{s.fragment}»" for s in rows)
