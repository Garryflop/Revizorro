import {
  CheckCircleFilled,
  CheckOutlined,
  DownloadOutlined,
  ExclamationCircleFilled,
  QuestionCircleOutlined,
  StopOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import { Alert, Button, Card, Col, Collapse, Descriptions, Row, Tooltip } from "antd";
import type { ReactNode } from "react";
import { AGENT, countBySeverity, plural, SEV_ORDER, W_FINDING } from "../lib/labels";
import { RefList, RichText, useRefs } from "../lib/refs";
import type { Decision, Finding, Report, Severity } from "../types";
import type { Filters } from "./Findings";
import type { ReqFilter } from "./Requirements";

const DECISION_ICON: Record<Decision, ReactNode> = {
  ready: <CheckCircleFilled />,
  ready_after_fixes: <ExclamationCircleFilled />,
  not_ready: <StopOutlined />,
};

interface Props {
  report: Report;
  kept: Finding[];
  runId: string;
  onFindings: (filters?: Partial<Filters>) => void;
  onQuestions: () => void;
  onRequirements: (filter?: ReqFilter) => void;
}

// Horizontal bars split by severity; one row per group, clickable.
function Breakdown({ rows, onPick }: { rows: { key: string; name: string; hint?: ReactNode; counts: Record<Severity, number> }[]; onPick?: (key: string) => void }) {
  const total = (c: Record<Severity, number>) => c.critical + c.major + c.minor;
  const max = Math.max(1, ...rows.map((r) => total(r.counts)));
  return (
    <div className="bars">
      {rows.map((r) => {
        const body = (
          <>
            <span className="bars-name">{r.name}</span>
            <span className="bars-track" aria-hidden>
              {SEV_ORDER.map((s) =>
                r.counts[s] ? <i key={s} className={`bars-seg sev-${s}`} style={{ width: `${(r.counts[s] / max) * 100}%` }} /> : null,
              )}
            </span>
            <span className="bars-n">{total(r.counts)}</span>
          </>
        );
        const row = onPick ? (
          <button type="button" className="bars-row" onClick={() => onPick(r.key)}>
            {body}
          </button>
        ) : (
          <div className="bars-row">{body}</div>
        );
        return (
          <Tooltip key={r.key} title={r.hint} placement="topLeft">
            {row}
          </Tooltip>
        );
      })}
    </div>
  );
}

function group(kept: Finding[], key: (f: Finding) => string) {
  const m = new Map<string, Finding[]>();
  for (const f of kept) m.set(key(f), [...(m.get(key(f)) ?? []), f]);
  return [...m.entries()].sort((a, b) => b[1].length - a[1].length);
}

export function Overview({ report, kept, runId, onFindings, onQuestions, onRequirements }: Props) {
  const { meta } = useRefs();
  const v = report.verdict;
  const p = report.passport;
  const counts = countBySeverity(kept);
  const blocked = report.probes.filter((x) => !x.derivable).length;

  const stats: { n: ReactNode; label: string; tone?: string; go: () => void }[] = [
    { n: report.requirements.length, label: "требований в документе", go: () => onRequirements() },
    { n: counts.critical, label: "критичных замечаний", tone: counts.critical ? "tone-critical" : undefined, go: () => onFindings({ sev: "critical" }) },
    { n: counts.major, label: "существенных", tone: counts.major ? "tone-major" : undefined, go: () => onFindings({ sev: "major" }) },
    { n: counts.minor, label: "незначительных", go: () => onFindings({ sev: "minor" }) },
    { n: report.questions.length, label: "вопросов авторам", go: onQuestions },
    {
      n: (
        <>
          {blocked}
          <small> из {report.probes.length}</small>
        </>
      ),
      label: "тест-кейсов нельзя написать",
      go: () => onRequirements("blocked"),
    },
  ];

  return (
    <div className="overview">
      <section className={`hero hero-${v.decision}`}>
        <div className="hero-icon" aria-hidden>
          {DECISION_ICON[v.decision]}
        </div>
        <div className="hero-text">
          <h1>{meta.decision[v.decision]}</h1>
          <p>
            <RichText text={v.rationale} />
          </p>
          <div className="hero-actions">
            <Button type="primary" icon={<WarningOutlined />} onClick={() => onFindings(counts.critical ? { sev: "critical" } : {})}>
              {counts.critical
                ? `Разобрать ${counts.critical} ${plural(counts.critical, ["критичное", "критичных", "критичных"])}`
                : `Разобрать ${kept.length} ${plural(kept.length, W_FINDING)}`}
            </Button>
            {report.questions.length > 0 && (
              <Button icon={<QuestionCircleOutlined />} onClick={onQuestions}>
                Ответить на вопросы
              </Button>
            )}
            <Button icon={<DownloadOutlined />} href={`/api/runs/${runId}/report.md`} download="report.md">
              Скачать отчёт
            </Button>
          </div>
        </div>
      </section>

      <div className="stats">
        {stats.map((s) => (
          <button type="button" key={s.label} className={`stat ${s.tone ?? ""}`} onClick={s.go}>
            <b>{s.n}</b>
            <span>{s.label}</span>
          </button>
        ))}
      </div>

      {report.unclassified_blocks.length > 0 && (
        <Alert
          type="warning"
          showIcon
          title={`Фрагментов документа, которые агент не смог отнести ни к требованиям, ни к служебному тексту: ${report.unclassified_blocks.length}`}
        />
      )}

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={15}>
          <Card title="Что исправить в первую очередь" className="card-fill">
            <ol className="fixes">
              {v.first_fixes.map((x, i) => (
                <li key={i}>
                  <span className="fix-n">{i + 1}</span>
                  <div>
                    <div className="fix-action">
                      <RichText text={x.action} />
                    </div>
                    {x.refs.length > 0 && <RefList ids={x.refs} max={12} />}
                  </div>
                </li>
              ))}
            </ol>
          </Card>
        </Col>
        <Col xs={24} xl={9}>
          <Card title="Готовность по ролям" className="card-fill">
            <h4>Разработка</h4>
            <p>
              <RichText text={v.development} />
            </p>
            <h4>Тестирование</h4>
            <p>
              <RichText text={v.testing} />
            </p>
            {v.can_start_now.length > 0 && (
              <>
                <h4>Можно начинать уже сейчас</h4>
                <ul className="can-start">
                  {v.can_start_now.map((x, i) => (
                    <li key={i}>
                      <CheckOutlined />
                      <span>
                        <RichText text={x} />
                      </span>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </Card>
        </Col>

        <Col xs={24} xl={12}>
          <Card title="Какие свойства требований нарушены" className="card-fill">
            <Breakdown
              rows={group(kept, (f) => f.criterion).map(([code, fs]) => ({
                key: code,
                name: meta.criteria[code]?.name ?? code,
                hint: meta.criteria[code] && (
                  <>
                    <b>{meta.criteria[code].source}</b>
                    {meta.criteria[code].violation && (
                      <>
                        <br />
                        Нарушение: {meta.criteria[code].violation}
                      </>
                    )}
                  </>
                ),
                counts: countBySeverity(fs),
              }))}
              onPick={(code) => onFindings({ criterion: code })}
            />
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card title="Какой агент что нашёл" className="card-fill">
            <Breakdown
              rows={group(kept, (f) => f.source_agent).map(([agent, fs]) => ({
                key: agent,
                name: AGENT[agent] ?? agent,
                counts: countBySeverity(fs),
              }))}
            />
            <p className="muted bars-note">
              Замечания без подтверждённой цитаты и отклонённые критиком сюда не входят:{" "}
              {report.findings.filter((f) => f.status === "rejected").length} отклонено,{" "}
              {report.findings.filter((f) => f.status === "merged").length} объединено с похожими.
            </p>
          </Card>
        </Col>
      </Row>

      <Collapse
        className="passport"
        items={[
          {
            key: "passport",
            label: "Паспорт прогона: модели, версия, токены, стоимость",
            children: (
              <Descriptions
                size="small"
                column={{ xs: 1, md: 2 }}
                items={[
                  { key: "file", label: "Файл", children: `${p.source_file} (${p.source_format})` },
                  { key: "date", label: "Дата", children: new Date(p.started_at).toLocaleString("ru-RU") },
                  { key: "models", label: "Модели", children: (p.models_used.length ? p.models_used : [p.model_default, p.model_strong]).join(", ") },
                  { key: "version", label: "Версия агента", children: p.agent_version },
                  { key: "calls", label: "Запросов к модели", children: `${p.llm_calls}${p.cached_calls ? `, из кэша ${p.cached_calls}` : ""}` },
                  {
                    key: "tokens",
                    label: "Токены",
                    children: `${p.input_tokens.toLocaleString("ru-RU")} на входе, ${p.output_tokens.toLocaleString("ru-RU")} на выходе`,
                  },
                  { key: "cost", label: "Стоимость по прайсу", children: p.cost_usd === null ? "нет данных" : `$${p.cost_usd.toFixed(2)}` },
                  { key: "sha", label: "SHA-256 файла", children: p.sha256 ? <code>{p.sha256.slice(0, 16)}…</code> : "нет данных" },
                ]}
              />
            ),
          },
        ]}
      />
    </div>
  );
}
