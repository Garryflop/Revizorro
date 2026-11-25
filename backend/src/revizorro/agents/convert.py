"""Convert LLM outputs into domain objects (ids are assigned later by the pipeline)."""

from __future__ import annotations

from revizorro.agents.schemas import LLMFinding, LLMLocation, LLMScenario, LLMSetFinding
from revizorro.domain.models import Finding, Location, Outcome, Scenario


def location(loc: LLMLocation) -> Location:
    return Location(block_id=loc.block_id.strip().strip("[]"), quote=loc.quote.strip())


def scenario(s: LLMScenario | None) -> Scenario | None:
    if s is None or not s.outcomes:
        return None
    return Scenario(
        preconditions=s.preconditions,
        steps=s.steps,
        outcomes=[Outcome(basis=o.basis, result=o.result) for o in s.outcomes],
    )


def requirement_finding(rid: str, f: LLMFinding, agent: str) -> Finding:
    return Finding(
        fid="",
        scope="requirement",
        rid=rid,
        criterion=f.criterion,
        severity=f.severity,
        title=f.title,
        problem=f.problem,
        impact=f.impact,
        suggestion=f.suggestion,
        locations=[location(loc) for loc in f.locations],
        counterexample=scenario(f.counterexample),
        source_agent=agent,
    )


def set_finding(f: LLMSetFinding, agent: str, known_rids: set[str]) -> Finding:
    return Finding(
        fid="",
        scope="set",
        related_rids=[r for r in f.rids if r in known_rids],
        criterion=f.criterion,
        severity=f.severity,
        title=f.title,
        problem=f.problem,
        impact=f.impact,
        suggestion=f.suggestion,
        locations=[location(loc) for loc in f.locations],
        counterexample=scenario(f.counterexample),
        source_agent=agent,
    )
