import { EditOutlined, LikeOutlined, StopOutlined, UserOutlined } from "@ant-design/icons";
import { Alert, Button, Empty, Input, Progress, Radio, Tag } from "antd";
import { useMemo, useState } from "react";
import { RefList, RichText } from "../lib/refs";
import type { Question } from "../types";

const OWN = "__own__";

// A saved answer is either an option label ("A"), the phrase "Вариант A: ..." or free text.
function pickedLabel(q: Question, answer: string | undefined): string | null {
  if (!answer) return null;
  const label = /^Вариант\s+([^\s:.]+)/.exec(answer)?.[1] ?? answer.trim();
  return q.options.find((o) => o.label === label || o.answer === answer)?.label ?? null;
}

interface Props {
  questions: Question[];
  answered: Record<string, string>;
  rewrites: number;
  busy: boolean;
  problem: string | null;
  onSubmit: (answers: Record<string, string>) => void;
  onRewrites: () => void;
}

export function Questions({ questions, answered, rewrites, busy, problem, onSubmit, onRewrites }: Props) {
  // choice holds an option label or OWN; own holds free-text answers.
  const [choice, setChoice] = useState<Record<string, string>>(() =>
    Object.fromEntries(questions.filter((q) => answered[q.qid]).map((q) => [q.qid, pickedLabel(q, answered[q.qid]) ?? OWN])),
  );
  const [own, setOwn] = useState<Record<string, string>>(() =>
    Object.fromEntries(questions.filter((q) => answered[q.qid] && !pickedLabel(q, answered[q.qid])).map((q) => [q.qid, answered[q.qid]])),
  );

  const answers = useMemo(() => {
    const out: Record<string, string> = {};
    for (const q of questions) {
      const c = choice[q.qid];
      if (!c) continue;
      const value = c === OWN ? (own[q.qid] ?? "").trim() : c;
      if (value) out[q.qid] = value;
    }
    return out;
  }, [questions, choice, own]);
  const filled = Object.keys(answers).length;

  if (!questions.length) return <Empty description="Вопросов к авторам нет" />;

  return (
    <div className="questions">
      <div className="section-head">
        <h1>Вопросы авторам</h1>
        <p className="muted">
          Каждый вопрос — это решение, без которого нельзя исправить требования. Выберите вариант или впишите свой:
          агент перепишет затронутые требования и проверит новую редакцию. Первые вопросы снимают больше всего замечаний.
        </p>
      </div>

      {rewrites > 0 && (
        <Alert
          type="success"
          showIcon
          title={`По ответам переписано требований: ${rewrites}`}
          action={<Button onClick={onRewrites}>Смотреть новую редакцию</Button>}
        />
      )}
      {problem && <Alert type="error" showIcon title={problem} />}

      {questions.map((q) => (
        <section key={q.qid} id={`q-${q.qid}`} className={`qcard${answers[q.qid] ? " answered" : ""}`} aria-labelledby={`qt-${q.qid}`}>
          <div className="qcard-top">
            <span className="qcard-id">{q.qid}</span>
            <Tag icon={<UserOutlined />}>Кому: {q.addressee}</Tag>
            {q.finding_ids.length > 0 && <span className="muted">Ответ снимает замечания:</span>}
            <RefList ids={q.finding_ids} max={5} />
          </div>
          <h3 id={`qt-${q.qid}`}>{q.question}</h3>
          <p className="muted">
            <RichText text={q.why} />
          </p>

          <Radio.Group
            className="options"
            value={choice[q.qid]}
            onChange={(e) => setChoice((c) => ({ ...c, [q.qid]: e.target.value }))}
          >
            {q.options.map((o) => (
              <Radio key={o.label} value={o.label} className="option">
                <span className="option-answer">
                  <b>{o.label}.</b> {o.answer}
                  {o.label === q.recommended && (
                    <Tag color="success" icon={<LikeOutlined />} className="option-rec">
                      рекомендует агент
                    </Tag>
                  )}
                </span>
                <span className="option-cost">
                  <RichText text={o.consequence} />
                </span>
              </Radio>
            ))}
            <Radio value={OWN} className="option">
              <span className="option-answer">Свой вариант</span>
              {choice[q.qid] === OWN && (
                <Input.TextArea
                  autoSize={{ minRows: 2, maxRows: 6 }}
                  autoFocus
                  className="option-own"
                  placeholder="Опишите решение своими словами"
                  value={own[q.qid] ?? ""}
                  onChange={(e) => setOwn((o) => ({ ...o, [q.qid]: e.target.value }))}
                />
              )}
            </Radio>
          </Radio.Group>

          <div className="qcard-foot">
            {q.blocks_what && (
              <span className="muted">
                <StopOutlined /> Без ответа нельзя начать: {q.blocks_what.charAt(0).toLowerCase() + q.blocks_what.slice(1)}
              </span>
            )}
            {q.rids.length > 0 && (
              <span className="qcard-reqs">
                <span className="muted">Затронет требования:</span> <RefList ids={q.rids} max={6} />
              </span>
            )}
            {choice[q.qid] && (
              <Button
                type="link"
                size="small"
                onClick={() =>
                  setChoice((c) => {
                    const { [q.qid]: _dropped, ...rest } = c;
                    return rest;
                  })
                }
              >
                Снять ответ
              </Button>
            )}
          </div>
        </section>
      ))}

      <div className="answer-bar">
        <div className="answer-progress">
          <span>
            Отвечено {filled} из {questions.length}
          </span>
          <Progress percent={Math.round((filled / questions.length) * 100)} showInfo={false} size="small" />
        </div>
        <Button type="primary" size="large" icon={<EditOutlined />} loading={busy} disabled={filled === 0} onClick={() => onSubmit(answers)}>
          Переписать требования по ответам
        </Button>
        <span className="muted">Займёт около минуты: готовые результаты проверки берутся из кэша.</span>
      </div>
    </div>
  );
}
