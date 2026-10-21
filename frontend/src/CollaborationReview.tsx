import { useEffect, useState } from "react";
import { RunBriefSource } from "./RunBriefSource";

type Proposal = {
  id: string;
  kind: "plan" | "delegation" | "message";
  status: string;
  source_execution_id: string;
  payload_hash: string;
  payload: Record<string, unknown>;
  admitted_ref: string | null;
};

type Props = {
  projectId: string;
  projectName: string;
  api: <T>(path: string, init?: RequestInit) => Promise<T>;
  onError: (message: string) => void;
};

export function CollaborationReview({ projectId, projectName, api, onError }: Props) {
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [busy, setBusy] = useState(false);

  async function load() {
    if (!projectId) {
      setProposals([]);
      return;
    }
    setProposals(await api<Proposal[]>(
      `/api/collaboration-proposals?project_id=${encodeURIComponent(projectId)}`,
    ));
  }

  useEffect(() => {
    let current = true;
    if (!projectId) {
      setProposals([]);
      return;
    }
    api<Proposal[]>(`/api/collaboration-proposals?project_id=${encodeURIComponent(projectId)}`)
      .then((rows) => { if (current) setProposals(rows); })
      .catch((error) => {
        if (current) onError(error instanceof Error ? error.message : "Review unavailable");
      });
    return () => { current = false; };
  }, [projectId]);

  async function decide(proposal: Proposal, approved: boolean) {
    setBusy(true);
    try {
      await api(`/api/collaboration-proposals/${proposal.id}/decision`, {
        method: "POST",
        body: JSON.stringify({ approved, payload_hash: proposal.payload_hash }),
      });
      await load();
    } catch (error) {
      onError(error instanceof Error ? error.message : "Decision failed");
    } finally {
      setBusy(false);
    }
  }

  const pending = proposals.filter((proposal) => proposal.status === "pending");
  return (
    <section className="panel">
      <h2>Collaboration proposals</h2>
      <p className="muted">
        Review untrusted agent output for {projectName || "the selected project"}.
        Approval rechecks project access, budget, scope and limits before any work is admitted.
      </p>
      <button className="quiet" onClick={() => load().catch((error) => onError(error.message))}>
        Refresh proposals
      </button>
      {!projectId || pending.length === 0 ? (
        <p className="empty">No pending collaboration proposals.</p>
      ) : (
        pending.map((proposal) => (
          <div className="row" key={proposal.id}>
            <div>
              <strong>{proposal.kind}</strong>
              <small>Source execution: {proposal.source_execution_id}</small>
              {proposal.kind === "plan" && proposal.payload.document_source != null && <>
                <p>Source-bound document plan. Review the recorded brief and prepared prefix before admitting work.</p>
                <p className="muted">Admission creates backlog tasks only. Each reviewed draft fixture requires a separate request and exact output approval.</p>
                <RunBriefSource key={proposal.source_execution_id} executionId={proposal.source_execution_id}
                  projectId={projectId} api={api} />
              </>}
              <pre className="proposal-content">{JSON.stringify(proposal.payload, null, 2)}</pre>
              <small>SHA-256 proposal: {proposal.payload_hash}</small>
            </div>
            <div className="actions">
              <button className="quiet" disabled={busy} onClick={() => decide(proposal, true)}>
                Admit proposal
              </button>
              <button className="quiet" disabled={busy} onClick={() => decide(proposal, false)}>
                Reject
              </button>
            </div>
          </div>
        ))
      )}
    </section>
  );
}
