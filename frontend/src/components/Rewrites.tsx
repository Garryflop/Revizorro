import { ArrowDownOutlined, CheckCircleFilled, WarningFilled } from "@ant-design/icons";
import { Card, Empty } from "antd";
import { Ref, RefList, useRefs } from "../lib/refs";
import type { Report } from "../types";

// Requirements rewritten from the answers, each with the result of the repeated check.
export function Rewrites({ report }: { report: Report }) {
  const { meta, questions } = useRefs();
  if (!report.resolutions.length) return <Empty description="Новой редакции пока нет: ответьте на вопросы авторам" />;

  return (
    <div className="rewrites">
      <div className="section-head">
        <h1>Новая редакция требований</h1>
        <p className="muted">
          Агент переписал требования по вашим ответам и проверил новый текст тем же ревьюером. Старая формулировка
          зачёркнута.
        </p>
      </div>
      {report.resolutions.map((res) => {
        const q = questions.get(res.qid);
        const picked = q?.options.find((o) => o.label === res.answer);
        return (
          <Card
            key={res.qid}
            title={
              <span className="rewrite-title">
                <Ref id={res.qid} /> {q?.question}
              </span>
            }
          >
            <p className="rewrite-answer">
              <b>Ваш ответ:</b> {picked ? `${picked.label}. ${picked.answer}` : res.answer}
            </p>
            {res.rewrites.length === 0 && <p className="muted">По этому ответу менять текст требований не пришлось.</p>}
            {res.rewrites.map((w) => (
              <div key={w.rid} className="rewrite">
                <div className="rewrite-head">
                  <Ref id={w.rid} />
                  {w.resolved_fids.length > 0 && (
                    <span className="muted">
                      закрывает <RefList ids={w.resolved_fids} max={8} />
                    </span>
                  )}
                </div>
                <div className="rewrite-old">{w.old}</div>
                <ArrowDownOutlined className="rewrite-arrow" />
                <div className="rewrite-new">{w.new}</div>
                {w.remaining.length === 0 ? (
                  <div className="rewrite-check tone-ok">
                    <CheckCircleFilled /> Повторная проверка: замечаний нет
                  </div>
                ) : (
                  <div className="rewrite-check tone-major">
                    <WarningFilled /> Повторная проверка, осталось:{" "}
                    {w.remaining.map((f) => `${meta.criteria[f.criterion]?.name ?? f.criterion}: ${f.title}`).join("; ")}
                  </div>
                )}
              </div>
            ))}
          </Card>
        );
      })}
    </div>
  );
}
