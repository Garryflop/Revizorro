"""Critic agent: rejects false positives, merges duplicates, calibrates severity."""

from __future__ import annotations

from revizorro import prompts
from revizorro.agents.context import document_section, findings_section
from revizorro.agents.schemas import CriticDecision, CriticResult
from revizorro.domain.models import SEVERITY_ORDER, Document, Finding
from revizorro.llm.runner import LLMRunner


async def critique(runner: LLMRunner, doc: Document, findings: list[Finding]) -> list[CriticDecision]:
    if not findings:
        return []
    prompt = (
        document_section(doc)
        + "\n"
        + findings_section(findings, "Замечания на перепроверку")
        + "\nПрими решение по каждому замечанию."
    )
    out = await runner.run(
        agent_name="critic",
        role="strong",
        instructions=prompts.instructions("critic"),
        prompt=prompt,
        output_type=CriticResult,
    )
    return out.decisions


MERGEABLE_ACROSS = {"conforming", "traceable"}  # formatting defects may be pooled across requirements


def merge_allowed(f: Finding, target: Finding) -> bool:
    """Guard against the critic pooling different requirements' defects into one finding."""
    if f.scope == "set":
        return True
    if f.rid == target.rid or f.criterion in MERGEABLE_ACROSS:
        return True
    if f.rid and f.rid in target.related_rids:
        return True
    return bool({loc.block_id for loc in f.locations} & {loc.block_id for loc in target.locations})


def apply_decisions(findings: list[Finding], decisions: list[CriticDecision]) -> None:
    """Mutate findings in place; unknown or missing decisions keep the finding."""
    by_id = {f.fid: f for f in findings}
    decided = {d.fid: d for d in decisions if d.fid in by_id}

    for fid, d in decided.items():
        f = by_id[fid]
        f.critic_note = d.reason
        if d.verdict == "reject":
            f.status = "rejected"
        elif d.verdict == "merge" and d.merge_into in by_id and d.merge_into != fid:
            if merge_allowed(f, by_id[d.merge_into]):
                f.status = "merged"
                f.merged_into = d.merge_into
            else:
                f.severity = d.severity
                f.critic_note = (
                    f"Критик предлагал объединить с {d.merge_into}; оставлено отдельно: другое требование."
                )
        else:
            f.severity = d.severity

    # Resolve merge chains and cycles: the final target must be kept.
    for f in findings:
        if f.status != "merged":
            continue
        seen = {f.fid}
        target = by_id[f.merged_into] if f.merged_into else None
        while (
            target is not None and target.status == "merged" and target.merged_into and target.fid not in seen
        ):
            seen.add(target.fid)
            target = by_id.get(target.merged_into)
        if target is None or target.status != "kept":
            f.status, f.merged_into = "kept", None
            continue
        f.merged_into = target.fid
        target.merged_from.append(f.fid)
        # The surviving finding carries the stronger of the two critic ratings.
        dup_severity = decided[f.fid].severity if f.fid in decided else f.severity
        if SEVERITY_ORDER[dup_severity] < SEVERITY_ORDER[target.severity]:
            target.severity = dup_severity
        known = {(loc.block_id, loc.quote) for loc in target.locations}
        for loc in f.locations:
            if (loc.block_id, loc.quote) not in known and len(target.locations) < 6:
                target.locations.append(loc)
                known.add((loc.block_id, loc.quote))
        for rid in [f.rid, *f.related_rids]:
            if rid and rid != target.rid and rid not in target.related_rids:
                target.related_rids.append(rid)
