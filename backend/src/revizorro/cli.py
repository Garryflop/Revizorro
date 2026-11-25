"""Command line: `revizorro <requirements file> <report file>`."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from revizorro import __version__
from revizorro.config import load_settings, normalize_model_id
from revizorro.domain.models import DECISION_RU, Question

app = typer.Typer(add_completion=False, help="Revizorro — ИИ-агент статической проверки требований.")
console = Console(highlight=False)

STAGES = {
    "ingest": "Чтение документа",
    "segment": "Нарезка требований",
    "review": "Проверка требований, тест-дизайн, проверка набора",
    "verify": "Сверка цитат и перепроверка критиком",
    "clarify": "Вопросы-развилки",
    "resolve": "Новая редакция по ответам и повторная проверка",
    "summarize": "Итог",
}


def _on_event(event: dict[str, Any]) -> None:
    kind = event.get("type")
    if kind == "stage":
        name = STAGES.get(event["stage"], event["stage"])
        if event["status"] == "start":
            console.print(f"[bold cyan]→[/] {name}…")
        else:
            details = ", ".join(f"{k}: {v}" for k, v in event.items() if k not in ("type", "stage", "status"))
            console.print(f"  [green]✓[/] {name}" + (f" [dim]({details})[/]" if details else ""))
    elif kind == "llm_retry":
        wait = event.get("wait_s")
        console.print(
            f"  [yellow]![/] {event.get('agent')}: {event.get('reason')}"
            + (f", повтор через {wait} с" if wait is not None else ", повтор")
        )
    elif kind == "llm_fallback":
        target = event.get("to") or "запасных моделей нет"
        console.print(f"  [yellow]![/] {event['from']}: {event['reason']} → {target}")
    elif kind == "llm_done" and not event.get("cached"):
        console.print(
            f"    [dim]{event['agent']} · {event['model']} · {event['duration_s']} с · "
            f"{event['input_tokens']}→{event['output_tokens']} ток.[/]"
        )


def _ask_interactively(questions: list[Question]) -> dict[str, str]:
    console.print(
        Panel(
            "Агент подготовил вопросы-развилки. Ответьте буквой варианта или своим текстом.\n"
            "Enter — пропустить вопрос, q — закончить отвечать.",
            title="Уточнение",
        )
    )
    answers: dict[str, str] = {}
    for q in questions:
        table = Table(show_header=False, box=None, padding=(0, 1))
        for o in q.options:
            mark = " [green](рекомендуется)[/]" if o.label == q.recommended else ""
            table.add_row(f"[bold]{o.label}[/]{mark}", o.answer, f"[dim]{o.consequence}[/]")
        console.print(Panel(table, title=f"{q.qid} → {q.addressee}", subtitle=q.blocks_what, expand=True))
        console.print(f"[bold]{q.question}[/]\n[dim]{q.why}[/]")
        raw = Prompt.ask("Ответ", default="", show_default=False).strip()
        if raw.lower() in ("q", "й", "quit", "exit"):
            break
        if raw:
            answers[q.qid] = raw
    return answers


def _load_answers(path: Path) -> dict[str, str]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise typer.BadParameter("Файл ответов должен быть YAML-словарём вида Q-01: A")
    return {str(k): str(v) for k, v in data.items() if v not in (None, "")}


@app.command()
def main(
    input_file: Annotated[Path, typer.Argument(help="Документ с требованиями: .pdf, .md, .txt, .docx")],
    report_file: Annotated[
        Path, typer.Argument(help="Куда записать отчёт: .md (рядом появятся .html и .json)")
    ],
    model: Annotated[
        str | None,
        typer.Option("--model", "-m", help="Модель для массовых шагов, например google:gemini-3.5-flash"),
    ] = None,
    strong_model: Annotated[
        str | None, typer.Option("--strong-model", help="Модель для проверки набора, критика и итога")
    ] = None,
    answers: Annotated[
        Path | None, typer.Option("--answers", "-a", help="YAML с ответами на вопросы-развилки")
    ] = None,
    interactive: Annotated[
        bool, typer.Option("--interactive", "-i", help="Задать вопросы-развилки в терминале")
    ] = False,
    no_cache: Annotated[bool, typer.Option("--no-cache", help="Не использовать кэш ответов модели")] = False,
    concurrency: Annotated[int | None, typer.Option(help="Сколько запросов к модели одновременно")] = None,
    batch_size: Annotated[
        int | None, typer.Option(help="Сколько требований проверять за один запрос")
    ] = None,
    env_file: Annotated[Path | None, typer.Option(help="Путь к .env, если он не в текущей папке")] = None,
) -> None:
    """Проверить документ с требованиями и записать отчёт."""
    from revizorro.pipeline.orchestrator import run_review
    from revizorro.reporting.renderer import write_outputs

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

    settings = load_settings(env_file)
    if concurrency:
        settings.concurrency = concurrency
    if batch_size:
        settings.batch_size = batch_size
    try:
        default, strong = settings.resolve_models()
    except RuntimeError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1) from e
    if model:
        default = normalize_model_id(model)
        strong = normalize_model_id(strong_model) if strong_model else default
    elif strong_model:
        strong = normalize_model_id(strong_model)

    given_answers = _load_answers(answers) if answers else None
    console.print(f"[bold]Revizorro {__version__}[/] · {input_file} · модели: {default} / {strong}")

    try:
        report = asyncio.run(
            run_review(
                input_file,
                settings,
                model_default=default,
                model_strong=strong,
                answers=given_answers,
                ask=_ask_interactively if interactive else None,
                use_cache=not no_cache,
                on_event=_on_event,
            )
        )
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Ошибка: {e}[/]")
        raise typer.Exit(1) from e
    except RuntimeError as e:
        console.print(f"[red]Ошибка обращения к модели: {e}[/]")
        raise typer.Exit(2) from e

    paths = write_outputs(report, report_file)
    kept = report.kept()
    critical = sum(f.severity == "critical" for f in kept)
    p = report.passport
    cost = "н/д" if p.cost_usd is None else f"${p.cost_usd:.4f}"
    console.print(
        Panel(
            f"[bold]{DECISION_RU[report.verdict.decision]}[/]\n"
            f"Требований: {len(report.requirements)} · нарушений: {len(kept)} (критичных {critical}) · "
            f"вопросов: {len(report.questions)}\n"
            f"Запросов: {p.llm_calls} (из кэша {p.cached_calls}) · токены {p.input_tokens}→{p.output_tokens} · "
            f"стоимость {cost} · {p.duration_s} с\n\n"
            f"Отчёт: {paths.markdown}\nHTML: {paths.html}\nJSON: {paths.json}"
            + (f"\nШаблон ответов: {paths.answers}" if report.questions else ""),
            title="Готово",
        )
    )


if __name__ == "__main__":
    app()
