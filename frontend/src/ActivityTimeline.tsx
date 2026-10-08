import { useEffect, useState } from "react";

type Activity = {
  sequence: number;
  action: string;
  resource: string;
  outcome: string;
  created_at: string;
};

type Props = {
  projectId: string;
  api: <T>(path: string, init?: RequestInit) => Promise<T>;
  onError: (message: string) => void;
};

export function ActivityTimeline({ projectId, api, onError }: Props) {
  const [rows, setRows] = useState<Activity[]>([]);
  const [connection, setConnection] = useState("connecting");

  useEffect(() => {
    let active = true;
    let source: EventSource | null = null;
    setRows([]);
    setConnection("connecting");
    if (!projectId) return;
    const base = `/api/projects/${encodeURIComponent(projectId)}/activity`;
    api<Activity[]>(base).then((initial) => {
      if (!active) return;
      setRows(initial);
      const cursor = initial.at(-1)?.sequence ?? 0;
      source = new EventSource(`${base}/stream?after=${cursor}`);
      source.onopen = () => { if (active) setConnection("live"); };
      source.onerror = () => { if (active) setConnection("reconnecting"); };
      source.addEventListener("activity", (event) => {
        if (!active) return;
        const row = JSON.parse((event as MessageEvent).data) as Activity;
        setRows((current) => current.some((item) => item.sequence === row.sequence)
          ? current : [...current, row].slice(-100));
      });
    }).catch((error) => {
      if (active) onError(error instanceof Error ? error.message : "Activity unavailable");
    });
    return () => {
      active = false;
      source?.close();
    };
  }, [projectId]);

  return (
    <section className="panel">
      <h2>Project activity</h2>
      <p className="muted">Persisted events for the selected project · {connection}</p>
      {rows.length === 0 ? <p className="empty">No project activity yet.</p> : rows.map((row) => (
        <div className="row" key={row.sequence}>
          <div>
            <strong>{row.action}</strong>
            <small>{row.resource} · {new Date(row.created_at).toLocaleString()}</small>
          </div>
          <span className="badge">{row.outcome}</span>
        </div>
      ))}
    </section>
  );
}
