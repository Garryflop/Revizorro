import { CloseCircleOutlined, SearchOutlined } from "@ant-design/icons";
import { Button, Empty, Input, Segmented, Select, Splitter, Tag } from "antd";
import { useMemo } from "react";
import { countBySeverity, SEV_ORDER, SEV_PLURAL } from "../lib/labels";
import { useRefs } from "../lib/refs";
import type { Block, Finding, Severity } from "../types";
import { DocumentPage } from "./DocumentPage";
import { FindingCard } from "./FindingCard";
import { SEV_ICON } from "./Severity";

export interface Filters {
  sev: Severity | null;
  criterion: string | null;
  scope: "requirement" | "set" | null;
  query: string;
  block: string | null; // only findings attached to this place of the document
  rid: string | null; // only findings of this requirement
}

export const NO_FILTERS: Filters = { sev: null, criterion: null, scope: null, query: "", block: null, rid: null };

export function matches(f: Finding, x: Filters): boolean {
  if (x.sev && f.severity !== x.sev) return false;
  if (x.criterion && f.criterion !== x.criterion) return false;
  if (x.scope && f.scope !== x.scope) return false;
  if (x.block && !f.locations.some((l) => l.block_id === x.block)) return false;
  if (x.rid && f.rid !== x.rid && !f.related_rids.includes(x.rid)) return false;
  const q = x.query.trim().toLowerCase();
  if (q && !`${f.fid} ${f.title} ${f.problem} ${f.suggestion}`.toLowerCase().includes(q)) return false;
  return true;
}

interface Props {
  kept: Finding[];
  blocks: Block[];
  marks: Map<string, Finding[]>;
  filters: Filters;
  onFilters: (f: Filters) => void;
  openFid: string | null;
  onToggle: (f: Finding) => void;
  selected: string | null; // highlighted document block
  quote: { block: string; text: string } | null;
  onLocate: (blockId: string, quote?: string) => void;
  questionsOf: Map<string, string[]>;
  wide: boolean;
  fileName: string;
}

export function Findings(p: Props) {
  const { meta, blocks: blockMap } = useRefs();
  const { kept, filters: x, onFilters } = p;
  const listed = useMemo(() => kept.filter((f) => matches(f, x)), [kept, x]);
  const counts = useMemo(() => countBySeverity(kept), [kept]);
  const criteria = useMemo(() => {
    const n = new Map<string, number>();
    for (const f of kept) n.set(f.criterion, (n.get(f.criterion) ?? 0) + 1);
    return [...n.entries()].sort((a, b) => b[1] - a[1]);
  }, [kept]);
  const place = x.block ? blockMap.get(x.block) : null;
  const filtered = listed.length !== kept.length;

  const list = (
    <div className="flist">
      {listed.length === 0 && (
        <Empty description="Под выбранные условия замечаний нет">
          <Button onClick={() => onFilters(NO_FILTERS)}>Сбросить фильтры</Button>
        </Empty>
      )}
      {listed.map((f) => (
        <FindingCard
          key={f.fid}
          f={f}
          open={p.openFid === f.fid}
          questionIds={p.questionsOf.get(f.fid) ?? []}
          canLocate={p.wide}
          onToggle={() => p.onToggle(f)}
          onLocate={p.onLocate}
        />
      ))}
    </div>
  );

  return (
    <div className="findings">
      <div className="filterbar" role="group" aria-label="Фильтр замечаний">
        <Segmented<Severity | "all">
          value={x.sev ?? "all"}
          onChange={(v) => onFilters({ ...x, sev: v === "all" ? null : v })}
          options={[
            { value: "all", label: `Все ${kept.length}` },
            ...SEV_ORDER.map((s) => ({
              value: s,
              label: (
                <span className={`tone-${s}`}>
                  {SEV_ICON[s]} {SEV_PLURAL[s]} {counts[s]}
                </span>
              ),
            })),
          ]}
        />
        <Select
          allowClear
          placeholder="Критерий качества"
          className="filter-select"
          value={x.criterion}
          onChange={(v) => onFilters({ ...x, criterion: v ?? null })}
          options={criteria.map(([code, n]) => ({ value: code, label: `${meta.criteria[code]?.name ?? code} (${n})` }))}
          popupMatchSelectWidth={false}
        />
        <Select
          allowClear
          placeholder="К чему относится"
          className="filter-select"
          value={x.scope}
          onChange={(v) => onFilters({ ...x, scope: v ?? null })}
          options={[
            { value: "requirement", label: "К одному требованию" },
            { value: "set", label: "К набору требований" },
          ]}
        />
        <Input
          allowClear
          className="filter-search"
          prefix={<SearchOutlined />}
          placeholder="Поиск по замечаниям"
          value={x.query}
          onChange={(e) => onFilters({ ...x, query: e.target.value })}
        />
        {x.rid && (
          <Tag closable color="processing" onClose={() => onFilters({ ...x, rid: null })}>
            Требование {x.rid}
          </Tag>
        )}
        {place && (
          <Tag closable color="processing" onClose={() => onFilters({ ...x, block: null })}>
            Фрагмент: {place.text.length > 36 ? `${place.text.slice(0, 36)}…` : place.text}
          </Tag>
        )}
        {filtered && (
          <span className="filter-count muted">
            Показано {listed.length} из {kept.length}
            <Button type="link" size="small" icon={<CloseCircleOutlined />} onClick={() => onFilters(NO_FILTERS)}>
              Сбросить
            </Button>
          </span>
        )}
      </div>

      {p.wide ? (
        <Splitter className="work">
          <Splitter.Panel defaultSize="46%" min="30%" max="70%">
            <div className="work-scroll">{list}</div>
          </Splitter.Panel>
          <Splitter.Panel>
            <div className="work-scroll doc-pane">
              <div className="doc-legend">
                <b>{p.fileName}</b>
                <span className="legend">
                  {SEV_ORDER.map((s) => (
                    <span key={s} className="legend-item">
                      <i className={`legend-bar sev-${s}`} /> {meta.severity[s]}
                    </span>
                  ))}
                </span>
                <span className="muted">Нажмите на отмеченный фрагмент, чтобы увидеть замечания к нему.</span>
              </div>
              <DocumentPage
                blocks={p.blocks}
                marks={p.marks}
                selectedBlock={p.selected}
                quote={p.quote}
                onSelect={(id) => onFilters({ ...NO_FILTERS, block: id })}
              />
            </div>
          </Splitter.Panel>
        </Splitter>
      ) : (
        list
      )}
    </div>
  );
}
