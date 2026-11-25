import { LoadingOutlined } from "@ant-design/icons";
import { Alert, Button, Collapse, Progress as Bar, Steps } from "antd";
import { useEffect, useState } from "react";
import { api } from "../api";
import type { Report, RunEvent } from "../types";
import { Brand } from "./Brand";

// Stage key, title, what happens there.
const STAGES: [string, string, string][] = [
  ["ingest", "Чтение документа", "Документ делится на фрагменты с адресом: раздел, строка, страница."],
  ["segment", "Выделение требований", "Агент-нарезчик находит отдельные требования и привязывает каждое к цитате."],
  [
    "review",
    "Проверка",
    "Параллельно работают ревьюер требований, тест-дизайнер и ревьюеры набора: согласованность, полнота, контракт API.",
  ],
  ["verify", "Перепроверка", "Код сверяет каждую цитату с документом, критик отсеивает ложные и повторные замечания."],
  ["clarify", "Вопросы авторам", "Агент готовит вопросы с вариантами ответа и последствиями каждого варианта."],
  ["resolve", "Новая редакция", "По ответам агент переписывает требования и проверяет их повторно."],
  ["summarize", "Итог", "Вердикт о готовности и порядок исправлений."],
];

type StageState = "pending" | "active" | "done";

function detail(e: RunEvent): string {
  const names: Record<string, string> = {
    blocks: "фрагментов",
    requirements: "требований",
    findings: "замечаний",
    kept: "подтверждено",
    rejected: "отклонено",
    merged: "объединено",
    unverified: "без цитаты",
    questions: "вопросов",
    rewrites: "новых редакций",
  };
  return Object.entries(e)
    .filter(([k]) => k in names)
    .map(([k, v]) => `${v} ${names[k]}`)
    .join(", ");
}

const clock = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

export function Progress({ runId, onDone, onRestart }: { runId: string; onDone: (r: Report) => void; onRestart: () => void }) {
  const [stages, setStages] = useState<Record<string, { state: StageState; note: string }>>({});
  const [log, setLog] = useState<{ text: string; warn?: boolean }[]>([]);
  const [failed, setFailed] = useState<string | null>(null);
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    const stop = api.events(runId, (e) => {
      if (e.type === "stage") {
        const name = String(e.stage);
        setStages((s) => ({ ...s, [name]: { state: e.status === "done" ? "done" : "active", note: detail(e) } }));
      } else if (e.type === "llm_done" && !e.cached) {
        setLog((l) => [...l, { text: `${e.agent}, ${e.model}: ${e.duration_s} с, ${e.input_tokens} → ${e.output_tokens} токенов` }]);
      } else if (e.type === "llm_retry") {
        setLog((l) => [...l, { text: `${e.agent}: ${e.reason}, повтор`, warn: true }]);
      } else if (e.type === "llm_fallback") {
        setLog((l) => [...l, { text: `${e.from}: ${e.reason}, переключаюсь на ${e.to ?? "нет запасной модели"}`, warn: true }]);
      } else if (e.type === "run" && e.status === "done") {
        api.report(runId).then(onDone).catch((err) => setFailed(String(err)));
      } else if (e.type === "run" && e.status === "failed") {
        setFailed(String(e.error));
      }
    });
    return stop;
  }, [runId, onDone]);

  useEffect(() => {
    if (failed) return;
    const t = window.setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => window.clearInterval(t);
  }, [failed]);

  const visible = STAGES.filter(([key]) => key !== "resolve" || stages.resolve);
  const done = visible.filter(([key]) => stages[key]?.state === "done").length;
  const activeIndex = visible.findIndex(([key]) => stages[key]?.state === "active");

  return (
    <div className="screen">
      <header className="bar">
        <Brand onClick={onRestart} />
      </header>
      <main className="progress">
        <h1>{failed ? "Проверка остановилась" : "Идёт проверка документа"}</h1>
        <p className="muted">
          Прошло {clock(seconds)}. Вкладку можно закрыть: результат сохранится по этой же ссылке.
        </p>
        <Bar percent={Math.round((done / visible.length) * 100)} status={failed ? "exception" : "active"} showInfo={false} />

        <Steps
          className="stages"
          orientation="vertical"
          size="small"
          current={activeIndex < 0 ? done : activeIndex}
          status={failed ? "error" : "process"}
          items={visible.map(([key, title, what]) => {
            const st = stages[key]?.state ?? "pending";
            return {
              title,
              content: st === "done" && stages[key].note ? `${what} Результат: ${stages[key].note}.` : what,
              status: st === "done" ? ("finish" as const) : st === "active" ? ("process" as const) : ("wait" as const),
              icon: st === "active" && !failed ? <LoadingOutlined /> : undefined,
            };
          })}
        />

        {failed && (
          <Alert
            type="error"
            showIcon
            title="Не удалось закончить проверку"
            description={failed}
            action={<Button onClick={onRestart}>Начать заново</Button>}
          />
        )}

        {log.length > 0 && (
          <Collapse
            ghost
            size="small"
            items={[
              {
                key: "log",
                label: <span className="muted">Обращения к модели: {log.length}</span>,
                children: (
                  <div className="calls">
                    {log.map((l, i) => (
                      <div key={i} className={l.warn ? "warn" : undefined}>
                        {l.text}
                      </div>
                    ))}
                  </div>
                ),
              },
            ]}
          />
        )}
      </main>
    </div>
  );
}
