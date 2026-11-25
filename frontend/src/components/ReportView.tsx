import {
  AuditOutlined,
  CheckCircleFilled,
  CodeOutlined,
  DownloadOutlined,
  EditOutlined,
  ExclamationCircleFilled,
  FileMarkdownOutlined,
  FileTextOutlined,
  Html5Outlined,
  PlusOutlined,
  ProfileOutlined,
  QuestionCircleOutlined,
  StopOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import { Button, Dropdown, Grid, Menu, Tag, Tooltip } from "antd";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api } from "../api";
import { countBySeverity, DECISION_SHORT, SEV_RANK } from "../lib/labels";
import { RefContext, resolveFinding, type RefApi } from "../lib/refs";
import type { Decision, Finding, Meta, Report } from "../types";
import { Brand } from "./Brand";
import { Findings, NO_FILTERS, type Filters } from "./Findings";
import { Overview } from "./Overview";
import { Questions } from "./Questions";
import { RequirementDrawer } from "./RequirementDrawer";
import { Requirements, type ReqFilter } from "./Requirements";
import { Rewrites } from "./Rewrites";

type Section = "overview" | "findings" | "questions" | "requirements" | "rewrites";
const SECTIONS: Section[] = ["overview", "findings", "questions", "requirements", "rewrites"];

const DECISION_TAG: Record<Decision, { color: string; icon: ReactNode }> = {
  ready: { color: "success", icon: <CheckCircleFilled /> },
  ready_after_fixes: { color: "warning", icon: <ExclamationCircleFilled /> },
  not_ready: { color: "error", icon: <StopOutlined /> },
};

interface Props {
  report: Report;
  meta: Meta;
  runId: string;
  initialTab?: string;
  initialItem?: string; // R-07, F-057 or Q-08 from a deep link
  onRestart: () => void;
  onRun: (id: string) => void;
}

function scrollToId(id: string) {
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  document
    .getElementById(id)
    ?.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: id.startsWith("blk-") ? "center" : "start" });
}

export function ReportView({ report, meta, runId, initialTab, initialItem, onRestart, onRun }: Props) {
  const wide = !!Grid.useBreakpoint().lg;

  const kept = useMemo(
    () =>
      report.findings
        .filter((f) => f.status === "kept")
        .sort((a, b) => SEV_RANK[a.severity] - SEV_RANK[b.severity] || a.fid.localeCompare(b.fid)),
    [report],
  );
  const findings = useMemo(() => new Map(report.findings.map((f) => [f.fid, f])), [report]);
  const reqs = useMemo(() => new Map(report.requirements.map((r) => [r.rid, r])), [report]);
  const questions = useMemo(() => new Map(report.questions.map((q) => [q.qid, q])), [report]);
  const blocks = useMemo(() => new Map(report.document.blocks.map((b) => [b.id, b])), [report]);
  // Findings attached to each document block, for the marks in the margin.
  const marks = useMemo(() => {
    const m = new Map<string, Finding[]>();
    for (const f of kept) for (const loc of f.locations) m.set(loc.block_id, [...(m.get(loc.block_id) ?? []), f]);
    return m;
  }, [kept]);
  // Which questions remove which finding.
  const questionsOf = useMemo(() => {
    const m = new Map<string, string[]>();
    for (const q of report.questions)
      for (const id of q.finding_ids) {
        const f = resolveFinding(id, findings);
        if (f && !m.get(f.fid)?.includes(q.qid)) m.set(f.fid, [...(m.get(f.fid) ?? []), q.qid]);
      }
    return m;
  }, [report, findings]);

  const start = initialTab === "summary" ? "overview" : (initialTab as Section);
  const [section, setSection] = useState<Section>(SECTIONS.includes(start) ? start : "overview");
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [openFid, setOpenFid] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null); // highlighted document block
  const [quote, setQuote] = useState<{ block: string; text: string } | null>(null);
  const [drawer, setDrawer] = useState<string | null>(null);
  const [reqFilter, setReqFilter] = useState<ReqFilter>("all");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const sectionRef = useRef(section);
  sectionRef.current = section;

  // Element ids to scroll to once the next render has put them on the page.
  const pending = useRef<string[]>([]);
  useEffect(() => {
    if (!pending.current.length) return;
    const ids = pending.current;
    pending.current = [];
    requestAnimationFrame(() => ids.forEach(scrollToId));
  });

  // The hash is a shareable link to the open section and, optionally, to one item in it.
  const go = useCallback(
    (s: Section, item?: string) => {
      setSection(s);
      history.replaceState(null, "", `#/run/${runId}/${s}${item ? `/${item}` : ""}`);
    },
    [runId],
  );

  const showBlock = useCallback((blockId: string, text?: string) => {
    setSelected(blockId);
    setQuote(text ? { block: blockId, text } : null);
    pending.current.push(`blk-${blockId}`);
  }, []);

  const refApi = useMemo<RefApi>(
    () => ({
      meta,
      reqs,
      findings,
      questions,
      blocks,
      openRequirement: (rid) => {
        setDrawer(rid);
        history.replaceState(null, "", `#/run/${runId}/${sectionRef.current}/${rid}`);
      },
      openFinding: (fid) => {
        const f = findings.get(fid);
        setDrawer(null);
        go("findings", fid);
        setFilters(NO_FILTERS);
        setOpenFid(fid);
        pending.current.push(`fnd-${fid}`);
        if (f?.locations[0]) showBlock(f.locations[0].block_id, f.locations[0].quote);
      },
      openQuestion: (qid) => {
        setDrawer(null);
        go("questions", qid);
        pending.current.push(`q-${qid}`);
      },
      openBlock: (blockId, text) => {
        setDrawer(null);
        go("findings");
        setOpenFid(null);
        setFilters({ ...NO_FILTERS, block: marks.has(blockId) ? blockId : null });
        showBlock(blockId, text);
      },
    }),
    [meta, reqs, findings, questions, blocks, marks, go, showBlock, runId],
  );

  // Open the item named in a deep link once, after the first render.
  const linked = useRef(false);
  useEffect(() => {
    if (linked.current || !initialItem) return;
    linked.current = true;
    if (initialItem.startsWith("R-") && reqs.has(initialItem)) setDrawer(initialItem);
    else if (initialItem.startsWith("F-")) {
      const f = resolveFinding(initialItem, findings);
      if (f) refApi.openFinding(f.fid);
    } else if (initialItem.startsWith("Q-") && questions.has(initialItem)) refApi.openQuestion(initialItem);
  }, [initialItem, reqs, findings, questions, refApi]);

  const toggle = (f: Finding) => {
    const next = openFid === f.fid ? null : f.fid;
    setOpenFid(next);
    go("findings", next ?? undefined);
    if (next && f.locations[0]) showBlock(f.locations[0].block_id, f.locations[0].quote);
  };
  const applyFilters = (x: Filters) => {
    setFilters(x);
    if (x.block !== filters.block) {
      setSelected(x.block);
      setQuote(null);
    }
  };
  const toFindings = (x: Partial<Filters> = {}) => {
    setFilters({ ...NO_FILTERS, ...x });
    setOpenFid(null);
    go("findings");
  };

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

  const p = report.passport;
  const counts = countBySeverity(kept);
  const rewrites = report.resolutions.reduce((n, r) => n + r.rewrites.length, 0);
  const answered = Object.fromEntries(report.resolutions.map((r) => [r.qid, r.answer]));
  const decision = DECISION_TAG[report.verdict.decision];

  const navLabel = (text: string, n: number, tone?: string) => (
    <span className="nav-label">
      <span className="nav-text">{text}</span>
      <span className={`nav-count ${tone ?? ""}`}>{n}</span>
    </span>
  );
  const nav = [
    { key: "overview", icon: <AuditOutlined />, label: "Итог" },
    { key: "findings", icon: <WarningOutlined />, label: navLabel("Замечания", kept.length, counts.critical ? "tone-critical" : undefined) },
    { key: "questions", icon: <QuestionCircleOutlined />, label: navLabel("Вопросы авторам", report.questions.length) },
    { key: "requirements", icon: <ProfileOutlined />, label: navLabel("Требования", report.requirements.length) },
    ...(report.resolutions.length ? [{ key: "rewrites", icon: <EditOutlined />, label: navLabel("Новая редакция", rewrites) }] : []),
  ];

  return (
    <RefContext.Provider value={refApi}>
      <div className="report">
        <header className="bar">
          <Brand onClick={() => go("overview")} />
          <span className="bar-doc">
            <FileTextOutlined />
            <span className="bar-title">{report.document.title}</span>
            <span className="muted bar-file">{p.source_file}</span>
          </span>
          <Tooltip title={meta.decision[report.verdict.decision]}>
            <Tag color={decision.color} icon={decision.icon} className="bar-verdict" onClick={() => go("overview")}>
              {DECISION_SHORT[report.verdict.decision]}
            </Tag>
          </Tooltip>
          <span className="spacer" />
          <Dropdown
            menu={{
              items: [
                {
                  key: "md",
                  icon: <FileMarkdownOutlined />,
                  label: (
                    <a href={`/api/runs/${runId}/report.md`} download="report.md">
                      Скачать отчёт в Markdown
                    </a>
                  ),
                },
                {
                  key: "html",
                  icon: <Html5Outlined />,
                  label: (
                    <a href={`/api/runs/${runId}/report.html`} target="_blank" rel="noreferrer">
                      Открыть отчёт одной страницей
                    </a>
                  ),
                },
                {
                  key: "json",
                  icon: <CodeOutlined />,
                  label: (
                    <a href={`/api/runs/${runId}/report`} target="_blank" rel="noreferrer">
                      Данные отчёта в JSON
                    </a>
                  ),
                },
              ],
            }}
          >
            <Button icon={<DownloadOutlined />} aria-label="Отчёт">
              {wide && "Отчёт"}
            </Button>
          </Dropdown>
          <Tooltip title={wide ? undefined : "Проверить другой документ"}>
            <Button icon={<PlusOutlined />} onClick={onRestart} aria-label="Проверить другой документ">
              {wide && "Новая проверка"}
            </Button>
          </Tooltip>
        </header>

        <div className="report-body">
          <nav className="nav" aria-label="Разделы отчёта">
            <Menu
              mode={wide ? "inline" : "horizontal"}
              inlineIndent={14}
              selectedKeys={[section]}
              items={nav}
              onClick={(e) => go(e.key as Section)}
            />
            {wide && (
              <div className="nav-legend">
                <b>Обозначения</b>
                <div>
                  <span className="ref ref-chip ref-req sample">R-07</span> требование
                </div>
                <div>
                  <span className="ref ref-chip ref-finding tone-critical sample">F-057</span> замечание
                </div>
                <div>
                  <span className="ref ref-chip ref-question sample">Q-08</span> вопрос авторам
                </div>
                <p>Любое обозначение в тексте можно нажать: откроется то, на что оно ссылается.</p>
              </div>
            )}
          </nav>

          <main className={`pane pane-${section}`}>
            {section === "overview" && (
              <Overview
                report={report}
                kept={kept}
                runId={runId}
                onFindings={toFindings}
                onQuestions={() => go("questions")}
                onRequirements={(f) => {
                  setReqFilter(f ?? "all");
                  go("requirements");
                }}
              />
            )}
            {section === "findings" && (
              <Findings
                kept={kept}
                blocks={report.document.blocks}
                marks={marks}
                filters={filters}
                onFilters={applyFilters}
                openFid={openFid}
                onToggle={toggle}
                selected={selected}
                quote={quote}
                onLocate={showBlock}
                questionsOf={questionsOf}
                wide={wide}
                fileName={p.source_file}
              />
            )}
            {section === "questions" && (
              <Questions
                questions={report.questions}
                answered={answered}
                rewrites={rewrites}
                busy={busy}
                problem={problem}
                onSubmit={submit}
                onRewrites={() => go("rewrites")}
              />
            )}
            {section === "requirements" && <Requirements report={report} kept={kept} filter={reqFilter} onFilter={setReqFilter} />}
            {section === "rewrites" && <Rewrites report={report} />}
          </main>
        </div>

        <RequirementDrawer
          rid={drawer}
          report={report}
          kept={kept}
          canLocate={wide}
          onClose={() => {
            setDrawer(null);
            go(section);
          }}
          onAllFindings={(rid) => {
            setDrawer(null);
            toFindings({ rid });
          }}
        />
      </div>
    </RefContext.Provider>
  );
}
