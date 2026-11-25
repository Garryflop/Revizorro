"""Segmenter agent: builds the requirement registry; code validates anchors, quotes and coverage."""

from __future__ import annotations

from dataclasses import dataclass, field

from revizorro import prompts
from revizorro.agents.context import document_section
from revizorro.agents.schemas import Segmentation
from revizorro.domain.models import Document, Requirement
from revizorro.llm.runner import LLMRunner
from revizorro.tools.quotes import verify_quote


@dataclass
class SegmentationOutcome:
    requirements: list[Requirement]
    context_blocks: list[str]
    template_blocks: list[str]
    unclassified_blocks: list[str]
    notes: list[str] = field(default_factory=list)


async def segment(runner: LLMRunner, doc: Document) -> SegmentationOutcome:
    prompt = document_section(doc) + "\nВыдели все требования этого документа."
    out = await runner.run(
        agent_name="segmenter",
        role="default",
        instructions=prompts.instructions("segmenter"),
        prompt=prompt,
        output_type=Segmentation,
    )
    return postprocess(doc, out)


def postprocess(doc: Document, out: Segmentation) -> SegmentationOutcome:
    notes: list[str] = []
    order = {b.id: i for i, b in enumerate(doc.blocks)}
    drafts: list[tuple[int, str, Requirement]] = []

    for raw in out.requirements:
        block_ids = [b for b in raw.block_ids if b in order]
        quote = raw.quote.strip()
        match = verify_quote(doc, block_ids[0] if block_ids else "", quote)
        if match.ok and match.block_id not in block_ids:
            block_ids.insert(0, match.block_id)
        if not block_ids:
            notes.append(f"{raw.rid}: не удалось привязать к документу, пропущено")
            continue
        if not match.ok:
            first = doc.block(block_ids[0])
            quote = first.text if first and len(first.text) <= 300 else quote
            notes.append(f"{raw.rid}: цитата заменена текстом блока {block_ids[0]}")
        elif not match.exact:
            quote = match.quote
        req = Requirement(
            rid=raw.rid,
            source_id=(raw.source_id or None),
            source_ref=raw.source_ref,
            kind=raw.kind,
            summary=raw.summary,
            quote=quote,
            block_ids=sorted(set(block_ids), key=order.__getitem__),
            traces_to=raw.traces_to,
        )
        drafts.append((order[req.block_ids[0]], raw.rid, req))

    # Renumber in document order and remap trace links.
    drafts.sort(key=lambda d: d[0])
    width = 2 if len(drafts) < 100 else 3
    remap: dict[str, str] = {}
    for n, (_, old, req) in enumerate(drafts, start=1):
        new = f"R-{n:0{width}d}"
        remap.setdefault(old, new)
        req.rid = new
    requirements = [req for _, _, req in drafts]
    for req in requirements:
        req.traces_to = sorted({remap[t] for t in req.traces_to if t in remap and remap[t] != req.rid})

    used = {b for r in requirements for b in r.block_ids}
    context = [b for b in out.context_blocks if b in order and b not in used]
    template = [b for b in out.template_blocks if b in order and b not in used and b not in context]
    classified = used | set(context) | set(template)
    unclassified = [b.id for b in doc.blocks if b.kind != "heading" and b.id not in classified]
    return SegmentationOutcome(requirements, context, template, unclassified, notes)
