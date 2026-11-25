from revizorro.tools.linter import lint
from revizorro.tools.quotes import normalize, verify_quote


def _block(doc, prefix):
    return next(b for b in doc.blocks if b.text.startswith(prefix))


def test_normalize_unifies_quotes_dashes_and_spaces():
    assert normalize("«Порог, ₸» —  1 000") == normalize('"порог, ₸" - 1 000')


def test_exact_quote(small_doc):
    b = _block(small_doc, "Ф-1.")
    m = verify_quote(small_doc, b.id, "задаёт порог от 1 000 до 5 000 ₸")
    assert m.ok and m.exact and m.block_id == b.id


def test_quote_reanchored_to_the_right_block(small_doc):
    wrong = _block(small_doc, "Ф-2.")
    right = _block(small_doc, "Ф-1.")
    m = verify_quote(small_doc, wrong.id, "Пользователь задаёт порог")
    assert m.ok and m.block_id == right.id


def test_fuzzy_quote_accepted_and_replaced_by_block_text(small_doc):
    b = _block(small_doc, "Ф-2.")
    m = verify_quote(small_doc, b.id, "Система быстро отправляет уведомления")
    assert m.ok and not m.exact and m.quote == b.text


def test_invented_quote_rejected(small_doc):
    b = _block(small_doc, "Ф-2.")
    assert not verify_quote(small_doc, b.id, "сервис гарантирует доставку за 5 секунд").ok


def test_quote_with_ellipsis(small_doc):
    b = _block(small_doc, "Ф-1.")
    assert verify_quote(small_doc, b.id, "Пользователь задаёт … ₸ включительно").ok


def test_linter_rules(small_doc):
    rules = {(s.rule, s.fragment) for s in lint(small_doc)}
    assert ("vague", "быстро") in rules
    assert ("empty_row", "(пусто)") in rules
    assert ("empty_section", "Пустой раздел") in rules
    assert any(rule == "mixed_units" for rule, _ in rules)


def test_rule_findings_are_anchored(small_doc, tmp_path):
    from revizorro.domain.models import Requirement
    from revizorro.ingestion import load_document
    from revizorro.tools.linter import rule_findings

    f1 = next(b for b in small_doc.blocks if b.text.startswith("Ф-1."))
    reqs = [
        Requirement(
            rid="R-01", source_ref="п.1", kind="functional", summary="s", quote="q", block_ids=[f1.id]
        )
    ]
    found = {f.title: f for f in rule_findings(small_doc, lint(small_doc), reqs)}
    mixed = found["Денежные суммы заданы в двух единицах: в тиынах и в тенге"]
    assert mixed.locations[0].quote == "Хранить сумму в тиынах и порог в тенге."
    assert verify_quote(small_doc, mixed.locations[0].block_id, mixed.locations[0].quote).ok
    blank = found["Незаполненные разделы и поля шаблона"]
    assert "пустых разделов — 1" in blank.problem and "пустых строк таблиц — 1" in blank.problem

    path = tmp_path / "open.md"
    path.write_text("# Д\n\n* Коды 400, 401 и далее — ошибки.\n", encoding="utf-8")
    doc = load_document(path)
    item = next(b for b in doc.blocks if b.kind == "list_item")
    reqs = [
        Requirement(rid="R-01", source_ref="п.1", kind="api", summary="s", quote="q", block_ids=[item.id])
    ]
    open_list = next(f for f in rule_findings(doc, lint(doc), reqs) if f.title.startswith("Открытый"))
    assert open_list.rid == "R-01" and open_list.criterion == "unambiguous"


def test_blank_sections_are_cited_by_heading(tmp_path):
    from revizorro.ingestion import load_document
    from revizorro.tools.linter import rule_findings

    path = tmp_path / "blank.md"
    lines = [
        "# Док",
        "",
        "Версия документа: не указана.",
        "",
        "## 7. Откат",
        "",
        "## 8. Согласование",
        "",
        "| Роль | ФИО |",
        "| --- | --- |",
        "| | |",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    doc = load_document(path)
    blank = next(f for f in rule_findings(doc, lint(doc), []) if f.title.startswith("Незаполненные"))
    quotes = [loc.quote for loc in blank.locations]
    assert "7. Откат" in quotes and "8. Согласование" in quotes  # numbered heading is not cut to "7."
    assert "Версия документа: не указана." in quotes
    assert all("(пусто)" not in q for q in quotes)  # our own markup is never presented as a quote
    assert all(verify_quote(doc, loc.block_id, loc.quote).ok for loc in blank.locations)


def test_dash_is_only_a_hint_and_conversion_rule_silences_unit_mix(tmp_path):
    from revizorro.ingestion import load_document
    from revizorro.tools.linter import rule_findings

    lines = [
        "# Док",
        "",
        "Сумма хранится в тиынах, порог задаётся в тенге. Пересчёт: 1 тенге = 100 тиынов.",
        "",
        "| Поле | DB field |",
        "| --- | --- |",
        "| result | — |",
        "| Примечание: Да / Нет | |",
        "",
    ]
    path = tmp_path / "doc.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    doc = load_document(path)
    signals = lint(doc)
    assert any(s.rule == "dash" for s in signals)
    findings = rule_findings(doc, signals, [])
    assert not any("единиц" in f.title for f in findings)  # the document describes the conversion
    blank = next(f for f in findings if f.title.startswith("Незаполненные"))
    assert "прочерк" not in blank.problem and "неотмеченных пунктов чек-листа" in blank.problem
    assert [loc.quote for loc in blank.locations] == ["Примечание: Да / Нет"]  # empty-cell mark is not quoted


def test_linter_deduplicates(small_doc):
    signals = lint(small_doc)
    keys = [(s.block_id, s.rule, s.fragment) for s in signals]
    assert len(keys) == len(set(keys))
