import { Fragment, type ReactNode } from "react";
import type { Block, Finding, Severity } from "../types";

const RANK: Record<Severity, number> = { critical: 0, major: 1, minor: 2 };

export function worst(findings: Finding[]): Severity | null {
  return findings.reduce<Severity | null>((w, f) => (w === null || RANK[f.severity] < RANK[w] ? f.severity : w), null);
}

// Highlight a quote inside block text; falls back to plain text when it is not found verbatim.
function withMark(text: string, quote: string | null): ReactNode {
  if (!quote) return text;
  const at = text.toLowerCase().indexOf(quote.toLowerCase().replace(/[«»"]/g, "").trim());
  if (at < 0) return text;
  const len = quote.replace(/[«»"]/g, "").trim().length;
  return (
    <>
      {text.slice(0, at)}
      <mark>{text.slice(at, at + len)}</mark>
      {text.slice(at + len)}
    </>
  );
}

interface Props {
  blocks: Block[];
  marks: Map<string, Finding[]>;
  selectedBlock: string | null;
  quote: { block: string; text: string } | null;
  onSelect: (blockId: string) => void;
}

export function DocumentPage({ blocks, marks, selectedBlock, quote, onSelect }: Props) {
  const attrs = (b: Block) => {
    const fs = marks.get(b.id) ?? [];
    const sev = worst(fs);
    return {
      id: `blk-${b.id}`,
      "data-count": fs.length ? String(fs.length) : undefined,
      className: ["blk", sev && "marked", sev && `sev-${sev}`, selectedBlock === b.id && "selected"].filter(Boolean).join(" "),
      onClick: fs.length ? () => onSelect(b.id) : undefined,
      title: fs.length ? `${fs.length} замеч.: ${fs.map((f) => f.fid).join(", ")}` : undefined,
    };
  };
  const text = (b: Block) => withMark(b.text, quote?.block === b.id ? quote.text : null);

  // Group consecutive table rows into one table and list items into one list.
  const isTable = (b: Block) => b.kind === "table_row" || b.kind === "table_header";
  const groups: Block[][] = [];
  for (const b of blocks) {
    const last = groups[groups.length - 1];
    const joinTable = last && isTable(last[0]) && b.kind === "table_row";
    const joinList = last && last[0].kind === "list_item" && b.kind === "list_item";
    if (joinTable || joinList) last.push(b);
    else groups.push([b]);
  }

  return (
    <article className="page" aria-label="Проверяемый документ">
      {groups.map((g) => {
        const first = g[0];
        if (first.kind === "table_header" || first.kind === "table_row") {
          return (
            <table key={first.id}>
              <tbody>
                {g.map((b) => (
                  <tr key={b.id} {...attrs(b)}>
                    {b.text.split(" | ").map((cell, i) =>
                      b.kind === "table_header" ? <th key={i}>{cell}</th> : <td key={i}>{cell === "(пусто)" ? "" : withMark(cell, quote?.block === b.id ? quote.text : null)}</td>,
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          );
        }
        if (first.kind === "list_item") {
          return (
            <ul key={first.id}>
              {g.map((b) => (
                <li key={b.id} {...attrs(b)}>
                  {text(b)}
                </li>
              ))}
            </ul>
          );
        }
        return (
          <Fragment key={first.id}>
            {g.map((b) => {
              const a = attrs(b);
              switch (b.kind) {
                case "heading": {
                  const level = Math.min(4, b.heading_level ?? 2);
                  const H = `h${level}` as "h1";
                  return <H key={b.id} {...a}>{text(b)}</H>;
                }
                case "code":
                  return <pre key={b.id} {...a}>{text(b)}</pre>;
                default:
                  return <p key={b.id} {...a}>{text(b)}</p>;
              }
            })}
          </Fragment>
        );
      })}
    </article>
  );
}
