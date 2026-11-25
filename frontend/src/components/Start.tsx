import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { Meta } from "../types";

const ACCEPT = ".pdf,.docx,.md,.markdown,.txt";

export function Start({ meta, error, onRun }: { meta: Meta | null; error: string | null; onRun: (id: string) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(error);
  const [model, setModel] = useState("");
  const [strong, setStrong] = useState("");
  const [defaults, setDefaults] = useState<{ d?: string; s?: string }>({});

  useEffect(() => setProblem(error), [error]);
  useEffect(() => {
    api
      .health()
      .then((h) => (h.ok ? setDefaults({ d: h.model_default, s: h.model_strong }) : setProblem(h.error ?? null)))
      .catch(() => undefined);
  }, []);

  const launch = async (start: () => Promise<{ id: string }>) => {
    setBusy(true);
    setProblem(null);
    try {
      onRun((await start()).id);
    } catch (e) {
      setProblem(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };
  const upload = (file: File | undefined) => {
    if (file) void launch(() => api.startUpload(file, model || undefined, strong || undefined));
  };

  return (
    <main className="start">
      <div className="wordmark">Revizorro</div>
      <h1>Ревизия ТЗ до того, как по нему начнут писать код</h1>
      <p className="lede">
        Агент разбирает документ на требования, проверяет каждое и весь набор по ISO/IEC/IEEE 29148 и IEEE 830,
        подтверждает противоречия контрпримерами и задаёт авторам вопросы с вариантами ответа.
      </p>

      <div
        className={`drop${over ? " over" : ""}`}
        role="button"
        tabIndex={0}
        aria-label="Выбрать файл с требованиями"
        onClick={() => input.current?.click()}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          upload(e.dataTransfer.files[0]);
        }}
      >
        <div className="page-lines">
          <strong>{busy ? "Загружаю документ…" : "Перетащите сюда документ с требованиями"}</strong>
          <br />
          или нажмите, чтобы выбрать файл.
          <br />
          PDF, DOCX, Markdown или текст.
        </div>
        <input ref={input} type="file" accept={ACCEPT} hidden onChange={(e) => upload(e.target.files?.[0])} />
      </div>

      <div className="start-actions">
        {meta?.example && (
          <button className="btn btn-quiet" disabled={busy} onClick={() => launch(() => api.startExample(model || undefined, strong || undefined))}>
            Проверить пример: «Уведомление о расходах по карте»
          </button>
        )}
        <span className="muted">Проверка занимает 3–8 минут.</span>
      </div>
      {problem && <p className="error">{problem}</p>}

      <div className="models">
        <label>
          Модель для массовых шагов
          <input value={model} placeholder={defaults.d ?? "из .env"} onChange={(e) => setModel(e.target.value)} />
        </label>
        <label>
          Модель для проверки набора и итога
          <input value={strong} placeholder={defaults.s ?? "из .env"} onChange={(e) => setStrong(e.target.value)} />
        </label>
      </div>
    </main>
  );
}
