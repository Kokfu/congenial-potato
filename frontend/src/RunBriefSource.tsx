import { useEffect, useState } from "react";

type Source = { status: "unpinned" } | {
  status: "pinned"; project_id: string; revision: number; digest: string; content: string;
};
type Props = {
  executionId: string;
  projectId: string;
  api: <T>(path: string, init?: RequestInit) => Promise<T>;
};

export function RunBriefSource({ executionId, projectId, api }: Props) {
  const [source, setSource] = useState<Source | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    api<Source>(`/api/executions/${encodeURIComponent(executionId)}/brief`, { signal: controller.signal })
      .then((row) => {
        if (controller.signal.aborted) return;
        if (row.status === "pinned" && row.project_id !== projectId) throw Error("Source project mismatch");
        setSource(row);
      }).catch((e) => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [api, executionId, projectId]);
  return <section aria-label="Run source brief">
    {error && <p role="alert">Could not read recorded source: {error}</p>}
    {!source && !error && <p>Loading recorded source…</p>}
    {source?.status === "unpinned" && <p>No source brief was recorded for this older run.</p>}
    {source?.status === "pinned" && <details>
      <summary>Recorded source brief · revision {source.revision}</summary>
      <p className="muted">Recorded when the run was admitted. Fixture generation does not use these notes.</p>
      <p className="brief-digest">SHA-256: <code>{source.digest}</code></p>
      <pre aria-label="Run source content">{source.content || "(Empty brief)"}</pre>
    </details>}
  </section>;
}
