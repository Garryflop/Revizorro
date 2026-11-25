"""Segmenter agent: builds the requirement registry; code validates anchors, quotes and coverage."""

from __future__ import annotations

from dataclasses import dataclass, field

from revizorro import prompts
from revizorro.agents.context import document_section, requirements_section
from revizorro.agents.schemas import Segmentation
from revizorro.domain.models import Document, Requirement
from revizorro.llm.runner import LLMRunner
from revizorro.tools.quotes import verify_quote

STRUCTURAL = ("heading", "table_header")  # never requirements on their own


@dataclass
class SegmentationOutcome:
    requirements: list[Requirement]
    context_blocks: list[str]
    template_blocks: list[str]
    unclassified_blocks: list[str]
    notes: list[str] = field(default_factory=list)


async def segment(runner: LLMRunner, doc: Document) -> SegmentationOutcome:
    out = await runner.run(
        agent_name="segmenter",
        role="strong",  # every later step depends on the registry, so it gets the stronger model
        instructions=prompts.instructions("segmenter"),
        prompt=document_section(doc) + "\nВыдели все требования этого документа.",
        output_type=Segmentation,
    )
    outcome = postprocess(doc, out)
    if not outcome.unclassified_blocks:
        return outcome

    # Coverage control: blocks the first pass skipped get a second, focused pass.
    leftover = outcome.unclassified_blocks
    listing = "\n".join(f"[{b}] {doc.block(b).text}" for b in leftover if doc.block(b))  # type: ignore[union-attr]
    repair = await runner.run(
        agent_name="segmenter_repair",
        role="strong",
        instructions=prompts.instructions("segmenter"),
        prompt=document_section(doc)
        + "\n"
        + requirements_section(outcome.requirements, "Уже выделенные требования")
        + "\n# Блоки без классификации\n\n"
        + listing
        + "\n\nЭти блоки остались без классификации после первого прохода. Классифицируй только их: "
        "если блок содержит требование (в том числе критерий приёмки), добавь его в `requirements` "
        "с идентификатором N-01, N-02…; иначе отнеси блок к `context_blocks` или `template_blocks`. "
        "В `traces_to` ссылайся на идентификаторы уже выделенных требований.",
        output_type=Segmentation,
    )
    return merge(doc, outcome, repair)


def _build(
    doc: Document, out: Segmentation, notes: list[str], only_blocks: set[str] | None = None
) -> list[Requirement]:
    """Validate anchors and quotes; requirement ids stay as the model gave them."""
    order = {b.id: i for i, b in enumerate(doc.blocks)}
    reqs: list[Requirement] = []
    for raw in out.requirements:
        block_ids = [b for b in raw.block_ids if b in order]
        quote = raw.quote.strip()
        match = verify_quote(doc, block_ids[0] if block_ids else "", quote)
        if match.ok and match.block_id not in block_ids:
            block_ids.insert(0, match.block_id)
        if only_blocks is not None:
            block_ids = [b for b in block_ids if b in only_blocks]
        if not block_ids:
            notes.append(f"{raw.rid}: не удалось привязать к документу, пропущено")
            continue
        if not match.ok or match.block_id not in block_ids:
            first = doc.block(block_ids[0])
            quote = first.text if first and len(first.text) <= 300 else quote
            notes.append(f"{raw.rid}: цитата заменена текстом блока {block_ids[0]}")
        elif not match.exact:
            quote = match.quote
        reqs.append(
            Requirement(
                rid=raw.rid,
                source_id=(raw.source_id or None),
                source_ref=raw.source_ref,
                kind=raw.kind,
                summary=raw.summary,
                quote=quote,
                block_ids=sorted(set(block_ids), key=order.__getitem__),
                traces_to=raw.traces_to,
            )
        )
    return reqs


def _renumber(doc: Document, reqs: list[Requirement]) -> list[Requirement]:
    """Sort by position in the document, assign R-01…, remap trace links."""
    order = {b.id: i for i, b in enumerate(doc.blocks)}
    indexed = sorted(enumerate(reqs), key=lambda p: (order[p[1].block_ids[0]], p[0]))
    width = 2 if len(reqs) < 100 else 3
    remap: dict[str, str] = {}
    for n, (_, req) in enumerate(indexed, start=1):
        new = f"R-{n:0{width}d}"
        remap.setdefault(req.rid, new)
        req.rid = new
    result = [req for _, req in indexed]
    for req in result:
        req.traces_to = sorted({remap[t] for t in req.traces_to if t in remap and remap[t] != req.rid})
    return result


def _finalize(
    doc: Document, reqs: list[Requirement], context: list[str], template: list[str], notes: list[str]
) -> SegmentationOutcome:
    known = {b.id for b in doc.blocks}
    used = {b for r in reqs for b in r.block_ids}
    context = list(dict.fromkeys(b for b in context if b in known and b not in used))
    template = list(dict.fromkeys(b for b in template if b in known and b not in used and b not in context))
    classified = used | set(context) | set(template)
    unclassified = [b.id for b in doc.blocks if b.kind not in STRUCTURAL and b.id not in classified]
    return SegmentationOutcome(reqs, context, template, unclassified, notes)


def postprocess(doc: Document, out: Segmentation) -> SegmentationOutcome:
    notes: list[str] = []
    reqs = _renumber(doc, _build(doc, out, notes))
    return _finalize(doc, reqs, out.context_blocks, out.template_blocks, notes)


def merge(doc: Document, first: SegmentationOutcome, repair: Segmentation) -> SegmentationOutcome:
    """Add requirements found by the repair pass; they may only claim the leftover blocks."""
    leftover = set(first.unclassified_blocks)
    notes = list(first.notes)
    extra = _build(doc, repair, notes, only_blocks=leftover)
    existing = {r.rid for r in first.requirements}
    for n, req in enumerate(extra, start=1):
        req.traces_to = [t for t in req.traces_to if t in existing]
        req.rid = f"N-{n:03d}"
    if extra:
        notes.append(f"Повторный проход нарезки добавил требований: {len(extra)}")
    reqs = _renumber(doc, [*first.requirements, *extra])
    context = [*first.context_blocks, *(b for b in repair.context_blocks if b in leftover)]
    template = [*first.template_blocks, *(b for b in repair.template_blocks if b in leftover)]
    return _finalize(doc, reqs, context, template, notes)
