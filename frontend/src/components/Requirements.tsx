import { SearchOutlined } from "@ant-design/icons";
import { Input, Segmented, Table, Tag, Tooltip } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useMemo, useState } from "react";
import { countBySeverity } from "../lib/labels";
import { useRefs } from "../lib/refs";
import type { Finding, Report, Requirement, Severity } from "../types";
import { SevCounts } from "./Severity";

export type ReqFilter = "all" | "with" | "blocked" | "clean";

interface RowData {
  key: string;
  r: Requirement;
  counts: Record<Severity, number>;
  weight: number; // sort key: critical findings first
  total: number;
  probes: number;
  derivable: number;
  questions: number;
}

interface Props {
  report: Report;
  kept: Finding[];
  filter: ReqFilter;
  onFilter: (f: ReqFilter) => void;
}

export function Requirements({ report, kept, filter, onFilter }: Props) {
  const { meta, openRequirement } = useRefs();
  const [query, setQuery] = useState("");

  const rows = useMemo<RowData[]>(
    () =>
      report.requirements.map((r) => {
        const own = kept.filter((f) => f.rid === r.rid || f.related_rids.includes(r.rid));
        const counts = countBySeverity(own);
        const probes = report.probes.filter((p) => p.rid === r.rid);
        return {
          key: r.rid,
          r,
          counts,
          weight: counts.critical * 100 + counts.major * 10 + counts.minor,
          total: own.length,
          probes: probes.length,
          derivable: probes.filter((p) => p.derivable).length,
          questions: report.questions.filter((q) => q.rids.includes(r.rid)).length,
        };
      }),
    [report, kept],
  );

  const q = query.trim().toLowerCase();
  const shown = rows.filter(
    (x) =>
      (filter === "all" ||
        (filter === "with" && x.total > 0) ||
        (filter === "blocked" && x.derivable < x.probes) ||
        (filter === "clean" && x.total === 0)) &&
      (!q || `${x.r.rid} ${x.r.source_id ?? ""} ${x.r.summary} ${x.r.source_ref}`.toLowerCase().includes(q)),
  );
  const kinds = [...new Set(report.requirements.map((r) => r.kind))];

  const columns: ColumnsType<RowData> = [
    {
      title: "ID",
      key: "id",
      width: 120,
      sorter: (a, b) => a.r.rid.localeCompare(b.r.rid),
      render: (_, x) => (
        <span className="req-id">
          <b>{x.r.rid}</b>
          {x.r.source_id && (
            <Tooltip title="Обозначение в документе">
              <span className="ref-src">{x.r.source_id}</span>
            </Tooltip>
          )}
        </span>
      ),
    },
    {
      title: "Требование",
      key: "summary",
      render: (_, x) => (
        <>
          <div>{x.r.summary}</div>
          <div className="muted req-where">{x.r.source_ref}</div>
        </>
      ),
    },
    {
      title: "Тип",
      key: "kind",
      width: 170,
      filters: kinds.map((k) => ({ text: meta.kind[k] ?? k, value: k })),
      onFilter: (value, x) => x.r.kind === value,
      render: (_, x) => <Tag>{meta.kind[x.r.kind] ?? x.r.kind}</Tag>,
    },
    {
      title: "Замечания",
      key: "findings",
      width: 140,
      sorter: (a, b) => a.weight - b.weight,
      defaultSortOrder: undefined,
      render: (_, x) => <SevCounts counts={x.counts} meta={meta} />,
    },
    {
      title: (
        <Tooltip title="Сколько пробных тест-кейсов удалось написать по тексту требования. Если ожидаемый результат вывести нельзя, требование непроверяемо.">
          <span className="term">Тест-кейсы</span>
        </Tooltip>
      ),
      key: "probes",
      width: 130,
      sorter: (a, b) => a.probes - a.derivable - (b.probes - b.derivable),
      render: (_, x) =>
        x.probes === 0 ? (
          <span className="faint">нет</span>
        ) : (
          <span className={x.derivable < x.probes ? "tone-major" : undefined}>
            {x.derivable} из {x.probes}
          </span>
        ),
    },
    {
      title: "Вопросы",
      key: "questions",
      width: 100,
      sorter: (a, b) => a.questions - b.questions,
      render: (_, x) => (x.questions ? x.questions : <span className="faint">нет</span>),
    },
  ];

  return (
    <div className="requirements">
      <div className="section-head">
        <h1>Реестр требований</h1>
        <p className="muted">
          Так агент разобрал документ на отдельные требования. Нажмите на строку, чтобы увидеть текст, замечания,
          тест-кейсы и связанные вопросы.
        </p>
      </div>
      <div className="filterbar">
        <Segmented<ReqFilter>
          value={filter}
          onChange={onFilter}
          options={[
            { value: "all", label: `Все ${rows.length}` },
            { value: "with", label: `С замечаниями ${rows.filter((x) => x.total > 0).length}` },
            { value: "blocked", label: `Тест не написать ${rows.filter((x) => x.derivable < x.probes).length}` },
            { value: "clean", label: `Без замечаний ${rows.filter((x) => x.total === 0).length}` },
          ]}
        />
        <Input
          allowClear
          className="filter-search"
          prefix={<SearchOutlined />}
          placeholder="Поиск по требованиям"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>
      <Table<RowData>
        size="middle"
        columns={columns}
        dataSource={shown}
        pagination={false}
        rowClassName="req-row"
        onRow={(x) => ({
          onClick: () => openRequirement(x.r.rid),
          onKeyDown: (e) => e.key === "Enter" && openRequirement(x.r.rid),
          tabIndex: 0,
        })}
        scroll={{ x: 860 }}
      />
    </div>
  );
}
