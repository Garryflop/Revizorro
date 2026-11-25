"""The review pipeline: ingestion → segmentation → parallel reviews → verification → questions → verdict."""

from __future__ import annotations

import asyncio
import subprocess
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from revizorro import __version__, prompts
from revizorro.agents.clarifier import ask_questions, resolve_answers
from revizorro.agents.critic import apply_decisions, critique
from revizorro.agents.reviewers import design_tests, review_requirements
from revizorro.agents.segmenter import segment
from revizorro.agents.set_reviewers import review_set
from revizorro.agents.summarizer import summarize
from revizorro.config import REPO_ROOT, Settings
from revizorro.domain.models import Document, Finding, Question, Report, RunPassport
from revizorro.ingestion import load_document
from revizorro.llm.runner import EventSink, LLMRunner
from revizorro.pipeline import stats as st
from revizorro.tools.linter import lint, rule_findings
from revizorro.tools.quotes import verify_quote

AskFn = Callable[[list[Question]], dict[str, str]]


def agent_version() -> str:
    try:
        out = subprocess.run(
            ["git", "describe", "--tags", "--always", "--dirty"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            return f"{out.stdout.strip()} (revizorro {__version__})"
    except (OSError, subprocess.SubprocessError):
        pass
    return f"revizorro {__version__} (без git)"


def verify_locations(doc: Document, findings: list[Finding]) -> None:
    """Code-level anchor check: a finding without a confirmed quote never reaches the report."""
    for f in findings:
        verified = []
        for loc in f.locations:
            m = verify_quote(doc, loc.block_id, loc.quote)
            if m.ok:
                loc.block_id, loc.quote, loc.verified = m.block_id, m.quote, True
                loc.label = doc.location_label(m.block_id)
                verified.append(loc)
        f.locations = verified
        if not verified:
            f.status = "unverified"


def number_findings(findings: list[Finding], rid_order: dict[str, int]) -> list[Finding]:
    agent_rank = {
        "reviewer": 0,
        "test_designer": 1,
        "consistency": 2,
        "api_contract": 3,
        "completeness": 4,
        "linter": 5,
    }
    findings.sort(
        key=lambda f: (
            f.scope == "set",
            rid_order.get(f.rid or "", 10_000),
            agent_rank.get(f.source_agent, 9),
        )
    )
    width = 3 if len(findings) < 1000 else 4
    for n, f in enumerate(findings, start=1):
        f.fid = f"F-{n:0{width}d}"
    return findings


async def run_review(
    input_path: str | Path,
    settings: Settings,
    *,
    model_default: str,
    model_strong: str,
    answers: dict[str, str] | None = None,
    ask: AskFn | None = None,
    use_cache: bool = True,
    on_event: EventSink | None = None,
) -> Report:
    emit = on_event or (lambda _e: None)
    started = time.perf_counter()
    started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    runner = LLMRunner(settings, model_default, model_strong, use_cache=use_cache, on_event=emit)

    def stage(name: str, status: str, **extra: Any) -> None:
        emit({"type": "stage", "stage": name, "status": status, **extra})

    stage("ingest", "start")
    doc = load_document(input_path)
    signals = lint(doc)
    stage("ingest", "done", blocks=len(doc.blocks), signals=len(signals), format=doc.source_format)

    stage("segment", "start")
    seg = await segment(runner, doc)
    reqs = seg.requirements
    stage("segment", "done", requirements=len(reqs), unclassified=len(seg.unclassified_blocks))

    batch = settings.batch_for(model_default)
    stage("review", "start", requirements=len(reqs), batch=batch)
    review_task = review_requirements(runner, doc, reqs, signals, batch)
    tests_task = design_tests(runner, doc, reqs, batch)
    set_task = review_set(runner, doc, reqs, signals)
    review, tests, set_findings = await asyncio.gather(review_task, tests_task, set_task)
    stage("review", "done", findings=len(review.findings) + len(tests.findings) + len(set_findings))

    stage("verify", "start")
    rid_order = {r.rid: i for i, r in enumerate(reqs)}
    rules = rule_findings(doc, signals, reqs)
    findings = number_findings([*review.findings, *tests.findings, *set_findings, *rules], rid_order)
    verify_locations(doc, findings)
    candidates = [f for f in findings if f.status == "kept"]
    decisions = await critique(runner, doc, candidates)
    apply_decisions(candidates, decisions)
    kept = [f for f in findings if f.status == "kept"]
    stage(
        "verify",
        "done",
        kept=len(kept),
        rejected=sum(f.status == "rejected" for f in findings),
        merged=sum(f.status == "merged" for f in findings),
        unverified=sum(f.status == "unverified" for f in findings),
    )

    stage("clarify", "start")
    questions = await ask_questions(runner, doc, reqs, findings, review.unassessable)
    stage("clarify", "done", questions=len(questions))

    collected = dict(answers or {})
    if ask is not None and questions:
        collected.update(ask(questions))
    resolutions = []
    if collected:
        stage("resolve", "start", answers=len(collected))
        resolutions = await resolve_answers(runner, doc, reqs, findings, questions, collected)
        stage("resolve", "done", rewrites=sum(len(r.rewrites) for r in resolutions))

    stage("summarize", "start")
    stats = st.compute(reqs, findings, tests.probes, questions)
    verdict = await summarize(runner, doc.title, reqs, findings, questions, st.as_text(stats))
    stage("summarize", "done", decision=verdict.decision)

    records = runner.records
    costs = [r.cost_usd for r in records]  # cached calls carry the cost of the run that produced them
    passport = RunPassport(
        document_title=doc.title,
        source_file=Path(doc.source_path).name,
        source_format=doc.source_format,
        sha256=doc.sha256,
        started_at=started_at,
        duration_s=round(time.perf_counter() - started, 1),
        model_default=model_default,
        model_strong=model_strong,
        models_used=sorted({r.model for r in records}),
        agent_version=agent_version(),
        prompts_version=prompts.version(),
        llm_calls=len(records),
        cached_calls=sum(r.cached for r in records),
        input_tokens=sum(r.input_tokens for r in records),
        output_tokens=sum(r.output_tokens for r in records),
        cost_usd=None if any(c is None for c in costs) else round(sum(c or 0.0 for c in costs), 4),
    )
    return Report(
        passport=passport,
        document=doc,
        requirements=reqs,
        context_blocks=seg.context_blocks,
        template_blocks=seg.template_blocks,
        unclassified_blocks=seg.unclassified_blocks,
        segmentation_notes=seg.notes,
        findings=findings,
        unassessable=review.unassessable,
        probes=tests.probes,
        questions=questions,
        resolutions=resolutions,
        verdict=verdict,
        linter=signals,
        llm_calls=records,
    )
