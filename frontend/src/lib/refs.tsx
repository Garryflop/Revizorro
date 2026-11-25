import { Tooltip } from "antd";
import { createContext, useContext, type ReactNode } from "react";
import type { Block, Finding, Meta, Question, Requirement } from "../types";

// Everything a reference (R-07, F-057, Q-08, B030) needs to explain itself and to open its target.
export interface RefApi {
  meta: Meta;
  reqs: Map<string, Requirement>;
  findings: Map<string, Finding>;
  questions: Map<string, Question>;
  blocks: Map<string, Block>;
  openRequirement: (rid: string) => void;
  openFinding: (fid: string) => void;
  openQuestion: (qid: string) => void;
  openBlock: (blockId: string, quote?: string) => void;
}

export const RefContext = createContext<RefApi | null>(null);

export function useRefs(): RefApi {
  const api = useContext(RefContext);
  if (!api) throw new Error("RefContext is missing");
  return api;
}

// A merged finding points to the one that stayed in the report; follow the chain.
export function resolveFinding(fid: string, findings: Map<string, Finding>): Finding | null {
  let f = findings.get(fid);
  for (let i = 0; f && f.status === "merged" && f.merged_into && i < 10; i += 1) f = findings.get(f.merged_into);
  return f && f.status === "kept" ? f : null;
}

interface Target {
  kind: "req" | "finding" | "question" | "block";
  label: ReactNode;
  hint: ReactNode;
  tone?: string;
  open: () => void;
}

const clip = (s: string, n = 180) => (s.length > n ? `${s.slice(0, n).trimEnd()}…` : s);

function describe(id: string, api: RefApi, inline?: boolean): Target | null {
  if (id.startsWith("R-")) {
    const r = api.reqs.get(id);
    if (!r) return null;
    return {
      kind: "req",
      label: (
        <>
          {id}
          {!inline && r.source_id && <span className="ref-src">{r.source_id}</span>}
        </>
      ),
      hint: (
        <>
          <b>
            Требование {id}
            {r.source_id && ` (${r.source_id})`}
          </b>
          <br />
          {clip(r.summary)}
        </>
      ),
      open: () => api.openRequirement(id),
    };
  }
  if (id.startsWith("F-")) {
    const f = resolveFinding(id, api.findings);
    if (!f) return null;
    return {
      kind: "finding",
      label: id,
      tone: `tone-${f.severity}`,
      hint: (
        <>
          <b>
            Замечание {f.fid}, {api.meta.severity[f.severity]}
          </b>
          {f.fid !== id && <> (сюда вошло {id})</>}
          <br />
          {clip(f.title)}
        </>
      ),
      open: () => api.openFinding(f.fid),
    };
  }
  if (id.startsWith("Q-")) {
    const q = api.questions.get(id);
    if (!q) return null;
    return {
      kind: "question",
      label: id,
      hint: (
        <>
          <b>Вопрос {id}</b>
          <br />
          {clip(q.question)}
        </>
      ),
      open: () => api.openQuestion(id),
    };
  }
  const b = api.blocks.get(id);
  if (!b) return null;
  return {
    kind: "block",
    label: id,
    hint: (
      <>
        <b>Фрагмент документа</b>
        {b.section.length > 0 && <>, {b.section[b.section.length - 1]}</>}
        <br />
        {clip(b.text, 140)}
      </>
    ),
    open: () => api.openBlock(id),
  };
}

// Clickable reference. `inline` renders it as a link inside prose, otherwise as a chip.
export function Ref({ id, inline }: { id: string; inline?: boolean }) {
  const api = useRefs();
  const t = describe(id, api, inline);
  if (!t) return <span className="ref-dead">{id}</span>;
  return (
    <Tooltip title={t.hint} mouseEnterDelay={0.2}>
      <button
        type="button"
        className={["ref", `ref-${t.kind}`, inline ? "ref-inline" : "ref-chip", t.tone].filter(Boolean).join(" ")}
        onClick={(e) => {
          e.stopPropagation();
          t.open();
        }}
      >
        {t.label}
      </button>
    </Tooltip>
  );
}

export function RefList({ ids, max = 6 }: { ids: string[]; max?: number }) {
  const unique = [...new Set(ids)];
  const shown = unique.slice(0, max);
  const rest = unique.slice(max);
  return (
    <span className="ref-list">
      {shown.map((id) => (
        <Ref key={id} id={id} />
      ))}
      {rest.length > 0 && (
        <Tooltip title={rest.join(", ")}>
          <span className="ref-more">ещё {rest.length}</span>
        </Tooltip>
      )}
    </span>
  );
}

const REF_RE = /\b([RFQ]-\d{2,3}|B\d{3})\b/g;

// Prose from the agents with every R-/F-/Q-/B-identifier turned into a clickable reference.
export function RichText({ text }: { text: string }) {
  const parts = text.split(REF_RE);
  return <>{parts.map((p, i) => (i % 2 ? <Ref key={i} id={p} inline /> : p))}</>;
}
