// Mirrors the backend Report JSON (revizorro.domain.models).

export type Severity = "critical" | "major" | "minor";
export type Decision = "ready" | "ready_after_fixes" | "not_ready";

export interface Block {
  id: string;
  kind: "heading" | "paragraph" | "list_item" | "table_header" | "table_row" | "code";
  text: string;
  section: string[];
  line_start: number;
  line_end: number;
  page: number | null;
  heading_level: number | null;
}

export interface Requirement {
  rid: string;
  source_id: string | null;
  source_ref: string;
  kind: string;
  summary: string;
  quote: string;
  block_ids: string[];
  traces_to: string[];
}

export interface Location {
  block_id: string;
  quote: string;
  label: string;
  verified?: boolean;
}

export interface Unassessable {
  rid: string;
  criterion: string;
  reason: string;
}

export interface Scenario {
  preconditions: string;
  steps: string[];
  outcomes: { basis: string; result: string }[];
}

export interface Finding {
  fid: string;
  scope: "requirement" | "set";
  rid: string | null;
  related_rids: string[];
  criterion: string;
  severity: Severity;
  title: string;
  problem: string;
  impact: string;
  suggestion: string;
  locations: Location[];
  counterexample: Scenario | null;
  source_agent: string;
  status: "kept" | "rejected" | "merged" | "unverified";
  critic_note: string;
  merged_into: string | null;
  merged_from: string[];
}

export interface TestProbe {
  rid: string;
  technique: string;
  title: string;
  preconditions: string;
  steps: string[];
  expected: string;
  derivable: boolean;
  blocker: string;
}

export interface QuestionOption {
  label: string;
  answer: string;
  consequence: string;
}

export interface Question {
  qid: string;
  addressee: string;
  question: string;
  why: string;
  options: QuestionOption[];
  recommended: string | null;
  finding_ids: string[];
  rids: string[];
  blocks_what: string;
  priority?: number;
}

export interface Rewrite {
  rid: string;
  old: string;
  new: string;
  resolved_fids: string[];
  remaining: Finding[];
}

export interface Resolution {
  qid: string;
  answer: string;
  rewrites: Rewrite[];
}

export interface Verdict {
  decision: Decision;
  development: string;
  testing: string;
  rationale: string;
  first_fixes: { action: string; refs: string[] }[];
  can_start_now: string[];
}

export interface Passport {
  document_title: string;
  source_file: string;
  source_format: string;
  sha256?: string;
  prompts_version?: string;
  started_at: string;
  duration_s: number;
  model_default: string;
  model_strong: string;
  models_used: string[];
  agent_version: string;
  llm_calls: number;
  cached_calls: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number | null;
}

export interface Report {
  passport: Passport;
  document: { title: string; blocks: Block[] };
  requirements: Requirement[];
  context_blocks: string[];
  template_blocks: string[];
  unclassified_blocks: string[];
  segmentation_notes: string[];
  findings: Finding[];
  unassessable: Unassessable[];
  probes: TestProbe[];
  questions: Question[];
  resolutions: Resolution[];
  verdict: Verdict;
}

export interface Meta {
  criteria: Record<string, { name: string; source: string; violation?: string }>;
  individual: string[];
  set: string[];
  severity: Record<Severity, string>;
  kind: Record<string, string>;
  decision: Record<Decision, string>;
  example: boolean;
}

export interface RunSummary {
  id: string;
  filename: string;
  status: "queued" | "running" | "done" | "failed";
  error: string | null;
  model_default: string;
  model_strong: string;
  answers: Record<string, string>;
}

export interface RunEvent {
  type: string;
  [key: string]: unknown;
}
