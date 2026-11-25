"""Prompt fragments shared by agents. The document always goes first so providers can cache the prefix."""

from __future__ import annotations

from revizorro.domain.criteria import ALL
from revizorro.domain.models import KIND_RU, SEVERITY_RU, Document, Finding, Question, Requirement


def document_section(doc: Document) -> str:
    return f"# Документ «{doc.title}»\n\n{doc.render_for_llm()}\n"


def requirement_card(r: Requirement) -> str:
    src = r.source_id or "без номера"
    traces = f" | связано с: {', '.join(r.traces_to)}" if r.traces_to else ""
    return (
        f"- {r.rid} | в документе: {src} | {KIND_RU.get(r.kind, r.kind)} | блоки: {', '.join(r.block_ids)}"
        f" | {r.source_ref}{traces}\n  Суть: {r.summary}\n  Цитата: «{r.quote}»"
    )


def requirements_section(reqs: list[Requirement], title: str = "Реестр требований") -> str:
    return f"# {title}\n\n" + "\n".join(requirement_card(r) for r in reqs) + "\n"


def finding_line(f: Finding, with_details: bool = True) -> str:
    crit = ALL.get(f.criterion)
    crit_name = crit.name if crit else f.criterion
    refs = f.rid or ", ".join(f.related_rids) or "набор"
    locs = "; ".join(f"[{loc.block_id}] «{loc.quote}»" for loc in f.locations)
    text = f"- {f.fid} | {refs} | {crit_name} | {SEVERITY_RU[f.severity]} | {f.title}\n  Места: {locs}"
    if with_details:
        text += f"\n  Проблема: {f.problem}"
        if f.suggestion:
            text += f"\n  Предложение: {f.suggestion}"
        if f.counterexample:
            ce = f.counterexample
            outcomes = "; ".join(f"{o.basis}: {o.result}" for o in ce.outcomes)
            text += f"\n  Контрпример: {ce.preconditions} → {' → '.join(ce.steps)} ⇒ {outcomes}"
    return text


def findings_section(findings: list[Finding], title: str = "Замечания") -> str:
    if not findings:
        return f"# {title}\n\n(нет)\n"
    return f"# {title}\n\n" + "\n".join(finding_line(f) for f in findings) + "\n"


def question_line(q: Question) -> str:
    return f"- {q.qid} → {q.addressee}: {q.question} (закрывает: {', '.join(q.finding_ids) or '—'})"
