from pathlib import Path

import pytest

from revizorro.config import REPO_ROOT
from revizorro.domain.models import Document
from revizorro.ingestion import load_document

EXAMPLE = REPO_ROOT / "examples" / "requirements.md"

SMALL_MD = """# Тестовый документ

## Функциональные требования

* **Ф-1.** Пользователь задаёт порог от 1 000 до 5 000 ₸ включительно.
* **Ф-2.** Система быстро отправляет уведомление.

## Критерии приемки

| Условие | Результат |
| :--- | :--- |
| Порог 1 000 ₸ | Сохранено |
| | |

## Пустой раздел

## Данные

Хранить сумму в тиынах и порог в тенге.
"""


@pytest.fixture
def small_doc(tmp_path: Path) -> Document:
    path = tmp_path / "small.md"
    path.write_text(SMALL_MD, encoding="utf-8")
    return load_document(path)


@pytest.fixture
def example_doc() -> Document:
    return load_document(EXAMPLE)
