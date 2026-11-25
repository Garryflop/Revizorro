import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { Progress } from "./components/Progress";
import { ReportView } from "./components/ReportView";
import { Start } from "./components/Start";
import type { Meta, Report } from "./types";

type View =
  | { name: "start" }
  | { name: "progress"; runId: string }
  | { name: "report"; runId: string; report: Report };

// Run id lives in the URL hash so a reload or a shared link reopens the same result.
const runFromHash = () => /^#\/run\/([\w-]+)/.exec(window.location.hash)?.[1] ?? null;

export function App() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [view, setView] = useState<View>({ name: "start" });
  const [error, setError] = useState<string | null>(null);

  const openRun = useCallback(async (runId: string) => {
    window.location.hash = `#/run/${runId}`;
    try {
      const run = await api.run(runId);
      if (run.status === "done") setView({ name: "report", runId, report: await api.report(runId) });
      else setView({ name: "progress", runId });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setView({ name: "start" });
    }
  }, []);

  useEffect(() => {
    api.meta().then(setMeta).catch((e) => setError(`API недоступен: ${e.message}. Запустите revizorro-api.`));
    const id = runFromHash();
    if (id) void openRun(id);
  }, [openRun]);

  const restart = () => {
    window.location.hash = "";
    setView({ name: "start" });
  };

  if (view.name === "progress") {
    return (
      <Progress
        runId={view.runId}
        onDone={(report) => setView({ name: "report", runId: view.runId, report })}
        onRestart={restart}
      />
    );
  }
  if (view.name === "report" && meta) {
    return <ReportView report={view.report} meta={meta} runId={view.runId} onRestart={restart} onRun={openRun} />;
  }
  return <Start meta={meta} error={error} onRun={openRun} />;
}
