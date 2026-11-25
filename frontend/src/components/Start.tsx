import { ClockCircleOutlined, InboxOutlined, PlayCircleOutlined, SettingOutlined } from "@ant-design/icons";
import { Alert, Button, Collapse, Input, Steps, Upload } from "antd";
import { useEffect, useState } from "react";
import { api } from "../api";
import type { Meta } from "../types";
import { Brand } from "./Brand";

const ACCEPT = ".pdf,.docx,.md,.markdown,.txt,.json";

const HOW = [
  {
    title: "Загружаете документ",
    content: "ТЗ, спецификация или постановка задачи: PDF, DOCX, Markdown или текст.",
  },
  {
    title: "Агенты проверяют",
    content:
      "Делят текст на требования, проверяют каждое и весь набор по ISO/IEC/IEEE 29148 и IEEE 830, пробуют написать по ним тест-кейсы.",
  },
  {
    title: "Получаете результат",
    content: "Вердикт о готовности к разработке и замечания с цитатой из документа и способом исправить.",
  },
  {
    title: "Отвечаете на вопросы",
    content: "Агент предлагает варианты решения, переписывает требования по вашему выбору и проверяет новую редакцию.",
  },
];

export function Start({ meta, error, onRun }: { meta: Meta | null; error: string | null; onRun: (id: string) => void }) {
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

  return (
    <div className="screen">
      <header className="bar">
        <Brand />
      </header>
      <main className="start">
        <section className="start-main">
          <h1>Проверьте ТЗ до того, как по нему начнут писать код</h1>
          <p className="lede">
            Revizorro находит противоречия, пробелы и непроверяемые формулировки в требованиях и показывает, что
            исправить и что уточнить у авторов.
          </p>

          <Upload.Dragger
            accept={ACCEPT}
            multiple={false}
            showUploadList={false}
            disabled={busy}
            beforeUpload={(file) => {
              void launch(() => api.startUpload(file, model || undefined, strong || undefined));
              return false; // the file goes through our API call, not antd's uploader
            }}
          >
            <p className="ant-upload-drag-icon">
              <InboxOutlined />
            </p>
            <p className="ant-upload-text">{busy ? "Загружаю документ…" : "Перетащите файл с требованиями сюда"}</p>
            <p className="ant-upload-hint">
              или нажмите, чтобы выбрать. PDF, DOCX, Markdown, TXT.
              <br />
              Сохранённый отчёт report.json откроется сразу, без повторной проверки.
            </p>
          </Upload.Dragger>

          {meta?.example && (
            <div className="example">
              <Button
                icon={<PlayCircleOutlined />}
                size="large"
                disabled={busy}
                onClick={() => launch(() => api.startExample(model || undefined, strong || undefined))}
              >
                Проверить пример
              </Button>
              <span className="muted">
                Учебное ТЗ «Уведомление о расходах по карте»: функциональные требования и описание REST API.
              </span>
            </div>
          )}

          <p className="muted start-time">
            <ClockCircleOutlined /> Проверка занимает 5–10 минут. Повторная проверка того же файла берётся из кэша и занимает секунды.
          </p>

          {problem && <Alert type="error" showIcon title={problem} className="start-error" />}

          <Collapse
            ghost
            size="small"
            className="start-models"
            items={[
              {
                key: "models",
                label: (
                  <span className="muted">
                    <SettingOutlined /> Модели
                  </span>
                ),
                children: (
                  <div className="models">
                    <label>
                      Для массовых шагов: проверка требований, тест-кейсы
                      <Input value={model} placeholder={defaults.d ?? "из .env"} onChange={(e) => setModel(e.target.value)} />
                    </label>
                    <label>
                      Для сложных шагов: нарезка, проверка набора, критик, вопросы, итог
                      <Input value={strong} placeholder={defaults.s ?? "из .env"} onChange={(e) => setStrong(e.target.value)} />
                    </label>
                  </div>
                ),
              },
            ]}
          />
        </section>

        <aside className="start-how" aria-label="Как это работает">
          <h2>Как это работает</h2>
          <Steps orientation="vertical" size="small" items={HOW.map((s) => ({ ...s, status: "process" as const }))} />
        </aside>
      </main>
    </div>
  );
}
