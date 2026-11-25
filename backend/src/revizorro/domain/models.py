"""Core domain models shared by ingestion, agents, pipeline and reporting."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, PrivateAttr

Severity = Literal["critical", "major", "minor"]
SEVERITY_ORDER: dict[str, int] = {"critical": 0, "major": 1, "minor": 2}
SEVERITY_RU: dict[str, str] = {"critical": "критично", "major": "существенно", "minor": "незначительно"}

RequirementKind = Literal[
    "business_goal",
    "functional",
    "ui",
    "process",
    "nonfunctional",
    "data",
    "integration",
    "api",
    "acceptance",
    "constraint",
]
KIND_RU: dict[str, str] = {
    "business_goal": "бизнес-цель",
    "functional": "функциональное",
    "ui": "интерфейс",
    "process": "процесс",
    "nonfunctional": "нефункциональное",
    "data": "данные",
    "integration": "интеграция",
    "api": "API",
    "acceptance": "критерий приёмки",
    "constraint": "ограничение",
}

BlockKind = Literal["heading", "paragraph", "list_item", "table_header", "table_row", "code"]


# ---------- Document ----------


class Block(BaseModel):
    id: str
    kind: BlockKind
    text: str
    section: list[str] = Field(default_factory=list)
    line_start: int
    line_end: int
    page: int | None = None
    heading_level: int | None = None
    table_header: list[str] | None = None


class Document(BaseModel):
    title: str
    source_path: str
    source_format: str
    sha256: str
    markdown: str
    blocks: list[Block]
    _block_index: dict[str, Block] | None = PrivateAttr(default=None)

    def block(self, block_id: str) -> Block | None:
        return self._index().get(block_id)

    def _index(self) -> dict[str, Block]:
        if self._block_index is None:
            self._block_index = {b.id: b for b in self.blocks}
        return self._block_index

    def location_label(self, block_id: str) -> str:
        """Human-readable place in the document: section path, page, line."""
        b = self.block(block_id)
        if b is None:
            return block_id
        parts: list[str] = []
        if b.section:
            parts.append(" › ".join(b.section[-2:]))
        if b.kind == "table_row":
            parts.append("строка таблицы")
        if b.page is not None:
            parts.append(f"стр. {b.page}")
        parts.append(
            f"строка {b.line_start}" if b.line_start == b.line_end else f"строки {b.line_start}–{b.line_end}"
        )
        return ", ".join(parts)

    def render_for_llm(self) -> str:
        """Block-tagged text: the only view of the document that agents get."""
        lines: list[str] = []
        for b in self.blocks:
            if b.kind == "heading":
                lines.append(f"[{b.id}] {'#' * (b.heading_level or 1)} {b.text}")
            elif b.kind == "table_header":
                lines.append(f"[{b.id}] (заголовок таблицы) {b.text}")
            elif b.kind == "table_row":
                lines.append(f"[{b.id}] (строка таблицы) {b.text}")
            elif b.kind == "list_item":
                lines.append(f"[{b.id}] • {b.text}")
            elif b.kind == "code":
                lines.append(f"[{b.id}] (код) {b.text}")
            else:
                lines.append(f"[{b.id}] {b.text}")
        return "\n".join(lines)


# ---------- Requirements and findings ----------


class Requirement(BaseModel):
    rid: str
    source_id: str | None = None
    source_ref: str
    kind: RequirementKind
    summary: str
    quote: str
    block_ids: list[str]
    traces_to: list[str] = Field(default_factory=list)


class Location(BaseModel):
    block_id: str
    quote: str
    verified: bool = False
    label: str = ""


class Outcome(BaseModel):
    basis: str
    result: str


class Scenario(BaseModel):
    preconditions: str
    steps: list[str]
    outcomes: list[Outcome]


FindingStatus = Literal["kept", "rejected", "merged", "unverified"]


class Finding(BaseModel):
    fid: str
    scope: Literal["requirement", "set"]
    rid: str | None = None
    related_rids: list[str] = Field(default_factory=list)
    criterion: str
    severity: Severity
    title: str
    problem: str
    impact: str = ""
    suggestion: str = ""
    locations: list[Location]
    counterexample: Scenario | None = None
    source_agent: str
    status: FindingStatus = "kept"
    critic_note: str = ""
    merged_into: str | None = None
    merged_from: list[str] = Field(default_factory=list)


class Unassessable(BaseModel):
    rid: str
    criterion: str
    reason: str


class TestProbe(BaseModel):
    rid: str
    technique: str
    title: str
    preconditions: str
    steps: list[str]
    expected: str
    derivable: bool
    blocker: str = ""


class QuestionOption(BaseModel):
    label: str
    answer: str
    consequence: str


class Question(BaseModel):
    qid: str
    addressee: str
    question: str
    why: str
    options: list[QuestionOption]
    recommended: str | None = None
    finding_ids: list[str] = Field(default_factory=list)
    rids: list[str] = Field(default_factory=list)
    blocks_what: str = ""
    priority: float = 0.0


class Rewrite(BaseModel):
    rid: str
    old: str
    new: str
    resolved_fids: list[str] = Field(default_factory=list)
    remaining: list[Finding] = Field(default_factory=list)


class Resolution(BaseModel):
    qid: str
    answer: str
    rewrites: list[Rewrite]


class FixItem(BaseModel):
    action: str
    refs: list[str] = Field(default_factory=list)


class Verdict(BaseModel):
    decision: Literal["ready", "ready_after_fixes", "not_ready"]
    development: str
    testing: str
    rationale: str
    first_fixes: list[FixItem]
    can_start_now: list[str] = Field(default_factory=list)


DECISION_RU: dict[str, str] = {
    "ready": "Можно начинать разработку и тестирование",
    "ready_after_fixes": "Можно начинать после исправления перечисленных дефектов",
    "not_ready": "Начинать разработку и тестирование нельзя",
}


class LinterSignal(BaseModel):
    block_id: str
    rule: str
    message: str
    fragment: str


# ---------- Run ----------


class LLMCallRecord(BaseModel):
    agent: str
    model: str
    cached: bool
    duration_s: float
    input_tokens: int
    output_tokens: int
    cost_usd: float | None
    attempts: int = 1


class RunPassport(BaseModel):
    document_title: str
    source_file: str
    source_format: str
    sha256: str
    started_at: str
    duration_s: float
    model_default: str
    model_strong: str
    models_used: list[str] = Field(default_factory=list)
    agent_version: str
    prompts_version: str
    llm_calls: int
    cached_calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float | None


class Report(BaseModel):
    passport: RunPassport
    document: Document
    requirements: list[Requirement]
    context_blocks: list[str] = Field(default_factory=list)
    template_blocks: list[str] = Field(default_factory=list)
    unclassified_blocks: list[str] = Field(default_factory=list)
    segmentation_notes: list[str] = Field(default_factory=list)
    findings: list[Finding]
    unassessable: list[Unassessable] = Field(default_factory=list)
    probes: list[TestProbe] = Field(default_factory=list)
    questions: list[Question] = Field(default_factory=list)
    resolutions: list[Resolution] = Field(default_factory=list)
    verdict: Verdict
    linter: list[LinterSignal] = Field(default_factory=list)
    llm_calls: list[LLMCallRecord] = Field(default_factory=list)

    def kept(self) -> list[Finding]:
        return [f for f in self.findings if f.status == "kept"]
