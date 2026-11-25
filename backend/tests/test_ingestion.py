from pathlib import Path

import pytest

from revizorro.ingestion import UnsupportedFormatError, load_document


def test_blocks_keep_structure(small_doc):
    kinds = [b.kind for b in small_doc.blocks]
    assert small_doc.title == "Тестовый документ"
    assert "list_item" in kinds and "table_row" in kinds and "table_header" in kinds
    f1 = next(b for b in small_doc.blocks if b.text.startswith("Ф-1."))
    assert f1.section == ["Тестовый документ", "Функциональные требования"]
    assert f1.line_start == 5
    assert "**" not in f1.text  # emphasis stripped


def test_table_rows_carry_header_and_empty_cells(small_doc):
    rows = [b for b in small_doc.blocks if b.kind == "table_row"]
    assert rows[0].table_header == ["Условие", "Результат"]
    assert rows[1].text == "(пусто) | (пусто)"


def test_ids_are_sequential_and_render_tagged(small_doc):
    ids = [b.id for b in small_doc.blocks]
    assert ids == [f"B{n:03d}" for n in range(1, len(ids) + 1)]
    rendered = small_doc.render_for_llm()
    assert "[B001] # Тестовый документ" in rendered
    assert "(строка таблицы) Порог 1 000 ₸ | Сохранено" in rendered


def test_location_label(small_doc):
    f2 = next(b for b in small_doc.blocks if b.text.startswith("Ф-2."))
    assert small_doc.location_label(f2.id) == "Тестовый документ › Функциональные требования, строка 6"


def test_example_document_parses(example_doc):
    assert example_doc.title == "Уведомление о расходах по карте"
    assert len(example_doc.blocks) > 100
    assert any(b.text.startswith("Ф-3.") for b in example_doc.blocks)


def test_docx_roundtrip(tmp_path: Path):
    import docx

    d = docx.Document()
    d.add_heading("Спецификация", level=1)
    d.add_paragraph("Система должна хранить порог.")
    table = d.add_table(rows=2, cols=2)
    table.cell(0, 0).text, table.cell(0, 1).text = "Поле", "Значение"
    table.cell(1, 0).text, table.cell(1, 1).text = "amount", "integer"
    path = tmp_path / "spec.docx"
    d.save(str(path))

    doc = load_document(path)
    assert doc.title == "Спецификация"
    assert any(b.kind == "table_row" and b.text == "amount | integer" for b in doc.blocks)


def test_pdf_pages(tmp_path: Path):
    import pymupdf

    pdf = pymupdf.open()
    for text in ("Требование один: порог хранится.", "Требование два: push отправляется."):
        page = pdf.new_page()
        page.insert_text((72, 72), text, fontname="helv")
    path = tmp_path / "spec.pdf"
    pdf.save(str(path))

    doc = load_document(path)
    assert doc.source_format == "pdf"
    pages = {b.page for b in doc.blocks}
    assert pages == {1, 2}


def test_broken_paragraph_is_joined(tmp_path: Path):
    path = tmp_path / "broken.md"
    path.write_text(
        "# Док\n\nСервис получает порог\n\nкарты и отправляет push.\n\nНовый абзац.\n", encoding="utf-8"
    )
    texts = [b.text for b in load_document(path).blocks if b.kind == "paragraph"]
    assert texts == ["Сервис получает порог карты и отправляет push.", "Новый абзац."]


def test_br_in_table_cell(tmp_path: Path):
    path = tmp_path / "br.md"
    path.write_text(
        "| Поле | Значение |\n| --- | --- |\n| Роль<br>аналитик | 1<br>знак |\n", encoding="utf-8"
    )
    row = next(b for b in load_document(path).blocks if b.kind == "table_row")
    assert row.text == "Роль аналитик | 1 знак"


def test_unsupported_format(tmp_path: Path):
    path = tmp_path / "spec.xlsx"
    path.write_bytes(b"x")
    with pytest.raises(UnsupportedFormatError):
        load_document(path)
