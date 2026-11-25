"""Summary agent: readiness verdict and first fixes. Numbers come from code, not the model."""

from __future__ import annotations

from revizorro import prompts
from revizorro.agents.context import finding_line, question_line, requirements_section
from revizorro.agents.schemas import SummaryResult
from revizorro.domain.models import Finding, FixItem, Question, Requirement, Verdict
from revizorro.llm.runner import LLMRunner


async def summarize(
    runner: LLMRunner,
    title: str,
    reqs: list[Requirement],
    findings: list[Finding],
    questions: list[Question],
    stats_text: str,
) -> Verdict:
    kept = [f for f in findings if f.status == "kept"]
    important = [f for f in kept if f.severity in ("critical", "major")]
    prompt = (
        f"# Документ «{title}»\n\n"
        + requirements_section(reqs)
        + "\n# Статистика\n\n"
        + stats_text
        + "\n\n# Критичные и существенные замечания\n\n"
        + ("\n".join(finding_line(f, with_details=False) for f in important) or "(нет)")
        + "\n\n# Вопросы к авторам\n\n"
        + ("\n".join(question_line(q) for q in questions) or "(нет)")
        + "\n\nСформулируй итог ревью."
    )
    out = await runner.run(
        agent_name="summarizer",
        role="strong",
        instructions=prompts.instructions("summarizer"),
        prompt=prompt,
        output_type=SummaryResult,
    )
    decision = out.decision
    if decision == "ready" and any(f.severity == "critical" for f in kept):
        decision = "ready_after_fixes"  # hard rule: critical defects rule out "ready"
    return Verdict(
        decision=decision,
        development=humanize(out.development),
        testing=humanize(out.testing),
        rationale=humanize(out.rationale),
        first_fixes=[FixItem(action=humanize(x.action), refs=x.refs) for x in out.first_fixes],
        can_start_now=[humanize(x) for x in out.can_start_now],
    )


_CODES = {
    "ready_after_fixes": "начинать можно после исправлений",
    "not_ready": "начинать нельзя",
}


def humanize(text: str) -> str:
    """Replace enum codes the model sometimes leaks into prose."""
    for code, phrase in _CODES.items():
        text = text.replace(f"`{code}`", phrase).replace(code, phrase)
    return text
