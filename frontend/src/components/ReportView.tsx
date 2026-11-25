import { useMemo, useState } from "react";
import { api } from "../api";
import type { Finding, Meta, Report, Requirement, Severity } from "../types";
import { DocumentPage, worst } from "./DocumentPage";
import { FindingItem, reqLabel } from "./FindingItem";
import { Questions } from "./Questions";

type Tab = "summary" | "findings" | "questions" | "requirements" | "rewrites";
const RANK: Record<Severity, number> = { critical: 0, major: 1, minor: 2 };

interface Props {
  report: Report;
  meta: Meta;
  runId: string;
  onRestart: () => void;
  onRun: (id: string) => void;
}

export function ReportView({ report, meta, runId, onRestart, onRun }: Props) {
  const kept = useMemo(
    () => report.findings.filter((f) => f.status === "kept").sort((a, b) => RANK[a.severity] - RANK[b.severity] || a.fid.localeCompare(b.fid)),
    [report],
  );
  const byId = useMemo(() => new Map(report.findings.map((f) => [f.fid, f])), [report]);
  const reqs = useMemo(() => new Map<string, Requirement>(report.requirements.map((r) => [r.rid, r])), [report]);
  const marks = useMemo(() => {
    const m = new Map<string, Finding[]>();
    for (const f of kept) for (const loc of f.locations) m.set(loc.block_id, [...(m.get(loc.block_id) ?? []), f]);
    return m;
  }, [kept]);

  const [tab, setTab] = useState<Tab>("summary");
  const [open, setOpen] = useState<string | null>(null);
  const [block, setBlock] = useState<string | null>(null);
  const [quote, setQuote] = useState<{ block: string; text: string } | null>(null);
  const [sev, setSev] = useState<Severity | null>(null);
  const [scope, setScope] = useState<"requirement" | "set" | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const locate = (blockId: string, text?: string) => {
    setBlock(blockId);
    setQuote(text ? { block: blockId, text } : null);
    document.getElementById(`blk-${blockId}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  };
  const toggle = (f: Finding) => {
    const next = open === f.fid ? null : f.fid;
    setOpen(next);
    if (next && f.locations[0]) locate(f.locations[0].block_id, f.locations[0].quote);
  };
  const selectBlock = (blockId: string) => {
    setBlock(blockId);
    setQuote(null);
    setTab("findings");
  };

  const listed = kept.filter(
    (f) =>
      (!sev || f.severity === sev) &&
      (!scope || f.scope === scope) &&
      (!block || f.locations.some((l) => l.block_id === block)),
  );
  const counts = { critical: 0, major: 0, minor: 0 } as Record<Severity, number>;
  kept.forEach((f) => (counts[f.severity] += 1));
  const blocked = report.probes.filter((p) => !p.derivable).length;
  const p = report.passport;
  const answered = Object.fromEntries(report.resolutions.map((r) => [r.qid, r.answer]));

  const submit = async (answers: Record<string, string>) => {
    setBusy(true);
    setProblem(null);
    try {
      onRun((await api.answer(runId, answers)).id);
    } catch (e) {
      setProblem(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };

  const tabs: [Tab, string][] = [
    ["summary", "Итог"],
    ["findings", `Замечания (${kept.length})`],
    ["questions", `Вопросы (${report.questions.length})`],
    ["requirements", `Требования (${report.requirements.length})`],
    ...(report.resolutions.length ? ([["rewrites", "Новая редакция"]] as [Tab, string][]) : []),
  ];

  return (
    <div className="app">
      <header className="topbar">
        <span className="wordmark">Revizorro</span>
        <span className="doc-title">{report.document.title}</span>
        <span className="muted">{p.source_file}</span>
        <span className="spacer" />
        <a className="btn btn-quiet" href={`/api/runs/${runId}/report.md`} download="report.md">
          Скачать отчёт .md
        </a>
        <a className="btn btn-quiet" href={`/api/runs/${runId}/report.html`} target="_blank" rel="noreferrer">
          Открыть HTML-отчёт
        </a>
        <button className="btn btn-quiet" onClick={onRestart}>
          Проверить другой документ
        </button>
      </header>

      <div className="workspace">
        <div className="doc-scroll">
          <DocumentPage blocks={report.document.blocks} marks={marks} selectedBlock={block} quote={quote} onSelect={selectBlock} />
        </div>

        <aside className="panel" aria-label="Результаты проверки">
          <div className="tabs" role="tablist">
            {tabs.map(([key, label]) => (
              <button key={key} className="tab" role="tab" aria-selected={tab === key} onClick={() => setTab(key)}>
                {label}
              </button>
            ))}
          </div>

          <div className="panel-body">
            {tab === "summary" && (
              <>
                <p className={`verdict ${report.verdict.decision}`}>{meta.decision[report.verdict.decision]}</p>
                <div className="tally">
                  <div>
                    <b>{report.requirements.length}</b>
                    <span>требований</span>
                  </div>
                  <div className="c">
                    <b>{counts.critical}</b>
                    <span>критичных</span>
                  </div>
                  <div className="m">
                    <b>{counts.major}</b>
                    <span>существенных</span>
                  </div>
                  <div>
                    <b>{counts.minor}</b>
                    <span>незначительных</span>
                  </div>
                  <div>
                    <b>{blocked}</b>
                    <span>тестов не вывести</span>
                  </div>
                </div>
                <p>
                  <b>Разработка.</b> {report.verdict.development}
                </p>
                <p>
                  <b>Тестирование.</b> {report.verdict.testing}
                </p>
                <p className="muted">{report.verdict.rationale}</p>
                <h2>Что исправить в первую очередь</h2>
                <ol className="fixes">
                  {report.verdict.first_fixes.map((x, i) => (
                    <li key={i}>
                      {x.action} {x.refs.length > 0 && <span className="refs">({x.refs.join(", ")})</span>}
                    </li>
                  ))}
                </ol>
                {report.verdict.can_start_now.length > 0 && (
                  <p>
                    <b>Можно начинать уже сейчас:</b> {report.verdict.can_start_now.join("; ")}.
                  </p>
                )}
                <h2>Паспорт прогона</h2>
                <dl className="passport">
                  <dt>Модели</dt>
                  <dd>{p.models_used.length ? p.models_used.join(", ") : `${p.model_default}, ${p.model_strong}`}</dd>
                  <dt>Версия агента</dt>
                  <dd>{p.agent_version}</dd>
                  <dt>Запросов</dt>
                  <dd className="num">
                    {p.llm_calls}
                    {p.cached_calls > 0 && `, из кэша ${p.cached_calls}`}
                  </dd>
                  <dt>Токены</dt>
                  <dd className="num">
                    {p.input_tokens.toLocaleString("ru-RU")} на входе, {p.output_tokens.toLocaleString("ru-RU")} на выходе
                  </dd>
                  <dt>Стоимость</dt>
                  <dd className="num">{p.cost_usd === null ? "нет данных" : `$${p.cost_usd.toFixed(2)}`}</dd>
                </dl>
              </>
            )}

            {tab === "findings" && (
              <>
                <div className="filter" role="group" aria-label="Фильтр замечаний">
                  {(["critical", "major", "minor"] as Severity[]).map((s) => (
                    <button key={s} className="chip" aria-pressed={sev === s} onClick={() => setSev(sev === s ? null : s)}>
                      {meta.severity[s]} {counts[s]}
                    </button>
                  ))}
                  <button className="chip" aria-pressed={scope === "requirement"} onClick={() => setScope(scope === "requirement" ? null : "requirement")}>
                    к требованиям
                  </button>
                  <button className="chip" aria-pressed={scope === "set"} onClick={() => setScope(scope === "set" ? null : "set")}>
                    к набору
                  </button>
                  {block && (
                    <button className="chip" aria-pressed onClick={() => setBlock(null)}>
                      только выбранное место, сбросить
                    </button>
                  )}
                </div>
                {listed.length === 0 && <p className="muted">Под выбранные условия замечаний нет.</p>}
                {listed.map((f) => (
                  <FindingItem
                    key={f.fid}
                    f={f}
                    meta={meta}
                    reqs={reqs}
                    byId={byId}
                    open={open === f.fid}
                    onToggle={() => toggle(f)}
                    onLocate={locate}
                  />
                ))}
              </>
            )}

            {tab === "questions" && (
              <>
                {problem && <p className="error">{problem}</p>}
                <Questions questions={report.questions} reqs={reqs} answered={answered} busy={busy} onSubmit={submit} />
              </>
            )}

            {tab === "requirements" && (
              <table className="req-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Формулировка</th>
                    <th>Замечания</th>
                  </tr>
                </thead>
                <tbody>
                  {report.requirements.map((r) => {
                    const own = kept.filter((f) => f.rid === r.rid || f.related_rids.includes(r.rid));
                    const w = worst(own);
                    return (
                      <tr key={r.rid} onClick={() => locate(r.block_ids[0], r.quote)}>
                        <td>{reqLabel(r.rid, reqs)}</td>
                        <td>
                          {r.summary}
                          <div className="muted">{meta.kind[r.kind] ?? r.kind}</div>
                        </td>
                        <td className="marks">
                          <span className={w === "critical" ? "c" : w === "major" ? "m" : undefined}>{own.length || "—"}</span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}

            {tab === "rewrites" &&
              report.resolutions.map((res) => (
                <section key={res.qid}>
                  <h2>
                    {res.qid}: {res.answer}
                  </h2>
                  {res.rewrites.map((w) => (
                    <div key={w.rid} className="rewrite">
                      <b>{reqLabel(w.rid, reqs)}</b>
                      <div className="old">{w.old}</div>
                      <div className="new">{w.new}</div>
                      {w.resolved_fids.length > 0 && <div className="muted">Закрыто: {w.resolved_fids.join(", ")}</div>}
                      <div className="muted">
                        Повторная проверка:{" "}
                        {w.remaining.length ? w.remaining.map((f) => `${meta.criteria[f.criterion]?.name ?? f.criterion} — ${f.title}`).join("; ") : "замечаний нет"}
                      </div>
                    </div>
                  ))}
                </section>
              ))}
          </div>
        </aside>
      </div>
    </div>
  );
}
