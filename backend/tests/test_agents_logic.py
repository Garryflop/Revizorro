from revizorro.agents.clarifier import answer_text, rank_questions
from revizorro.agents.critic import apply_decisions
from revizorro.agents.schemas import (
    ClarifierResult,
    CriticDecision,
    LLMOption,
    LLMQuestion,
    Segmentation,
    SegRequirement,
)
from revizorro.agents.segmenter import postprocess
from revizorro.domain.models import Finding, Location


def _f(
    fid, rid=None, scope="requirement", severity="major", criterion="unambiguous", block="B001", related=()
):
    return Finding(
        fid=fid,
        scope=scope,
        rid=rid,
        related_rids=list(related),
        criterion=criterion,
        severity=severity,
        title=fid,
        problem="p",
        locations=[Location(block_id=block, quote="q", verified=True)],
        source_agent="reviewer",
    )


def _seg(rid, block_id, quote, **kw):
    return SegRequirement(
        rid=rid,
        source_id=kw.get("source_id"),
        source_ref="ref",
        kind=kw.get("kind", "functional"),
        summary="s",
        block_ids=[block_id],
        quote=quote,
        traces_to=kw.get("traces_to", []),
    )


def test_segmenter_renumbers_in_document_order_and_remaps_traces(small_doc):
    f1 = next(b for b in small_doc.blocks if b.text.startswith("Ф-1."))
    f2 = next(b for b in small_doc.blocks if b.text.startswith("Ф-2."))
    row = next(b for b in small_doc.blocks if b.kind == "table_row")
    out = Segmentation(
        requirements=[
            _seg("X-9", row.id, "Порог 1 000 ₸", kind="acceptance", traces_to=["X-2"]),
            _seg("X-2", f1.id, "задаёт порог от 1 000", source_id="Ф-1"),
            _seg("X-5", f2.id, "Система быстро отправляет", source_id="Ф-2"),
            _seg("X-7", "B999", "цитаты нет в документе"),
        ]
    )
    res = postprocess(small_doc, out)
    assert [r.rid for r in res.requirements] == ["R-01", "R-02", "R-03"]
    assert [r.source_id for r in res.requirements] == ["Ф-1", "Ф-2", None]
    assert res.requirements[2].traces_to == ["R-01"]
    assert any("X-7" in n for n in res.notes)
    assert res.unclassified_blocks  # paragraphs not mentioned by the segmenter


def test_critic_reject_merge_and_severity():
    a, b, c = _f("F-001", "R-01"), _f("F-002", "R-01"), _f("F-003", "R-02")
    apply_decisions(
        [a, b, c],
        [
            CriticDecision(fid="F-001", verdict="keep", severity="critical", reason=""),
            CriticDecision(
                fid="F-002", verdict="merge", merge_into="F-001", severity="major", reason="дубль"
            ),
            CriticDecision(fid="F-003", verdict="reject", severity="minor", reason="ответ в B010"),
        ],
    )
    assert a.status == "kept" and a.severity == "critical" and a.merged_from == ["F-002"]
    assert b.status == "merged" and b.merged_into == "F-001"
    assert c.status == "rejected" and c.critic_note == "ответ в B010"


def test_critic_cannot_pool_different_requirements():
    a = _f("F-001", "R-01", criterion="singular", block="B001")
    b = _f("F-002", "R-02", criterion="singular", block="B002")
    apply_decisions(
        [a, b],
        [
            CriticDecision(fid="F-001", verdict="keep", severity="minor"),
            CriticDecision(fid="F-002", verdict="merge", merge_into="F-001", severity="minor"),
        ],
    )
    assert b.status == "kept"


def test_merge_into_set_finding_is_allowed_for_related_requirement():
    req = _f("F-001", "R-01", block="B001")
    s = _f("F-002", scope="set", criterion="set_consistent", block="B005", related=["R-01", "R-02"])
    apply_decisions(
        [req, s],
        [
            CriticDecision(fid="F-001", verdict="merge", merge_into="F-002", severity="critical"),
            CriticDecision(fid="F-002", verdict="keep", severity="major"),
        ],
    )
    assert req.status == "merged" and s.severity == "critical"


def test_merge_cycle_falls_back_to_keep():
    a, b = _f("F-001", "R-01"), _f("F-002", "R-01")
    apply_decisions(
        [a, b],
        [
            CriticDecision(fid="F-001", verdict="merge", merge_into="F-002", severity="major"),
            CriticDecision(fid="F-002", verdict="merge", merge_into="F-001", severity="major"),
        ],
    )
    assert {a.status, b.status} != {"merged"}


def test_questions_ranked_by_severity_of_linked_findings():
    crit = _f("F-001", "R-01", severity="critical")
    minor = _f("F-002", "R-02", severity="minor")
    out = ClarifierResult(
        questions=[
            LLMQuestion(
                addressee="аналитик",
                question="мелкий",
                why="w",
                options=[
                    LLMOption(label="A", answer="a", consequence="c"),
                    LLMOption(label="B", answer="b", consequence="c"),
                ],
                recommended="Z",
                finding_ids=["F-002"],
                blocks_what="-",
            ),
            LLMQuestion(
                addressee="бизнес",
                question="важный",
                why="w",
                options=[
                    LLMOption(label="A", answer="a", consequence="c"),
                    LLMOption(label="B", answer="b", consequence="c"),
                ],
                recommended="A",
                finding_ids=["F-001", "F-404"],
                blocks_what="-",
            ),
        ]
    )
    qs = rank_questions(out, [crit, minor], {"R-01", "R-02"})
    assert [q.question for q in qs] == ["важный", "мелкий"]
    assert qs[0].qid == "Q-01" and qs[0].finding_ids == ["F-001"] and qs[0].rids == ["R-01"]
    assert qs[1].recommended is None  # unknown label dropped
    assert answer_text(qs[0], "a") == "Вариант A: a"
    assert answer_text(qs[0], "свой ответ") == "свой ответ"
