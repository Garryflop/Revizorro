import { AimOutlined, CheckCircleFilled, CloseCircleFilled } from "@ant-design/icons";
import { Button, Collapse, Drawer, Empty, Tag } from "antd";
import { SEV_RANK, TECHNIQUE } from "../lib/labels";
import { Ref, RefList, RichText, useRefs } from "../lib/refs";
import type { Finding, Report } from "../types";
import { SevTag } from "./Severity";

interface Props {
  rid: string | null;
  report: Report;
  kept: Finding[];
  canLocate: boolean;
  onClose: () => void;
  onAllFindings: (rid: string) => void;
}

// Everything known about one requirement: text, findings, test probes, questions, links.
export function RequirementDrawer({ rid, report, kept, canLocate, onClose, onAllFindings }: Props) {
  const { meta, reqs, blocks, openFinding, openBlock } = useRefs();
  const r = rid ? reqs.get(rid) : undefined;

  const own = r
    ? kept
        .filter((f) => f.rid === r.rid || f.related_rids.includes(r.rid))
        .sort((a, b) => SEV_RANK[a.severity] - SEV_RANK[b.severity])
    : [];
  const probes = r ? report.probes.filter((p) => p.rid === r.rid) : [];
  const questions = r ? report.questions.filter((q) => q.rids.includes(r.rid)) : [];
  const unknown = r ? report.unassessable.filter((u) => u.rid === r.rid) : [];
  const block = r ? blocks.get(r.block_ids[0]) : undefined;

  return (
    <Drawer
      open={!!r}
      onClose={onClose}
      size={600}
      destroyOnHidden
      title={
        r && (
          <span className="drawer-title">
            Требование {r.rid}
            {r.source_id && <span className="ref-src">{r.source_id}</span>}
            <Tag>{meta.kind[r.kind] ?? r.kind}</Tag>
          </span>
        )
      }
    >
      {r && (
        <div className="req-detail">
          <div className="quote">
            <div className="quote-text">«{r.quote}»</div>
            <div className="quote-foot">
              <span className="muted">
                {r.source_ref}
                {block?.page != null && `, стр. ${block.page}`}
              </span>
              {canLocate && (
                <Button size="small" icon={<AimOutlined />} onClick={() => openBlock(r.block_ids[0], r.quote)}>
                  Показать в документе
                </Button>
              )}
            </div>
          </div>

          <section>
            <h4>
              Замечания: {own.length}
              {own.length > 0 && (
                <Button type="link" size="small" onClick={() => onAllFindings(r.rid)}>
                  Открыть списком
                </Button>
              )}
            </h4>
            {own.length === 0 && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="К этому требованию замечаний нет" />}
            <div className="mini-list">
              {own.map((f) => (
                <button type="button" key={f.fid} className="mini-item" onClick={() => openFinding(f.fid)}>
                  <SevTag s={f.severity} meta={meta} />
                  <span>{f.title}</span>
                </button>
              ))}
            </div>
          </section>

          {probes.length > 0 && (
            <section>
              <h4>
                Пробные тест-кейсы: написать удалось {probes.filter((p) => p.derivable).length} из {probes.length}
              </h4>
              <Collapse
                size="small"
                items={probes.map((p, i) => ({
                  key: String(i),
                  label: (
                    <span className="probe-label">
                      {p.derivable ? <CheckCircleFilled className="tone-ok" /> : <CloseCircleFilled className="tone-critical" />}
                      <span>{p.title}</span>
                      <span className="faint">{TECHNIQUE[p.technique] ?? p.technique}</span>
                    </span>
                  ),
                  children: (
                    <div className="probe">
                      {p.preconditions && (
                        <p>
                          <b>Исходное состояние.</b> {p.preconditions}
                        </p>
                      )}
                      {p.steps.length > 0 && (
                        <ol>
                          {p.steps.map((s, j) => (
                            <li key={j}>{s}</li>
                          ))}
                        </ol>
                      )}
                      <p>
                        <b>Ожидаемый результат.</b> <RichText text={p.expected} />
                      </p>
                      {!p.derivable && p.blocker && (
                        <p className="tone-critical">
                          <b>Почему тест не написать.</b> <RichText text={p.blocker} />
                        </p>
                      )}
                    </div>
                  ),
                }))}
              />
            </section>
          )}

          {questions.length > 0 && (
            <section>
              <h4>Вопросы авторам, которые затрагивают требование</h4>
              <div className="mini-list">
                {questions.map((q) => (
                  <div key={q.qid} className="mini-row">
                    <Ref id={q.qid} />
                    <span>{q.question}</span>
                  </div>
                ))}
              </div>
            </section>
          )}

          {r.traces_to.length > 0 && (
            <section>
              <h4>Связано с требованиями</h4>
              <RefList ids={r.traces_to} max={20} />
            </section>
          )}

          {unknown.length > 0 && (
            <section>
              <h4>Что нельзя оценить по тексту</h4>
              <ul className="unknown">
                {unknown.map((u, i) => (
                  <li key={i}>
                    <b>{meta.criteria[u.criterion]?.name ?? u.criterion}.</b> <RichText text={u.reason} />
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}
    </Drawer>
  );
}
