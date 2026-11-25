"""Per-requirement agents: quality reviewer (ISO 29148 5.2.5) and test designer."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field

from revizorro import prompts
from revizorro.agents.context import document_section, requirements_section
from revizorro.agents.convert import location, requirement_finding
from revizorro.agents.schemas import ProbeBatch, ReviewBatch
from revizorro.domain.criteria import INDIVIDUAL, criteria_prompt_block
from revizorro.domain.models import (
    Document,
    Finding,
    LinterSignal,
    Location,
    Requirement,
    TestProbe,
    Unassessable,
)
from revizorro.llm.runner import LLMRunner
from revizorro.tools.linter import signals_for_prompt


def batches(items: Sequence[Requirement], size: int) -> list[list[Requirement]]:
    return [list(items[i : i + size]) for i in range(0, len(items), size)]


@dataclass
class ReviewOutcome:
    findings: list[Finding] = field(default_factory=list)
    unassessable: list[Unassessable] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


async def _review_batch(
    runner: LLMRunner, doc: Document, batch: list[Requirement], signals: list[LinterSignal]
) -> ReviewBatch:
    blocks = {b for r in batch for b in r.block_ids}
    prompt = (
        document_section(doc)
        + "\n"
        + requirements_section(batch, "Требования на проверку")
        + "\n# Сигналы линтера по этим блокам\n\n"
        + signals_for_prompt(signals, blocks)
        + "\n\nПроверь каждое требование из списка."
    )
    return await runner.run(
        agent_name="reviewer",
        role="default",
        instructions=prompts.instructions("reviewer", criteria=criteria_prompt_block(INDIVIDUAL)),
        prompt=prompt,
        output_type=ReviewBatch,
    )


async def review_requirements(
    runner: LLMRunner, doc: Document, reqs: list[Requirement], signals: list[LinterSignal], batch_size: int
) -> ReviewOutcome:
    outcome = ReviewOutcome()
    by_rid = {r.rid: r for r in reqs}
    results = await asyncio.gather(
        *(_review_batch(runner, doc, b, signals) for b in batches(reqs, batch_size))
    )
    seen: set[str] = set()
    for res in results:
        for a in res.assessments:
            if a.rid not in by_rid or a.rid in seen:
                continue
            seen.add(a.rid)
            outcome.findings.extend(requirement_finding(a.rid, f, "reviewer") for f in a.findings)
            outcome.unassessable.extend(
                Unassessable(rid=a.rid, criterion=u.criterion, reason=u.reason) for u in a.unassessable
            )
    outcome.missing = [r.rid for r in reqs if r.rid not in seen]
    return outcome


@dataclass
class ProbeOutcome:
    probes: list[TestProbe] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)


TESTABLE_KINDS = {
    "functional",
    "ui",
    "process",
    "nonfunctional",
    "data",
    "integration",
    "api",
    "acceptance",
    "constraint",
}


async def design_tests(
    runner: LLMRunner, doc: Document, reqs: list[Requirement], batch_size: int
) -> ProbeOutcome:
    targets = [r for r in reqs if r.kind in TESTABLE_KINDS]
    by_rid = {r.rid: r for r in targets}

    async def one(batch: list[Requirement]) -> ProbeBatch:
        prompt = (
            document_section(doc)
            + "\n"
            + requirements_section(batch, "Требования для тест-дизайна")
            + "\nНапиши пробные тест-кейсы для каждого требования из списка."
        )
        return await runner.run(
            agent_name="test_designer",
            role="default",
            instructions=prompts.instructions("test_designer"),
            prompt=prompt,
            output_type=ProbeBatch,
        )

    outcome = ProbeOutcome()
    results = await asyncio.gather(*(one(b) for b in batches(targets, batch_size)))
    for res in results:
        for item in res.items:
            req = by_rid.get(item.rid)
            if req is None:
                continue
            for p in item.probes[:3]:
                outcome.probes.append(
                    TestProbe(
                        rid=item.rid,
                        technique=p.technique,
                        title=p.title,
                        preconditions=p.preconditions,
                        steps=p.steps,
                        expected=p.expected,
                        derivable=p.derivable,
                        blocker=p.blocker,
                    )
                )
                if p.derivable or not p.blocker:
                    continue
                anchor = location(p.anchor) if p.anchor else None
                if anchor is None:
                    anchor = location_from_requirement(req)
                outcome.findings.append(
                    Finding(
                        fid="",
                        scope="requirement",
                        rid=item.rid,
                        criterion="verifiable",
                        severity="major",
                        title=f"Тест «{p.title}» нельзя довести до ожидаемого результата",
                        problem=p.blocker,
                        impact="Тестировщик не сможет определить ожидаемый результат; допустимы варианты: "
                        + p.expected,
                        suggestion=p.fix,
                        locations=[anchor],
                        source_agent="test_designer",
                    )
                )
    return outcome


def location_from_requirement(req: Requirement) -> Location:
    return Location(block_id=req.block_ids[0], quote=req.quote)
