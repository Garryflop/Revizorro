"""Deterministic statistics: every number in the summary comes from here."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from revizorro.domain.criteria import ALL
from revizorro.domain.models import KIND_RU, Finding, Question, Requirement, TestProbe

CRITICAL_CRITERIA = {"verifiable", "set_consistent", "complete", "set_complete", "correct", "unambiguous"}


@dataclass
class Stats:
    requirements: int
    by_kind: dict[str, int]
    findings_kept: int
    by_severity: dict[str, int]
    by_criterion: dict[str, int]
    rejected: int
    merged: int
    unverified: int
    reqs_with_findings: int
    reqs_clean: list[str]
    probes_total: int
    probes_derivable: int
    probes_blocked: int
    questions: int
    covered_by_acceptance: int
    coverable: int
    critical: list[Finding] = field(default_factory=list)


def compute(
    reqs: list[Requirement], findings: list[Finding], probes: list[TestProbe], questions: list[Question]
) -> Stats:
    kept = [f for f in findings if f.status == "kept"]
    touched: set[str] = set()
    for f in kept:
        if f.rid:
            touched.add(f.rid)
        touched.update(f.related_rids)
    acceptance = [r for r in reqs if r.kind == "acceptance"]
    coverable = [
        r for r in reqs if r.kind in ("functional", "nonfunctional", "api", "integration", "data", "ui")
    ]
    covered = [r for r in coverable if any(r.rid in a.traces_to for a in acceptance)]
    critical = sorted(
        (f for f in kept if f.severity == "critical"),
        key=lambda f: (f.criterion not in CRITICAL_CRITERIA, f.fid),
    )
    return Stats(
        requirements=len(reqs),
        by_kind=dict(Counter(r.kind for r in reqs)),
        findings_kept=len(kept),
        by_severity={s: sum(f.severity == s for f in kept) for s in ("critical", "major", "minor")},
        by_criterion=dict(Counter(f.criterion for f in kept).most_common()),
        rejected=sum(f.status == "rejected" for f in findings),
        merged=sum(f.status == "merged" for f in findings),
        unverified=sum(f.status == "unverified" for f in findings),
        reqs_with_findings=len(touched & {r.rid for r in reqs}),
        reqs_clean=[r.rid for r in reqs if r.rid not in touched],
        probes_total=len(probes),
        probes_derivable=sum(p.derivable for p in probes),
        probes_blocked=sum(not p.derivable for p in probes),
        questions=len(questions),
        covered_by_acceptance=len(covered),
        coverable=len(coverable),
        critical=critical,
    )


def as_text(s: Stats) -> str:
    kinds = ", ".join(f"{KIND_RU.get(k, k)}: {v}" for k, v in s.by_kind.items())
    crits = ", ".join(f"{ALL[c].name if c in ALL else c}: {n}" for c, n in s.by_criterion.items())
    return "\n".join(
        [
            f"- Требований: {s.requirements} ({kinds})",
            f"- Подтверждённых нарушений: {s.findings_kept} (критично {s.by_severity['critical']}, "
            f"существенно {s.by_severity['major']}, незначительно {s.by_severity['minor']})",
            f"- Нарушения по свойствам: {crits or 'нет'}",
            f"- Требований с нарушениями: {s.reqs_with_findings} из {s.requirements}",
            f"- Пробных тест-кейсов: {s.probes_total}, из них ожидаемый результат выводится для "
            f"{s.probes_derivable}, не выводится для {s.probes_blocked}",
            f"- Требований, покрытых критериями приёмки: {s.covered_by_acceptance} из {s.coverable}",
            f"- Вопросов к авторам: {s.questions}",
        ]
    )
