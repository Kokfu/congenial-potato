import { useEffect, useRef, useState } from "react";

type Version = { project_id: string; revision: number; digest: string; actor: string; created_at: string };
type Brief = Version & { content: string };
type Props = {
  projectId: string;
  api: <T>(path: string, init?: RequestInit) => Promise<T>;
  onSaved: () => Promise<void>;
};

export function ProjectBrief({ projectId, api, onSaved }: Props) {
  const [versions, setVersions] = useState<Version[]>([]);
  const [selected, setSelected] = useState(0);
  const [brief, setBrief] = useState<Brief | null>(null);
  const [draft, setDraft] = useState<{ content: string; expected_revision: number } | null>(null);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  const [saving, setSaving] = useState(false);
  const [older, setOlder] = useState(false);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const generation = useRef(0);
  const path = `/api/projects/${encodeURIComponent(projectId)}`;

  useEffect(() => {
    generation.current += 1;
    const controller = new AbortController();
    setLoadingOlder(false);
    setOlder(false);
    setBrief(null);
    setVersions([]);
    setSelected(0);
    setError("");
    api<Version[]>(`${path}/briefs`, { signal: controller.signal }).then((rows) => {
      if (controller.signal.aborted) return;
      setVersions(rows);
      setSelected(rows[0]?.revision ?? 0);
      setOlder(rows.length === 50);
    }).catch((e) => { if (!controller.signal.aborted) setError(e.message); });
    return () => { controller.abort(); generation.current += 1; };
  }, [api, path, reload]);

  useEffect(() => {
    const controller = new AbortController();
    setBrief(null);
    if (!selected) return () => controller.abort();
    api<Brief>(`${path}/briefs/${selected}`, { signal: controller.signal }).then((row) => {
      if (controller.signal.aborted) return;
      if (row.project_id !== projectId || row.revision !== selected) throw Error("Brief scope mismatch");
      setBrief(row);
    }).catch((e) => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [api, path, projectId, selected, reload]);

  const current = brief && brief.revision === versions[0]?.revision;
  return <section className="project-brief" aria-label="Selected project brief">
    <h3>Saved project brief</h3>
    <p className="muted">Source notes are quoted as untrusted data in bounded fixture context. Outputs remain synthetic.</p>
    <button className="quiet" disabled={saving} onClick={() => setReload((n) => n + 1)}>Reload brief history</button>
    {error && <p role="alert" className="error">{error}</p>}
    {versions.length > 0 && <label className="run-agent">
      Brief revision
      <select aria-label="Brief revision" value={selected} onChange={(e) => { setError(""); setSelected(Number(e.target.value)); }}>
        {versions.map((v) => <option key={v.revision} value={v.revision}>Revision {v.revision}</option>)}
      </select>
    </label>}
    {older && <button className="quiet" disabled={loadingOlder} onClick={async () => {
      const requestGeneration = generation.current;
      setLoadingOlder(true);
      try {
        const rows = await api<Version[]>(`${path}/briefs?before=${versions.at(-1)!.revision}`);
        if (requestGeneration !== generation.current) return;
        setVersions((v) => [...v, ...rows]);
        setOlder(rows.length === 50);
      } catch (e) {
        if (requestGeneration === generation.current) setError(e instanceof Error ? e.message : "Could not load older revisions");
      } finally { if (requestGeneration === generation.current) setLoadingOlder(false); }
    }}>Load older brief revisions</button>}
    {!brief && !error && <p className="muted">Loading brief…</p>}
    {brief && <>
      {brief.content ? <pre aria-label="Saved brief content">{brief.content}</pre> : <p className="muted">No brief was saved for this project.</p>}
      <p>Revision {brief.revision} · {brief.actor}</p>
      <p className="brief-digest">SHA-256: <code>{brief.digest}</code></p>
      {!draft && current && <button className="quiet" onClick={() => setDraft({ content: brief.content, expected_revision: brief.revision })}>Edit current brief</button>}
    </>}
    {draft && <form className="inline project-create" onSubmit={async (e) => {
      e.preventDefault();
      if (saving) return;
      setSaving(true);
      setError("");
      try {
        await api<Brief>(`${path}/brief`, { method: "PUT", body: JSON.stringify(draft) });
        setDraft(null);
        setReload((n) => n + 1);
        await onSaved();
      } catch (e) { setError(e instanceof Error ? e.message : "Could not save brief"); }
      finally { setSaving(false); }
    }}>
      <label className="project-brief-input">Revised project brief
        <textarea rows={6} maxLength={20000} value={draft.content} disabled={saving}
          onChange={(e) => setDraft({ ...draft, content: e.target.value })} />
      </label>
      <p>Editing from revision {draft.expected_revision}. Review the saved text above before applying a retained draft to a newer revision.</p>
      {current && brief.revision !== draft.expected_revision && <button type="button" disabled={saving}
        onClick={() => setDraft({ ...draft, expected_revision: brief.revision })}>Use displayed revision as draft base</button>}
      <button disabled={saving}>{saving ? "Saving brief…" : "Save brief revision"}</button>
      <button type="button" className="quiet" disabled={saving} onClick={() => setDraft(null)}>Cancel brief edit</button>
    </form>}
  </section>;
}
