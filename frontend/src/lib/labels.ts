import type { Decision, Finding, Severity } from "../types";

export const SEV_ORDER: Severity[] = ["critical", "major", "minor"];
export const SEV_RANK: Record<Severity, number> = { critical: 0, major: 1, minor: 2 };
export const SEV_PLURAL: Record<Severity, string> = {
  critical: "Критичные",
  major: "Существенные",
  minor: "Незначительные",
};

export const DECISION_SHORT: Record<Decision, string> = {
  ready: "Готов к разработке",
  ready_after_fixes: "Готов после исправлений",
  not_ready: "Не готов к разработке",
};

export const AGENT: Record<string, string> = {
  reviewer: "Ревьюер требований",
  test_designer: "Тест-дизайнер",
  consistency: "Ревьюер согласованности",
  completeness: "Ревьюер полноты",
  api_contract: "Ревьюер контракта API",
  linter: "Правила в коде",
};

export const TECHNIQUE: Record<string, string> = {
  boundary: "граничные значения",
  equivalence: "классы эквивалентности",
  negative: "негативный сценарий",
  scenario: "сценарий",
  state_transition: "переходы состояний",
  decision_table: "таблица решений",
};

// Russian plural form: plural(3, ["замечание", "замечания", "замечаний"]) -> "замечания"
export function plural(n: number, forms: [string, string, string]): string {
  const a = Math.abs(n) % 100;
  const b = a % 10;
  if (a > 10 && a < 20) return forms[2];
  if (b > 1 && b < 5) return forms[1];
  if (b === 1) return forms[0];
  return forms[2];
}

export const W_FINDING: [string, string, string] = ["замечание", "замечания", "замечаний"];
export const W_QUESTION: [string, string, string] = ["вопрос", "вопроса", "вопросов"];
export const W_REQUIREMENT: [string, string, string] = ["требование", "требования", "требований"];

export function worst(findings: Finding[]): Severity | null {
  return findings.reduce<Severity | null>(
    (w, f) => (w === null || SEV_RANK[f.severity] < SEV_RANK[w] ? f.severity : w),
    null,
  );
}

export function countBySeverity(findings: Finding[]): Record<Severity, number> {
  const c: Record<Severity, number> = { critical: 0, major: 0, minor: 0 };
  for (const f of findings) c[f.severity] += 1;
  return c;
}
