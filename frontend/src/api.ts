import type { Meta, Report, RunEvent, RunSummary } from "./types";

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      // keep status text
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  meta: () => fetch("/api/meta").then((r) => json<Meta>(r)),
  health: () =>
    fetch("/api/health").then((r) =>
      json<{ ok: boolean; error?: string; model_default?: string; model_strong?: string }>(r),
    ),

  startUpload(file: File, model?: string, strongModel?: string) {
    const form = new FormData();
    form.append("file", file);
    if (model) form.append("model", model);
    if (strongModel) form.append("strong_model", strongModel);
    return fetch("/api/runs", { method: "POST", body: form }).then((r) => json<RunSummary>(r));
  },

  startExample(model?: string, strongModel?: string) {
    const qs = new URLSearchParams();
    if (model) qs.set("model", model);
    if (strongModel) qs.set("strong_model", strongModel);
    return fetch(`/api/runs/example?${qs}`, { method: "POST" }).then((r) => json<RunSummary>(r));
  },

  run: (id: string) => fetch(`/api/runs/${id}`).then((r) => json<RunSummary>(r)),
  report: (id: string) => fetch(`/api/runs/${id}/report`).then((r) => json<Report>(r)),

  answer(id: string, answers: Record<string, string>) {
    return fetch(`/api/runs/${id}/answers`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answers }),
    }).then((r) => json<RunSummary>(r));
  },

  events(id: string, onEvent: (e: RunEvent) => void): () => void {
    const source = new EventSource(`/api/runs/${id}/events`);
    const handler = (msg: MessageEvent) => {
      try {
        onEvent(JSON.parse(msg.data) as RunEvent);
      } catch {
        // ignore malformed frames
      }
    };
    for (const type of ["stage", "llm_start", "llm_done", "llm_retry", "llm_fallback", "run"]) {
      source.addEventListener(type, handler as EventListener);
    }
    source.onerror = () => source.close();
    return () => source.close();
  },
};
