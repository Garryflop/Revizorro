import type { Finding, Meta, Requirement } from "../types";

const AGENT: Record<string, string> = {
  reviewer: "ревьюер требований",
  test_designer: "тест-дизайнер",
  consistency: "ревьюер согласованности",
  completeness: "ревьюер полноты",
  api_contract: "ревьюер контракта API",
};

export function reqLabel(rid: string, reqs: Map<string, Requirement>): string {
  const r = reqs.get(rid);
  return r?.source_id ? `${rid} (${r.source_id})` : rid;
}

interface Props {
  f: Finding;
  meta: Meta;
  reqs: Map<string, Requirement>;
  byId: Map<string, Finding>;
  open: boolean;
  onToggle: () => void;
  onLocate: (blockId: string, quote: string) => void;
}

export function FindingItem({ f, meta, reqs, byId, open, onToggle, onLocate }: Props) {
  const refs = [f.rid, ...f.related_rids].filter((r): r is string => !!r);
  const evidence = f.merged_from.map((id) => byId.get(id)).filter((x): x is Finding => !!x);
  return (
    <div className="finding">
      <button className="head" aria-expanded={open} onClick={onToggle}>
        <span className={`sev ${f.severity}`}>{meta.severity[f.severity]}</span>
        <span className="title">{f.title}</span>
        <span className="sub">
          {f.fid}, {meta.criteria[f.criterion]?.name ?? f.criterion}
          {refs.length > 0 && `, ${refs.slice(0, 4).map((r) => reqLabel(r, reqs)).join(", ")}${refs.length > 4 ? ` и ещё ${refs.length - 4}` : ""}`}
        </span>
      </button>
      {open && (
        <div className="body">
          {f.locations.map((loc, i) => (
            <div key={i} className="quote">
              <button className="link" onClick={() => onLocate(loc.block_id, loc.quote)}>
                «{loc.quote}»
              </button>
              <div className="muted">{loc.label}</div>
            </div>
          ))}
          <p>{f.problem}</p>
          {f.impact && (
            <p>
              <b>Последствия.</b> {f.impact}
            </p>
          )}
          {f.counterexample && (
            <div className="counter">
              <b>Контрпример.</b> {f.counterexample.preconditions}
              <ol>
                {f.counterexample.steps.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ol>
              <div className="outcomes">
                {f.counterexample.outcomes.map((o, i) => (
                  <div key={i}>
                    <b>{o.basis}</b>
                    <span>{o.result}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
          {f.suggestion && (
            <p>
              <b>Как исправить.</b> {f.suggestion}
            </p>
          )}
          {evidence.length > 0 && (
            <p className="muted">
              Независимо подтверждают:{" "}
              {evidence.map((e) => `${e.fid} (${AGENT[e.source_agent] ?? e.source_agent})`).join(", ")}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
