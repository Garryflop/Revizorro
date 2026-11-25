"""Decision-fork questions, answer-driven rewrites and re-checks of the new wording."""

from __future__ import annotations

from revizorro import prompts
from revizorro.agents.context import document_section, findings_section, requirements_section
from revizorro.agents.schemas import ClarifierResult, RecheckResult, ResolverResult
from revizorro.domain.criteria import INDIVIDUAL, criteria_prompt_block
from revizorro.domain.models import (
    Document,
    Finding,
    Question,
    QuestionOption,
    Requirement,
    Resolution,
    Rewrite,
    Unassessable,
)
from revizorro.llm.runner import LLMRunner

_WEIGHT = {"critical": 5.0, "major": 2.0, "minor": 0.5}


async def ask_questions(
    runner: LLMRunner,
    doc: Document,
    reqs: list[Requirement],
    findings: list[Finding],
    unassessable: list[Unassessable],
) -> list[Question]:
    important = [f for f in findings if f.status == "kept" and f.severity != "minor"]
    gaps = (
        "\n".join(f"- {u.rid}, {INDIVIDUAL[u.criterion].name}: {u.reason}" for u in unassessable) or "(нет)"
    )
    prompt = (
        document_section(doc)
        + "\n"
        + requirements_section(reqs)
        + "\n"
        + findings_section(important, "Подтверждённые замечания")
        + "\n# Свойства, которые нельзя оценить по тексту\n\n"
        + gaps
        + "\n\nСоставь вопросы-развилки к авторам документа."
    )
    out = await runner.run(
        agent_name="clarifier",
        role="strong",
        instructions=prompts.instructions("clarifier"),
        prompt=prompt,
        output_type=ClarifierResult,
    )
    return rank_questions(out, findings, {r.rid for r in reqs})


def rank_questions(out: ClarifierResult, findings: list[Finding], known_rids: set[str]) -> list[Question]:
    by_id = {f.fid: f for f in findings}

    def resolve(fid: str) -> Finding | None:
        f = by_id.get(fid)
        if f is not None and f.status == "merged" and f.merged_into:
            f = by_id.get(f.merged_into)
        return f if f is not None and f.status == "kept" else None

    questions: list[Question] = []
    for q in out.questions:
        linked = []
        for fid in q.finding_ids:
            f = resolve(fid)
            if f is not None and f.fid not in linked:
                linked.append(f.fid)
        rids = [r for r in q.rids if r in known_rids]
        for fid in linked:
            f = by_id[fid]
            for r in [f.rid, *f.related_rids]:
                if r and r not in rids:
                    rids.append(r)
        labels = {o.label for o in q.options}
        priority = sum(_WEIGHT[by_id[fid].severity] for fid in linked) + 0.25 * len(rids)
        questions.append(
            Question(
                qid="",
                addressee=q.addressee,
                question=q.question,
                why=q.why,
                options=[
                    QuestionOption(label=o.label, answer=o.answer, consequence=o.consequence)
                    for o in q.options
                ],
                recommended=q.recommended if q.recommended in labels else None,
                finding_ids=linked,
                rids=rids,
                blocks_what=q.blocks_what,
                priority=round(priority, 2),
            )
        )
    questions.sort(key=lambda q: -q.priority)
    for n, q in enumerate(questions, start=1):
        q.qid = f"Q-{n:02d}"
    return questions


def answer_text(q: Question, raw: str) -> str:
    """Map 'A' / 'b' / free text to the final answer text."""
    raw = raw.strip()
    for o in q.options:
        if raw.upper() == o.label.upper():
            return f"Вариант {o.label}: {o.answer}"
    return raw


async def resolve_answers(
    runner: LLMRunner,
    doc: Document,
    reqs: list[Requirement],
    findings: list[Finding],
    questions: list[Question],
    answers: dict[str, str],
) -> list[Resolution]:
    by_rid = {r.rid: r for r in reqs}
    by_fid = {f.fid: f for f in findings}
    resolutions: list[Resolution] = []

    for q in questions:
        if q.qid not in answers or not answers[q.qid].strip():
            continue
        answer = answer_text(q, answers[q.qid])
        affected = [by_rid[r] for r in q.rids if r in by_rid]
        if not affected:
            continue
        related = [by_fid[f] for f in q.finding_ids if f in by_fid]
        prompt = (
            document_section(doc)
            + "\n"
            + requirements_section(affected, "Затронутые требования")
            + "\n"
            + findings_section(related, "Замечания, к которым относится вопрос")
            + f"\n# Вопрос {q.qid}\n\n{q.question}\n\n# Ответ автора\n\n{answer}\n\n"
            + "Перепиши затронутые требования с учётом ответа."
        )
        out = await runner.run(
            agent_name="resolver",
            role="strong",
            instructions=prompts.instructions("resolver"),
            prompt=prompt,
            output_type=ResolverResult,
        )
        rewrites = [
            Rewrite(
                rid=w.rid,
                old=by_rid[w.rid].quote,
                new=w.new,
                resolved_fids=[f for f in w.resolved_fids if f in by_fid],
            )
            for w in out.rewrites
            if w.rid in by_rid
        ]
        resolutions.append(Resolution(qid=q.qid, answer=answer, rewrites=rewrites))

    all_rewrites = [w for res in resolutions for w in res.rewrites]
    if all_rewrites:
        await recheck(runner, doc, all_rewrites)
    return resolutions


async def recheck(runner: LLMRunner, doc: Document, rewrites: list[Rewrite]) -> None:
    cards = "\n".join(f"- {w.rid}\n  Было: «{w.old}»\n  Стало: «{w.new}»" for w in rewrites)
    prompt = document_section(doc) + "\n# Новые редакции\n\n" + cards + "\n\nПроверь каждую новую редакцию."
    out = await runner.run(
        agent_name="rechecker",
        role="default",
        instructions=prompts.instructions("rechecker", criteria=criteria_prompt_block(INDIVIDUAL)),
        prompt=prompt,
        output_type=RecheckResult,
    )
    by_rid: dict[str, list[Rewrite]] = {}
    for w in rewrites:
        by_rid.setdefault(w.rid, []).append(w)
    for item in out.items:
        for w in by_rid.get(item.rid, []):
            w.remaining = [
                Finding(
                    fid="",
                    scope="requirement",
                    rid=item.rid,
                    criterion=f.criterion,
                    severity=f.severity,
                    title=f.title,
                    problem=f.problem,
                    suggestion=f.suggestion,
                    locations=[],
                    source_agent="rechecker",
                )
                for f in item.findings
            ]
