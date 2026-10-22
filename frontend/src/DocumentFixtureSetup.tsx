import { useRef, useState } from "react";

type Props = {
  api: <T>(path: string, init?: RequestInit) => Promise<T>;
  onCreated: (projectId: string, managerId: string) => Promise<void>;
};

export function DocumentFixtureSetup({ api, onCreated }: Props) {
  const [name, setName] = useState("Document walkthrough");
  const [notes, setNotes] = useState("The review meeting needs an action list. Owners and dates are unknown.");
  const [busy, setBusy] = useState(false);
  const [started, setStarted] = useState(false);
  const [result, setResult] = useState("");
  const locked = useRef(false);
  return <section className="panel" aria-label="Document fixture walkthrough">
    <h2>Try the document workflow</h2>
    <p>Create a separate project, two synthetic agents, project execution grants and one backlog plan task.
      The plan is predefined; the draft quotes your notes. No paid model is used.</p>
    <form onSubmit={async (event) => {
      event.preventDefault();
      if (locked.current) return;
      locked.current = true;
      setBusy(true); setStarted(true);
      try {
        const created = await api<{ project_id: string; manager_id: string }>("/api/document-fixtures", {
          method: "POST", body: JSON.stringify({ name, notes }),
        });
        setResult(`Setup saved. Project: ${created.project_id}. Select its planner below and run the backlog plan task.`);
        await onCreated(created.project_id, created.manager_id);
      } catch (error) {
        setResult(`${error instanceof Error ? error.message : "Setup failed"}. Refresh and inspect Projects and Agents before trying again; a lost response may follow a saved setup.`);
      } finally { setBusy(false); }
    }}>
      <label>Walkthrough project name<input value={name} onChange={e => setName(e.target.value)}
        minLength={1} maxLength={120} required disabled={started} /></label>
      <label>Walkthrough source notes<textarea value={notes} onChange={e => setNotes(e.target.value)}
        minLength={1} maxLength={20000} rows={4} required disabled={started} /></label>
      <p className="muted">Use sample notes without credentials. Setup saves configuration only; it starts no execution.</p>
      <button disabled={started}>{busy ? "Saving fixture setup…" : "Create document fixture setup"}</button>
    </form>
    {result && <p role="status">{result}</p>}
    <ol>
      <li>Run the plan task with its planner; refresh until it reaches review.</li>
      <li>In Collaboration, inspect the recorded source and admit the exact plan.</li>
      <li>In Projects, request the reviewed draft fixture; refresh until review.</li>
      <li>In Approvals, inspect and approve the exact synthetic draft.</li>
      <li>In Artifacts, inspect saved output and source; return to Projects to accept the draft task.</li>
    </ol>
  </section>;
}
