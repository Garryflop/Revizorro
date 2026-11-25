import { useState } from "react";
import type { Question, Requirement } from "../types";
import { reqLabel } from "./FindingItem";

interface Props {
  questions: Question[];
  reqs: Map<string, Requirement>;
  answered: Record<string, string>;
  busy: boolean;
  onSubmit: (answers: Record<string, string>) => void;
}

export function Questions({ questions, reqs, answered, busy, onSubmit }: Props) {
  const [answers, setAnswers] = useState<Record<string, string>>(answered);
  const [own, setOwn] = useState<Record<string, string>>({});
  const filled = Object.values(answers).filter((v) => v.trim()).length;

  if (!questions.length) return <p className="muted">Вопросов к авторам нет.</p>;
  const set = (qid: string, value: string) => setAnswers((a) => ({ ...a, [qid]: value }));

  return (
    <>
      <p className="muted">
        Выберите вариант или впишите свой ответ. Агент перепишет затронутые требования и проверит новую редакцию.
      </p>
      {questions.map((q) => {
        const isOwn = answers[q.qid] !== undefined && !q.options.some((o) => o.label === answers[q.qid]);
        return (
          <section key={q.qid} className="question" aria-labelledby={`q-${q.qid}`}>
            <div className="to">
              {q.qid}, вопрос для роли «{q.addressee}»
              {q.rids.length > 0 && `, затрагивает ${q.rids.slice(0, 5).map((r) => reqLabel(r, reqs)).join(", ")}`}
            </div>
            <h3 id={`q-${q.qid}`}>{q.question}</h3>
            <p className="why">{q.why}</p>
            {q.options.map((o) => (
              <label key={o.label} className="option">
                <input
                  type="radio"
                  name={q.qid}
                  checked={answers[q.qid] === o.label}
                  onChange={() => set(q.qid, o.label)}
                />
                <span>
                  <b>{o.label}.</b> {o.answer}
                  {o.label === q.recommended && <span className="rec">рекомендуется</span>}
                </span>
                <span className="consequence">{o.consequence}</span>
              </label>
            ))}
            <label className="option">
              <input type="radio" name={q.qid} checked={isOwn} onChange={() => set(q.qid, own[q.qid] ?? "")} />
              <span>Свой ответ</span>
              <span className="consequence" style={{ gridColumn: "2" }}>
                <input
                  className="own"
                  value={own[q.qid] ?? (isOwn ? answers[q.qid] : "")}
                  placeholder="Ваш вариант решения"
                  onChange={(e) => {
                    setOwn((o) => ({ ...o, [q.qid]: e.target.value }));
                    set(q.qid, e.target.value);
                  }}
                />
              </span>
            </label>
            {q.blocks_what && <p className="muted">Без ответа блокируется: {q.blocks_what}</p>}
          </section>
        );
      })}
      <div className="answer-bar">
        <button className="btn" disabled={busy || filled === 0} onClick={() => onSubmit(answers)}>
          {busy ? "Отправляю ответы…" : `Переписать требования по ответам (${filled})`}
        </button>
        <span className="muted">Повторный прогон использует кэш и занимает около минуты.</span>
      </div>
    </>
  );
}
