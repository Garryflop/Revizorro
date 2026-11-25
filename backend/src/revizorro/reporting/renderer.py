"""Render a Report to Markdown (main), HTML, JSON, an answers template and a trace."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape
from markdown_it import MarkdownIt

from revizorro.domain.criteria import ALL
from revizorro.domain.models import (
    DECISION_RU,
    KIND_RU,
    SEVERITY_RU,
    Document,
    Finding,
    Report,
    RunPassport,
    Scenario,
)
from revizorro.reporting.view import AGENT_RU, build


def _cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _num(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def _dur(seconds: float) -> str:
    seconds = round(seconds)
    if seconds < 60:
        return f"{seconds} с"
    return f"{seconds // 60} мин {seconds % 60} с"


def _when(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    offset = dt.strftime("%z")
    tz = f"UTC{offset[:3]}:{offset[3:]}" if offset else ""
    return f"{dt:%Y-%m-%d %H:%M} {tz}".strip()


def _money(cost: float | None, p: RunPassport) -> str:
    if cost is None:
        return "н/д: цена модели неизвестна"
    text = f"${cost:.4f}" if cost < 0.01 else f"${cost:.2f}"
    if "google:" in (p.model_default + p.model_strong):
        return f"{text} по прайсу платного тарифа Gemini; на бесплатном тарифе — $0"
    if p.cached_calls == p.llm_calls and p.llm_calls:
        return f"{text} (все ответы из кэша; это стоимость исходного прогона)"
    return text


def _nodot(text: str) -> str:
    return text.strip().rstrip(".;")


def _scenario(s: Scenario) -> str:
    steps = "; ".join(f"{i}) {_nodot(step)}" for i, step in enumerate(s.steps, start=1))
    outcomes = "; ".join(f"**{_nodot(o.basis)}** → {_nodot(o.result)}" for o in s.outcomes)
    return f"Дано: {_nodot(s.preconditions)}. Шаги: {steps}. Результат: {outcomes}."


def _sections(block_ids: list[str], doc: Document) -> str:
    counts: dict[str, int] = {}
    for bid in block_ids:
        b = doc.block(bid)
        name = b.section[-1] if b and b.section else "вне разделов"
        counts[name] = counts.get(name, 0) + 1
    return ", ".join(f"«{name}» ({n})" for name, n in counts.items())


def _plural(n: int, one: str, few: str, many: str) -> str:
    """Russian plural form: 1 блок, 2 блока, 5 блоков."""
    tail = n % 100
    if 11 <= tail <= 14:
        word = many
    elif n % 10 == 1:
        word = one
    elif 2 <= n % 10 <= 4:
        word = few
    else:
        word = many
    return f"{n} {word}"


def _rids(rids: list[str], limit: int = 8) -> str:
    if len(rids) <= limit:
        return ", ".join(rids)
    return ", ".join(rids[:limit]) + f" и ещё {len(rids) - limit}"


def _refs(f: Finding) -> str:
    ids = [f.rid] if f.rid else []
    ids += [r for r in f.related_rids if r not in ids]
    return _rids(ids) if ids else "набор"


def _evidence(f: Finding) -> str:
    who = AGENT_RU.get(f.source_agent, f.source_agent)
    where = f", {f.rid}" if f.rid else ""
    return f"{f.fid} ({who}{where}): {f.title}"


def environment() -> Environment:
    env = Environment(
        loader=PackageLoader("revizorro.reporting", "templates"),
        autoescape=select_autoescape(enabled_extensions=("html.j2",), default_for_string=False),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        undefined=StrictUndefined,
    )
    env.filters.update(
        cell=_cell,
        num=_num,
        dur=_dur,
        when=_when,
        money=_money,
        scenario=_scenario,
        sections=_sections,
        rids=_rids,
        evidence=_evidence,
        plural=_plural,
        nodot=_nodot,
        refs=_refs,
        crit=lambda code: ALL[code].name if code in ALL else code,
        sev=lambda s: SEVERITY_RU.get(s, s),
        kind=lambda k: KIND_RU.get(k, k),
    )
    return env


@dataclass
class OutputPaths:
    markdown: Path
    html: Path
    json: Path
    answers: Path
    trace: Path


def output_paths(target: Path) -> OutputPaths:
    stem = target.with_suffix("")
    md = target if target.suffix.lower() in (".md", ".markdown") else stem.with_suffix(".md")
    html = target if target.suffix.lower() in (".html", ".htm") else stem.with_suffix(".html")
    js = target if target.suffix.lower() == ".json" else stem.with_suffix(".json")
    return OutputPaths(md, html, js, Path(f"{stem}.answers.yaml"), Path(f"{stem}.trace.jsonl"))


def render_markdown(report: Report, answers_file: str = "answers.yaml") -> str:
    ctx = build(report)
    ctx["decision_ru"] = DECISION_RU[report.verdict.decision]
    ctx["answers_file"] = answers_file
    text = environment().get_template("report.md.j2").render(**ctx)
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text


def render_html(report: Report, markdown: str) -> str:
    body = MarkdownIt("commonmark", {"html": False, "typographer": False}).enable("table").render(markdown)
    return (
        environment()
        .get_template("report.html.j2")
        .render(
            title=f"Ревью требований: {report.passport.document_title}",
            body=body,
            decision=report.verdict.decision,
        )
    )


def answers_template(report: Report) -> str:
    lines = [
        "# Ответы на вопросы-развилки Revizorro.",
        "# Впишите букву варианта (A, B, C…) или свой ответ текстом; пустые вопросы пропускаются.",
        "# Затем запустите проверку повторно с флагом --answers <этот файл>.",
        "",
    ]
    for q in report.questions:
        lines.append(f"# {q.qid} → {q.addressee}: {' '.join(q.question.split())}")
        for o in q.options:
            mark = " (рекомендуется)" if o.label == q.recommended else ""
            lines.append(f"#   {o.label}{mark}: {' '.join(o.answer.split())}")
        lines.append(f'{q.qid}: ""')
        lines.append("")
    return "\n".join(lines)


def write_outputs(report: Report, target: str | Path) -> OutputPaths:
    paths = output_paths(Path(target))
    paths.markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown = render_markdown(report, answers_file=paths.answers.name)
    paths.markdown.write_text(markdown, encoding="utf-8")
    paths.html.write_text(render_html(report, markdown), encoding="utf-8")
    paths.json.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    if report.questions:
        paths.answers.write_text(answers_template(report), encoding="utf-8")
    with paths.trace.open("w", encoding="utf-8") as fh:
        for rec in report.llm_calls:
            fh.write(json.dumps(rec.model_dump(), ensure_ascii=False) + "\n")
        for f in report.findings:
            if f.status != "kept":
                fh.write(
                    json.dumps(
                        {"type": "dropped_finding", "fid": f.fid, "status": f.status, "note": f.critic_note},
                        ensure_ascii=False,
                    )
                    + "\n"
                )
    return paths
