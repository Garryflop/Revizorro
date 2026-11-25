import { AimOutlined, DownOutlined } from "@ant-design/icons";
import { Button, Tooltip } from "antd";
import { AGENT } from "../lib/labels";
import { Ref, RefList, RichText, useRefs } from "../lib/refs";
import type { Finding } from "../types";
import { SevTag } from "./Severity";

interface Props {
  f: Finding;
  open: boolean;
  questionIds: string[]; // questions whose answer removes this finding
  canLocate: boolean;
  onToggle: () => void;
  onLocate: (blockId: string, quote: string) => void;
}

export function FindingCard({ f, open, questionIds, canLocate, onToggle, onLocate }: Props) {
  const { meta, findings } = useRefs();
  const refs = [f.rid, ...f.related_rids].filter((r): r is string => !!r);
  const criterion = meta.criteria[f.criterion];
  const evidence = f.merged_from.map((id) => findings.get(id)).filter((x): x is Finding => !!x);
  // Merged findings often cite the same place twice: drop a quote that is part of a longer one in the same block.
  const locations = f.locations.filter(
    (a, i) =>
      !f.locations.some(
        (b, j) => j !== i && b.block_id === a.block_id && b.quote.includes(a.quote) && (b.quote.length > a.quote.length || j < i),
      ),
  );

  return (
    <article id={`fnd-${f.fid}`} className={`fcard sev-${f.severity}${open ? " open" : ""}`}>
      <button type="button" className="fcard-head" aria-expanded={open} onClick={onToggle}>
        <SevTag s={f.severity} meta={meta} />
        <span className="fcard-title">{f.title}</span>
        <DownOutlined className="fcard-chevron" />
      </button>

      <div className="fcard-meta">
        <span className="fcard-id">{f.fid}</span>
        <Tooltip
          title={
            criterion ? (
              <>
                <b>{criterion.source}</b>
                {criterion.violation && (
                  <>
                    <br />
                    Нарушение: {criterion.violation}
                  </>
                )}
              </>
            ) : undefined
          }
        >
          <span className="term">{criterion?.name ?? f.criterion}</span>
        </Tooltip>
        {refs.length > 0 && <RefList ids={refs} max={open ? 20 : 4} />}
      </div>

      {open && (
        <div className="fcard-body">
          <section>
            <h4>Где в документе</h4>
            {locations.map((loc, i) => (
              <div key={i} className="quote">
                <div className="quote-text">«{loc.quote}»</div>
                <div className="quote-foot">
                  <span className="muted">{loc.label}</span>
                  {canLocate && (
                    <Tooltip title="Показать в документе">
                      <Button
                        size="small"
                        type="text"
                        icon={<AimOutlined />}
                        aria-label="Показать в документе"
                        onClick={() => onLocate(loc.block_id, loc.quote)}
                      />
                    </Tooltip>
                  )}
                </div>
              </div>
            ))}
          </section>

          <section>
            <h4>В чём проблема</h4>
            <p>
              <RichText text={f.problem} />
            </p>
          </section>

          {f.impact && (
            <section>
              <h4>К чему приведёт</h4>
              <p>
                <RichText text={f.impact} />
              </p>
            </section>
          )}

          {f.counterexample && (
            <section className="counter">
              <h4>Контрпример</h4>
              <p>
                <RichText text={f.counterexample.preconditions} />
              </p>
              <ol>
                {f.counterexample.steps.map((s, i) => (
                  <li key={i}>
                    <RichText text={s} />
                  </li>
                ))}
              </ol>
              <table className="outcomes">
                <thead>
                  <tr>
                    <th>Если следовать</th>
                    <th>Получится</th>
                  </tr>
                </thead>
                <tbody>
                  {f.counterexample.outcomes.map((o, i) => (
                    <tr key={i}>
                      <td>
                        <RichText text={o.basis} />
                      </td>
                      <td>
                        <RichText text={o.result} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}

          {f.suggestion && (
            <section className="fix">
              <h4>Как исправить</h4>
              <p>
                <RichText text={f.suggestion} />
              </p>
            </section>
          )}

          {questionIds.length > 0 && (
            <section>
              <h4>Снимается ответом на вопрос</h4>
              <span className="ref-list">
                {questionIds.map((q) => (
                  <Ref key={q} id={q} />
                ))}
              </span>
            </section>
          )}

          <p className="fcard-source muted">
            Нашёл: {AGENT[f.source_agent] ?? f.source_agent}.
            {evidence.length > 0 &&
              ` Независимо подтвердили: ${[...new Set(evidence.map((e) => AGENT[e.source_agent] ?? e.source_agent))].join(", ")} (${evidence.length}).`}
          </p>
        </div>
      )}
    </article>
  );
}
