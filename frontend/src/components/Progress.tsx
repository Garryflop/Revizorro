import { useEffect, useState } from "react";
import { api } from "../api";
import type { Report, RunEvent } from "../types";

const STAGES: [string, string][] = [
  ["ingest", "Чтение документа и разметка блоков"],
  ["segment", "Нарезка требований"],
  ["review", "Проверка требований, тест-дизайн, проверка набора"],
  ["verify", "Сверка цитат и перепроверка критиком"],
  ["clarify", "Вопросы-развилки к авторам"],
  ["resolve", "Новая редакция по ответам"],
  ["summarize", "Итог"],
];

type StageState = "pending" | "active" | "done";

function detail(e: RunEvent): string {
  const skip = new Set(["type", "stage", "status"]);
  const names: Record<string, string> = {
    blocks: "блоков",
    requirements: "требований",
    findings: "находок",
    kept: "подтверждено",
    rejected: "отклонено",
    merged: "склеено",
    unverified: "без цитаты",
    questions: "вопросов",
    rewrites: "новых редакций",
  };
  return Object.entries(e)
    .filter(([k]) => !skip.has(k) && k in names)
    .map(([k, v]) => `${v} ${names[k]}`)
    .join(", ");
}

export function Progress({ runId, onDone, onRestart }: { runId: string; onDone: (r: Report) => void; onRestart: () => void }) {
  const [stages, setStages] = useState<Record<string, { state: StageState; note: string }>>({});
  const [log, setLog] = useState<{ text: string; warn?: boolean }[]>([]);
  const [failed, setFailed] = useState<string | null>(null);

  useEffect(() => {
    const stop = api.events(runId, (e) => {
      if (e.type === "stage") {
        const name = String(e.stage);
        setStages((s) => ({ ...s, [name]: { state: e.status === "done" ? "done" : "active", note: detail(e) } }));
      } else if (e.type === "llm_done" && !e.cached) {
        setLog((l) => [...l, { text: `${e.agent} · ${e.model} · ${e.duration_s} с · ${e.input_tokens}→${e.output_tokens} токенов` }]);
      } else if (e.type === "llm_retry") {
        setLog((l) => [...l, { text: `${e.agent}: ${e.reason}, повтор`, warn: true }]);
      } else if (e.type === "llm_fallback") {
        setLog((l) => [...l, { text: `${e.from}: ${e.reason}, переключаюсь на ${e.to ?? "—"}`, warn: true }]);
      } else if (e.type === "run" && e.status === "done") {
        api.report(runId).then(onDone).catch((err) => setFailed(String(err)));
      } else if (e.type === "run" && e.status === "failed") {
        setFailed(String(e.error));
      }
    });
    return stop;
  }, [runId, onDone]);

  const visible = STAGES.filter(([key]) => key !== "resolve" || stages.resolve);
  return (
    <main className="progress">
      <div className="wordmark">Revizorro</div>
      <h1>Идёт проверка документа</h1>
      <p className="muted">Агенты работают параллельно; страницу можно не держать открытой — результат сохранится по ссылке.</p>
      <ol className="stages" aria-live="polite">
        {visible.map(([key, name]) => {
          const st = stages[key]?.state ?? "pending";
          return (
            <li key={key} className={st}>
              <span className="stage-name">{name}</span>
              <span className="stage-state">
                {st === "done" ? stages[key].note || "готово" : st === "active" ? "идёт…" : "ожидает"}
              </span>
            </li>
          );
        })}
      </ol>
      {log.length > 0 && (
        <div className="calls">
          {log.map((l, i) => (
            <div key={i} className={l.warn ? "warn" : undefined}>
              {l.text}
            </div>
          ))}
        </div>
      )}
      {failed && (
        <>
          <p className="error">Проверка остановилась: {failed}</p>
          <button className="btn btn-quiet" onClick={onRestart}>
            Начать заново
          </button>
        </>
      )}
    </main>
  );
}
