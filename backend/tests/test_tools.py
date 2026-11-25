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
    assert ("placeholder", "(пусто)") in rules
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
    mixed = found["Денежные величины заданы в разных единицах: тенге и тиыны"]
    assert mixed.locations[0].quote == "Хранить сумму в тиынах и порог в тенге."
    assert verify_quote(small_doc, mixed.locations[0].block_id, mixed.locations[0].quote).ok
    assert "Незаполненные поля и разделы шаблона" in found

    path = tmp_path / "open.md"
    path.write_text("# Д\n\n* Коды 400, 401 и далее — ошибки.\n", encoding="utf-8")
    doc = load_document(path)
    item = next(b for b in doc.blocks if b.kind == "list_item")
    reqs = [
        Requirement(rid="R-01", source_ref="п.1", kind="api", summary="s", quote="q", block_ids=[item.id])
    ]
    open_list = next(f for f in rule_findings(doc, lint(doc), reqs) if f.title.startswith("Открытый"))
    assert open_list.rid == "R-01" and open_list.criterion == "unambiguous"


def test_linter_deduplicates(small_doc):
    signals = lint(small_doc)
    keys = [(s.block_id, s.rule, s.fragment) for s in signals]
    assert len(keys) == len(set(keys))
