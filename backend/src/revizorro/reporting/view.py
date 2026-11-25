"""Precomputed view of a Report for templates: grouping, matrices, statuses."""

from __future__ import annotations

from dataclasses import dataclass, field

from revizorro.agents.set_reviewers import coverage_matrix
from revizorro.domain.criteria import ALL, INDIVIDUAL, SET
from revizorro.domain.models import SEVERITY_ORDER, Finding, Report, Requirement, TestProbe, Unassessable
from revizorro.pipeline import stats as st

SHORT = {
    "necessary": "Необх.",
    "appropriate": "Уровень",
    "unambiguous": "Однозн.",
    "complete": "Полн.",
    "singular": "Атом.",
    "feasible": "Реализ.",
    "verifiable": "Провер.",
    "correct": "Корр.",
    "conforming": "Шаблон",
}

TECHNIQUE_RU = {
    "boundary": "граничные значения",
    "equivalence": "классы эквивалентности",
    "decision_table": "таблица решений",
    "state_transition": "переходы состояний",
    "negative": "негативный",
    "scenario": "сценарий",
}

AGENT_RU = {
    "reviewer": "ревьюер требований",
    "test_designer": "тест-дизайнер",
    "consistency": "ревьюер согласованности",
    "completeness": "ревьюер полноты",
    "api_contract": "ревьюер контракта API",
    "linter": "линтер (правила)",
    "rechecker": "повторная проверка",
}


@dataclass
class RequirementView:
    req: Requirement
    findings: list[Finding]
    set_refs: list[Finding]
    unassessable: list[Unassessable]
    probes: list[TestProbe]
    matrix: dict[str, str] = field(default_factory=dict)


@dataclass
class SetCriterionView:
    code: str
    name: str
    source: str
    status: str
    count: int


def _cell(findings: list[Finding], unassessable: bool) -> str:
    if findings:
        worst = min(findings, key=lambda f: SEVERITY_ORDER[f.severity])
        return "‼" if worst.severity == "critical" else "✗"
    return "?" if unassessable else "✓"


def build(report: Report) -> dict:
    kept = report.kept()
    stats = st.compute(report.requirements, report.findings, report.probes, report.questions)

    req_views: list[RequirementView] = []
    for r in report.requirements:
        own = sorted(
            (f for f in kept if f.scope == "requirement" and f.rid == r.rid),
            key=lambda f: (SEVERITY_ORDER[f.severity], f.fid),
        )
        refs = [f for f in kept if f.scope == "set" and r.rid in f.related_rids]
        ua = [u for u in report.unassessable if u.rid == r.rid]
        view = RequirementView(r, own, refs, ua, [p for p in report.probes if p.rid == r.rid])
        for code in INDIVIDUAL:
            view.matrix[code] = _cell(
                [f for f in own if f.criterion == code], any(u.criterion == code for u in ua)
            )
        view.matrix["set"] = _cell(refs, False)  # worst set-level finding touching this requirement
        req_views.append(view)

    set_findings = sorted(
        (f for f in kept if f.scope == "set"), key=lambda f: (SEVERITY_ORDER[f.severity], f.fid)
    )
    set_criteria = []
    for code, info in SET.items():
        items = [f for f in set_findings if f.criterion == code]
        set_criteria.append(SetCriterionView(code, info.name, info.source, _cell(items, False), len(items)))

    critical_groups: dict[str, list[Finding]] = {
        "Непроверяемые": [],
        "Противоречивые": [],
        "Неполные": [],
        "Прочие критичные": [],
    }
    for f in stats.critical:
        if f.criterion == "verifiable":
            critical_groups["Непроверяемые"].append(f)
        elif f.criterion in ("set_consistent", "correct", "set_feasible"):
            critical_groups["Противоречивые"].append(f)
        elif f.criterion in ("complete", "set_complete"):
            critical_groups["Неполные"].append(f)
        else:
            critical_groups["Прочие критичные"].append(f)

    by_id = {f.fid: f for f in report.findings}
    req_by_id = {r.rid: r for r in report.requirements}
    raw_total = len(report.findings)
    after_quotes = raw_total - stats.unverified
    return {
        "r": report,
        "p": report.passport,
        "doc": report.document,
        "stats": stats,
        "reqs": req_views,
        "req_by_id": req_by_id,
        "set_findings": set_findings,
        "set_criteria": set_criteria,
        "coverage": coverage_matrix(report.requirements, report.probes),
        "critical_groups": {k: v for k, v in critical_groups.items() if v},
        "short": SHORT,
        "individual": INDIVIDUAL,
        "criteria": ALL,
        "technique_ru": TECHNIQUE_RU,
        "agent_ru": AGENT_RU,
        "by_id": by_id,
        "dropped": [f for f in report.findings if f.status in ("rejected", "merged", "unverified")],
        "funnel": {
            "raw": raw_total,
            "after_quotes": after_quotes,
            "rejected": stats.rejected,
            "merged": stats.merged,
            "kept": stats.findings_kept,
        },
        "has_api": any(c.agent == "api_contract" for c in report.llm_calls),
        "context_blocks": report.context_blocks,
        "template_blocks": report.template_blocks,
        "unclassified_blocks": report.unclassified_blocks,
    }
