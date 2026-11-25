"""Structured outputs the LLM agents must return. Field descriptions are part of the prompt."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from revizorro.domain.criteria import IndividualCriterion, SetCriterion
from revizorro.domain.models import RequirementKind, Severity

# ---------- shared ----------


class LLMLocation(BaseModel):
    block_id: str = Field(description="Якорь блока документа, например B024")
    quote: str = Field(
        description="Дословная цитата из этого блока: непрерывный фрагмент 5–25 слов, скопированный символ в символ"
    )


class LLMOutcome(BaseModel):
    basis: str = Field(description="Основание: пункт или трактовка, например «по Ф-3» или «трактовка 1»")
    result: str = Field(description="Что произойдёт при этом основании, с конкретными значениями")


class LLMScenario(BaseModel):
    preconditions: str = Field(description="Исходные данные с конкретными числами, датами, состоянием")
    steps: list[str] = Field(description="Шаги сценария по порядку")
    outcomes: list[LLMOutcome] = Field(description="Два и более расходящихся результата")


# ---------- segmentation ----------


class SegRequirement(BaseModel):
    rid: str = Field(description="Идентификатор в отчёте: R-01, R-02… по порядку появления в документе")
    source_id: str | None = Field(
        description="Идентификатор из документа, например «Ф-2»; null, если его нет"
    )
    source_ref: str = Field(
        description="Где в документе, человеческим языком: раздел и пункт или строка таблицы"
    )
    kind: RequirementKind
    summary: str = Field(description="Краткая формулировка своими словами, до 15 слов")
    block_ids: list[str] = Field(description="Блоки, из которых состоит требование (обычно один)")
    quote: str = Field(description="Дословная цитата ключевой фразы требования из первого блока, до 40 слов")
    traces_to: list[str] = Field(
        default_factory=list,
        description="rid требований, которые это требование проверяет, уточняет или реализует",
    )


class Segmentation(BaseModel):
    requirements: list[SegRequirement]
    context_blocks: list[str] = Field(
        default_factory=list,
        description="Блоки без требований, но с полезным контекстом (паспорт, пояснения)",
    )
    template_blocks: list[str] = Field(
        default_factory=list, description="Пустые или незаполненные элементы шаблона, чек-листы, согласования"
    )


# ---------- per-requirement review ----------


class LLMFinding(BaseModel):
    criterion: IndividualCriterion
    severity: Severity
    title: str = Field(description="Суть дефекта, до 12 слов")
    problem: str = Field(description="Что именно не так, со ссылкой на текст")
    impact: str = Field(description="Чем это помешает разработчику или тестировщику")
    suggestion: str = Field(description="Конкретная новая формулировка или точный список того, что дописать")
    locations: list[LLMLocation] = Field(min_length=1)
    counterexample: LLMScenario | None = Field(
        default=None, description="Для двусмысленности обязательно: сценарий и расходящиеся трактовки"
    )


class LLMUnassessable(BaseModel):
    criterion: IndividualCriterion
    reason: str = Field(description="Какого знания не хватает, чтобы оценить свойство")


class RequirementAssessment(BaseModel):
    rid: str
    findings: list[LLMFinding] = Field(default_factory=list)
    unassessable: list[LLMUnassessable] = Field(default_factory=list)


class ReviewBatch(BaseModel):
    assessments: list[RequirementAssessment] = Field(
        description="По одной записи на каждое требование из списка"
    )


# ---------- test design ----------

Technique = Literal["boundary", "equivalence", "decision_table", "state_transition", "negative", "scenario"]


class LLMProbe(BaseModel):
    technique: Technique
    title: str = Field(description="Название тест-кейса")
    preconditions: str = Field(description="Исходные данные с конкретными значениями")
    steps: list[str]
    expected: str = Field(
        description="Ожидаемый результат, выведенный только из документа; при derivable=false — какие варианты допускает текст"
    )
    derivable: bool = Field(description="Можно ли однозначно вывести ожидаемый результат из документа")
    blocker: str = Field(
        default="", description="При derivable=false: чего именно не хватает или что противоречит"
    )
    fix: str = Field(
        default="", description="При derivable=false: что дописать в требование, чтобы тест стал однозначным"
    )
    anchor: LLMLocation | None = Field(
        default=None, description="При derivable=false: место в документе, где не хватает информации"
    )


class RequirementProbes(BaseModel):
    rid: str
    probes: list[LLMProbe] = Field(default_factory=list)


class ProbeBatch(BaseModel):
    items: list[RequirementProbes] = Field(description="По одной записи на каждое требование из списка")


# ---------- set review ----------


class LLMSetFinding(BaseModel):
    criterion: SetCriterion
    severity: Severity
    rids: list[str] = Field(description="Все требования, которых касается замечание")
    title: str = Field(description="Суть дефекта, до 12 слов")
    problem: str
    impact: str
    suggestion: str
    locations: list[LLMLocation] = Field(min_length=1, description="Все места, участвующие в дефекте")
    counterexample: LLMScenario | None = Field(
        default=None, description="Для противоречий и пробелов в поведении обязательно"
    )


class SetReview(BaseModel):
    findings: list[LLMSetFinding] = Field(default_factory=list)


# ---------- critic ----------


class CriticDecision(BaseModel):
    fid: str
    verdict: Literal["keep", "reject", "merge"]
    merge_into: str | None = Field(default=None, description="При merge: fid замечания, которое остаётся")
    severity: Severity
    reason: str = Field(
        default="", description="Одно предложение; для reject обязательно, со ссылкой на блок"
    )


class CriticResult(BaseModel):
    decisions: list[CriticDecision]


# ---------- clarifier ----------


class LLMOption(BaseModel):
    label: str = Field(description="A, B, C…")
    answer: str = Field(description="Формулировка решения")
    consequence: str = Field(
        description="Что изменится: какие требования переписать (rid), какие тесты, риски"
    )


class LLMQuestion(BaseModel):
    addressee: str = Field(description="Кому задать: роль")
    question: str
    why: str = Field(description="Почему вопрос возник, со ссылками на rid")
    options: list[LLMOption] = Field(min_length=2, max_length=4)
    recommended: str | None = Field(default=None, description="label рекомендуемого варианта")
    finding_ids: list[str] = Field(default_factory=list, description="fid замечаний, которые закрывает ответ")
    rids: list[str] = Field(default_factory=list, description="Затронутые требования")
    blocks_what: str = Field(description="Что блокирует отсутствие ответа")


class ClarifierResult(BaseModel):
    questions: list[LLMQuestion]


# ---------- resolver ----------


class LLMRewrite(BaseModel):
    rid: str
    new: str = Field(description="Новая редакция требования целиком, готовая для вставки в документ")
    resolved_fids: list[str] = Field(
        default_factory=list, description="fid замечаний, которые закрывает редакция"
    )


class ResolverResult(BaseModel):
    rewrites: list[LLMRewrite]


class RecheckFinding(BaseModel):
    criterion: IndividualCriterion
    severity: Severity
    title: str
    problem: str
    suggestion: str


class RecheckItem(BaseModel):
    rid: str
    findings: list[RecheckFinding] = Field(default_factory=list)


class RecheckResult(BaseModel):
    items: list[RecheckItem]


# ---------- summary ----------


class LLMFix(BaseModel):
    action: str = Field(description="Конкретное действие")
    refs: list[str] = Field(default_factory=list, description="fid, rid, qid")


class SummaryResult(BaseModel):
    decision: Literal["ready", "ready_after_fixes", "not_ready"]
    development: str
    testing: str
    rationale: str
    first_fixes: list[LLMFix]
    can_start_now: list[str] = Field(default_factory=list)
