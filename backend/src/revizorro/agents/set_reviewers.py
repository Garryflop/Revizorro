"""Set-level agents (ISO 29148 5.2.6, IEEE 830 4.3): consistency and completeness/traceability."""

from __future__ import annotations

import asyncio

from revizorro import prompts
from revizorro.agents.context import document_section, requirements_section
from revizorro.agents.convert import set_finding
from revizorro.agents.schemas import SetReview
from revizorro.domain.criteria import SET, criteria_prompt_block
from revizorro.domain.models import Document, Finding, LinterSignal, Requirement, TestProbe
from revizorro.llm.runner import LLMRunner
from revizorro.tools.linter import signals_for_prompt

CONSISTENCY = ("set_consistent", "set_comprehensible", "set_feasible")
COMPLETENESS = ("set_complete", "traceable", "set_validatable", "ranked", "modifiable")
API_CONTRACT = ("set_consistent", "set_complete", "set_comprehensible")
API_MIN_REQUIREMENTS = 3
COVERED_KINDS = {"functional", "nonfunctional", "data", "integration", "api", "ui"}


def coverage_matrix(reqs: list[Requirement], probes: list[TestProbe] | None = None) -> list[dict]:
    """Which acceptance criteria and derivable test probes cover each requirement."""
    acceptance = [r for r in reqs if r.kind == "acceptance"]
    rows = []
    for r in reqs:
        if r.kind not in COVERED_KINDS:
            continue
        covering = [a.rid for a in acceptance if r.rid in a.traces_to]
        req_probes = [p for p in (probes or []) if p.rid == r.rid]
        rows.append(
            {
                "rid": r.rid,
                "source_id": r.source_id,
                "summary": r.summary,
                "acceptance": covering,
                "probes_total": len(req_probes),
                "probes_derivable": sum(p.derivable for p in req_probes),
            }
        )
    return rows


def coverage_text(rows: list[dict], reqs: list[Requirement]) -> str:
    lines = ["# Матрица покрытия (посчитана кодом)", ""]
    for row in rows:
        acc = ", ".join(row["acceptance"]) or "нет критериев приёмки"
        lines.append(f"- {row['rid']} ({row['source_id'] or 'без номера'}): {acc}")
    orphan = [r.rid for r in reqs if r.kind == "acceptance" and not r.traces_to]
    if orphan:
        lines.append(f"- Критерии приёмки без связи с требованиями: {', '.join(orphan)}")
    no_id = [r.rid for r in reqs if not r.source_id and r.kind not in ("business_goal",)]
    lines.append(f"- Требований без идентификатора в документе: {len(no_id)} из {len(reqs)}")
    return "\n".join(lines) + "\n"


async def review_set(
    runner: LLMRunner, doc: Document, reqs: list[Requirement], signals: list[LinterSignal]
) -> list[Finding]:
    known = {r.rid for r in reqs}
    base = document_section(doc) + "\n" + requirements_section(reqs)

    consistency_prompt = base + "\nНайди противоречия и несогласованности в наборе."
    completeness_prompt = (
        base
        + "\n"
        + coverage_text(coverage_matrix(reqs), reqs)
        + "\n# Сигналы линтера\n\n"
        + signals_for_prompt(signals)
        + "\n\nНайди пробелы и проблемы трассируемости набора."
    )

    jobs = {
        "consistency": runner.run(
            agent_name="consistency",
            role="strong",
            instructions=prompts.instructions(
                "consistency", criteria=criteria_prompt_block({k: SET[k] for k in CONSISTENCY})
            ),
            prompt=consistency_prompt,
            output_type=SetReview,
        ),
        "completeness": runner.run(
            agent_name="completeness",
            role="strong",
            instructions=prompts.instructions(
                "completeness", criteria=criteria_prompt_block({k: SET[k] for k in COMPLETENESS})
            ),
            prompt=completeness_prompt,
            output_type=SetReview,
        ),
    }
    if sum(r.kind == "api" for r in reqs) >= API_MIN_REQUIREMENTS:
        # Specialist pass: contract defects are spread over many table rows and get lost in a general review.
        jobs["api_contract"] = runner.run(
            agent_name="api_contract",
            role="strong",
            instructions=prompts.instructions(
                "api_contract", criteria=criteria_prompt_block({k: SET[k] for k in API_CONTRACT})
            ),
            prompt=base + "\nПроверь контракт API.",
            output_type=SetReview,
        )
    results = await asyncio.gather(*jobs.values())
    findings: list[Finding] = []
    for agent, res in zip(jobs, results, strict=True):
        findings += [set_finding(f, agent, known) for f in res.findings]
    return findings
