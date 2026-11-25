import { ExclamationCircleFilled, InfoCircleFilled, WarningFilled } from "@ant-design/icons";
import { Tag, Tooltip } from "antd";
import type { ReactNode } from "react";
import { SEV_ORDER } from "../lib/labels";
import type { Meta, Severity } from "../types";

export const SEV_ICON: Record<Severity, ReactNode> = {
  critical: <ExclamationCircleFilled />,
  major: <WarningFilled />,
  minor: <InfoCircleFilled />,
};

const SEV_COLOR: Record<Severity, string> = { critical: "error", major: "warning", minor: "default" };

export function SevTag({ s, meta }: { s: Severity; meta: Meta }) {
  return (
    <Tag color={SEV_COLOR[s]} icon={SEV_ICON[s]} className="sev-tag">
      {meta.severity[s]}
    </Tag>
  );
}

// Compact "2 critical, 1 major" counters for tables and lists.
export function SevCounts({ counts, meta }: { counts: Record<Severity, number>; meta: Meta }) {
  const shown = SEV_ORDER.filter((s) => counts[s] > 0);
  if (!shown.length) return <span className="faint">нет</span>;
  return (
    <span className="sev-counts">
      {shown.map((s) => (
        <Tooltip key={s} title={`${meta.severity[s]}: ${counts[s]}`}>
          <span className={`sev-count tone-${s}`}>
            {SEV_ICON[s]} {counts[s]}
          </span>
        </Tooltip>
      ))}
    </span>
  );
}
