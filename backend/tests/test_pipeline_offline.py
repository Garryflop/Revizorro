"""End-to-end pipeline run with canned model outputs: no network, no tokens."""

import asyncio
import json
from pathlib import Path

import pytest

from revizorro.agents import schemas as s
from revizorro.config import Settings
from revizorro.llm.runner import LLMRunner
from revizorro.pipeline.orchestrator import run_review
from revizorro.reporting.renderer import write_outputs
from tests.conftest import SMALL_MD


def _canned(doc_blocks):
    f1 = next(b for b in doc_blocks if b.text.startswith("Ф-1."))
    f2 = next(b for b in doc_blocks if b.text.startswith("Ф-2."))
    row = next(b for b in doc_blocks if b.kind == "table_row")
    data = next(b for b in doc_blocks if b.text.startswith("Хранить"))
    loc2 = s.LLMLocation(block_id=f2.id, quote="Система быстро отправляет уведомление")
    return {
        "segmenter": s.Segmentation(
            requirements=[
                s.SegRequirement(
                    rid="R-01",
                    source_id="Ф-1",
                    source_ref="п. 1",
                    kind="functional",
                    summary="Порог",
                    block_ids=[f1.id],
                    quote="задаёт порог от 1 000 до 5 000 ₸",
                ),
                s.SegRequirement(
                    rid="R-02",
                    source_id="Ф-2",
                    source_ref="п. 2",
                    kind="functional",
                    summary="Push",
                    block_ids=[f2.id],
                    quote="Система быстро отправляет уведомление",
                ),
                s.SegRequirement(
                    rid="R-03",
                    source_id=None,
                    source_ref="Критерии",
                    kind="acceptance",
                    summary="КП",
                    block_ids=[row.id],
                    quote="Порог 1 000 ₸",
                    traces_to=["R-01"],
                ),
            ]
        ),
        # Repair pass: the data paragraph becomes a requirement, the rest stays unclassified.
        "segmenter_repair": s.Segmentation(
            requirements=[
                s.SegRequirement(
                    rid="N-01",
                    source_id=None,
                    source_ref="Данные",
                    kind="data",
                    summary="Хранение",
                    block_ids=[data.id],
                    quote="Хранить сумму в тиынах",
                )
            ]
        ),
        "reviewer": s.ReviewBatch(
            assessments=[
                s.RequirementAssessment(
                    rid="R-02",
                    findings=[
                        s.LLMFinding(
                            criterion="verifiable",
                            severity="major",
                            title="Нет измеримого срока",
                            problem="«быстро» не измеримо",
                            impact="нет теста",
                            suggestion="не позднее 5 с",
                            locations=[loc2],
                        )
                    ],
                )
            ]
        ),
        "test_designer": s.ProbeBatch(
            items=[
                s.RequirementProbes(
                    rid="R-02",
                    probes=[
                        s.LLMProbe(
                            technique="boundary",
                            title="Срок отправки",
                            preconditions="порог достигнут",
                            steps=["провести покупку"],
                            expected="неизвестно",
                            derivable=False,
                            blocker="нет срока",
                            fix="указать срок",
                            anchor=loc2,
                        )
                    ],
                ),
                s.RequirementProbes(
                    rid="R-01",
                    probes=[
                        s.LLMProbe(
                            technique="boundary",
                            title="Граница 1 000",
                            preconditions="-",
                            steps=["ввести 1 000"],
                            expected="сохранено",
                            derivable=True,
                        )
                    ],
                ),
            ]
        ),
        "consistency": s.SetReview(
            findings=[
                s.LLMSetFinding(
                    criterion="set_consistent",
                    severity="critical",
                    rids=["R-01", "R-02"],
                    title="Конфликт",
                    problem="p",
                    impact="i",
                    suggestion="x",
                    locations=[s.LLMLocation(block_id=f1.id, quote="задаёт порог"), loc2],
                    counterexample=s.LLMScenario(
                        preconditions="порог 1 000",
                        steps=["покупка"],
                        outcomes=[
                            s.LLMOutcome(basis="по Ф-1", result="A"),
                            s.LLMOutcome(basis="по Ф-2", result="B"),
                        ],
                    ),
                )
            ]
        ),
        "completeness": s.SetReview(
            findings=[
                s.LLMSetFinding(
                    criterion="set_complete",
                    severity="major",
                    rids=[],
                    title="Выдумка",
                    problem="p",
                    impact="i",
                    suggestion="x",
                    locations=[s.LLMLocation(block_id=f1.id, quote="этой фразы нет в документе")],
                )
            ]
        ),
        "critic": s.CriticResult(
            decisions=[
                s.CriticDecision(fid="F-001", verdict="keep", severity="major"),
                s.CriticDecision(fid="F-002", verdict="merge", merge_into="F-001", severity="major"),
                s.CriticDecision(fid="F-003", verdict="keep", severity="critical"),
            ]
        ),
        "clarifier": s.ClarifierResult(
            questions=[
                s.LLMQuestion(
                    addressee="бизнес-владелец",
                    question="Какой срок отправки?",
                    why="R-02 неизмеримо",
                    options=[
                        s.LLMOption(label="A", answer="5 секунд", consequence="переписать R-02"),
                        s.LLMOption(label="B", answer="1 минута", consequence="переписать R-02"),
                    ],
                    recommended="A",
                    finding_ids=["F-001"],
                    rids=["R-02"],
                    blocks_what="тест R-02",
                )
            ]
        ),
        "resolver": s.ResolverResult(
            rewrites=[
                s.LLMRewrite(
                    rid="R-02",
                    new="Ф-2. Система должна отправить уведомление не позднее 5 с.",
                    resolved_fids=["F-001"],
                )
            ]
        ),
        "rechecker": s.RecheckResult(items=[s.RecheckItem(rid="R-02", findings=[])]),
        "summarizer": s.SummaryResult(
            decision="ready",
            development="d",
            testing="t",
            rationale="r",
            first_fixes=[s.LLMFix(action="исправить", refs=["F-003"])],
        ),
    }


@pytest.fixture
def fake_llm(monkeypatch, small_doc):
    canned = _canned(small_doc.blocks)
    calls: list[str] = []

    async def fake_run(self, *, agent_name, role, instructions, prompt, output_type):
        calls.append(agent_name)
        assert "[B001]" in prompt or agent_name == "summarizer"
        out = canned[agent_name]
        assert isinstance(out, output_type)
        self._record(agent_name, self.model_ids[role], False, 0.1, 100, 50, 0.001, 1)
        return out.model_copy(deep=True)

    monkeypatch.setattr(LLMRunner, "run", fake_run)
    return calls


def test_offline_pipeline_end_to_end(tmp_path: Path, fake_llm):
    src = tmp_path / "small.md"
    src.write_text(SMALL_MD, encoding="utf-8")
    settings = Settings(OPENAI_API_KEY="sk-test", REVIZORRO_CACHE_DIR=str(tmp_path / "cache"))
    report = asyncio.run(
        run_review(src, settings, model_default="test:x", model_strong="test:y", answers={"Q-01": "A"})
    )

    by_id = {f.fid: f for f in report.findings}
    assert by_id["F-001"].status == "kept" and by_id["F-001"].merged_from == ["F-002"]
    assert by_id["F-004"].status == "unverified"  # invented quote never reaches the report
    assert report.verdict.decision == "ready_after_fixes"  # critical finding forbids "ready"
    assert report.questions[0].qid == "Q-01"
    assert report.resolutions[0].rewrites[0].rid == "R-02"
    assert {"segmenter", "segmenter_repair", "reviewer", "critic", "resolver", "rechecker"} <= set(fake_llm)
    assert [r.kind for r in report.requirements] == ["functional", "functional", "acceptance", "data"]
    assert report.requirements[3].rid == "R-04"  # added by the repair pass, numbered in document order

    paths = write_outputs(report, tmp_path / "out" / "report.md")
    md = paths.markdown.read_text(encoding="utf-8")
    for heading in (
        "## 1. Паспорт прогона",
        "## 2. Как агент нарезал требования",
        "## 3. Проверка каждого требования",
        "## 4. Проверка всего набора требований",
        "## 5. Сводка",
        "## 6. Итог",
        "## 7. Вопросы к авторам документа",
        "## 8. Уточнения и новая редакция",
    ):
        assert heading in md
    assert "«Система быстро отправляет уведомление»" in md
    assert "Подтверждают: F-002" in md
    assert "4 требования" in md
    html = paths.html.read_text(encoding="utf-8")
    assert html.startswith("<!doctype html>")
    assert 'id="R-02"' in html and 'href="#R-02"' in html  # references jump to the requirement card
    assert json.loads(paths.json.read_text(encoding="utf-8"))["passport"]["llm_calls"] == len(fake_llm)
    assert "Q-01:" in paths.answers.read_text(encoding="utf-8")


def test_saved_report_opens_in_api_without_model_calls(tmp_path: Path, fake_llm):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from revizorro.api.app import app

    src = tmp_path / "small.md"
    src.write_text(SMALL_MD, encoding="utf-8")
    settings = Settings(OPENAI_API_KEY="sk-test", REVIZORRO_CACHE_DIR=str(tmp_path / "cache"))
    report = asyncio.run(run_review(src, settings, model_default="test:x", model_strong="test:y"))
    paths = write_outputs(report, tmp_path / "out" / "report.md")
    calls = len(fake_llm)

    client = TestClient(app)
    run = client.post(
        "/api/runs", files={"file": ("report.json", paths.json.read_bytes(), "application/json")}
    )
    assert run.status_code == 200 and run.json()["status"] == "done"
    opened = client.get(f"/api/runs/{run.json()['id']}/report").json()
    assert len(opened["requirements"]) == len(report.requirements)
    assert len(fake_llm) == calls  # nothing was sent to the model

    wrong = client.post("/api/runs", files={"file": ("report.json", b'{"hello": 1}', "application/json")})
    assert wrong.status_code == 422
