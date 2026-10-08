import { useEffect, useState } from "react";

type Invocation = {
  id: string;
  action: string;
  resource: string;
  arguments: Record<string, unknown>;
  status: string;
  approval: {
    id: string;
    status: string;
    payload_hash: string;
    target_version: string | null;
    expires_at: string;
  } | null;
};

type Props = {
  projectId: string;
  api: <T>(path: string, init?: RequestInit) => Promise<T>;
  onError: (message: string) => void;
};

export function ToolReview({ projectId, api, onError }: Props) {
  const [invocations, setInvocations] = useState<Invocation[]>([]);
  const [busy, setBusy] = useState(false);

  async function load() {
    if (!projectId) {
      setInvocations([]);
      return;
    }
    setInvocations(await api<Invocation[]>(
      `/api/tool-invocations?project_id=${encodeURIComponent(projectId)}`,
    ));
  }

  useEffect(() => {
    let current = true;
    if (!projectId) {
      setInvocations([]);
      return;
    }
    api<Invocation[]>(`/api/tool-invocations?project_id=${encodeURIComponent(projectId)}`)
      .then((rows) => { if (current) setInvocations(rows); })
      .catch((error) => {
        if (current) onError(error instanceof Error ? error.message : "Tool review unavailable");
      });
    return () => { current = false; };
  }, [projectId]);

  async function decide(row: Invocation, approved: boolean) {
    if (!row.approval) return;
    setBusy(true);
    try {
      await api(`/api/tool-invocations/${row.id}/decision`, {
        method: "POST",
        body: JSON.stringify({ approved, payload_hash: row.approval.payload_hash }),
      });
      await load();
    } catch (error) {
      onError(error instanceof Error ? error.message : "Tool decision failed");
    } finally {
      setBusy(false);
    }
  }

  const pending = invocations.filter((row) =>
    row.status === "awaiting_approval" && row.approval?.status === "pending"
  );
  return (
    <section className="panel">
      <h2>Tool approvals</h2>
      <p className="muted">
        Review exact arguments and the target resource. Approval authorizes one
        invocation; execution and its result are tracked separately.
      </p>
      <button className="quiet" onClick={() => load().catch((error) => onError(error.message))}>
        Refresh tool approvals
      </button>
      {!projectId || pending.length === 0 ? (
        <p className="empty">No pending tool approvals for this project.</p>
      ) : pending.map((row) => (
        <div className="row" key={row.id}>
          <div>
            <strong>{row.action}</strong>
            <small>Resource: {row.resource}</small>
            <pre className="proposal-content">{JSON.stringify(row.arguments, null, 2)}</pre>
            <small>Target version: {row.approval?.target_version ?? "new resource"}</small>
            <small>Expires: {row.approval?.expires_at}</small>
            <small>SHA-256 approval: {row.approval?.payload_hash}</small>
          </div>
          <div className="actions">
            <button className="quiet" disabled={busy} onClick={() => decide(row, true)}>
              Approve tool
            </button>
            <button className="quiet" disabled={busy} onClick={() => decide(row, false)}>
              Reject tool
            </button>
          </div>
        </div>
      ))}
    </section>
  );
}
