import { useEffect, useState } from "react";

type Version = {
  id: string;
  artifact_id: string;
  version: number;
  digest: string;
};
type Artifact = Version & {
  project_id: string;
  author: string;
  execution_id: string | null;
  content: string;
};
type Props = {
  projectId: string;
  projects: { id: string; name: string }[];
  onProjectChange: (id: string) => void;
  api: <T>(path: string, init?: RequestInit) => Promise<T>;
};

export function ArtifactBrowser({ projectId, projects, onProjectChange, api }: Props) {
  const [versions, setVersions] = useState<Version[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [artifact, setArtifact] = useState<Artifact | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setVersions([]);
    setSelectedId("");
    setArtifact(null);
    setError("");
    if (!projectId) return () => controller.abort();
    setLoading(true);
    api<Version[]>(`/api/artifacts?project_id=${encodeURIComponent(projectId)}`, {
      signal: controller.signal,
    }).then((rows) => {
      if (controller.signal.aborted) return;
      setVersions(rows);
      setSelectedId(rows[0]?.id ?? "");
    }).catch((reason) => {
      if (!controller.signal.aborted) setError(reason.message ?? "Could not load outputs");
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [api, projectId, reload]);

  useEffect(() => {
    const controller = new AbortController();
    setArtifact(null);
    if (!selectedId) return () => controller.abort();
    setError("");
    api<Artifact>(`/api/artifacts/versions/${encodeURIComponent(selectedId)}`, {
      signal: controller.signal,
    }).then((result) => {
      if (controller.signal.aborted) return;
      if (result.project_id !== projectId || result.id !== selectedId) {
        throw new Error("Output does not match the selected project and version");
      }
      setArtifact(result);
    }).catch((reason) => {
      if (!controller.signal.aborted) setError(reason.message ?? "Could not read output");
    });
    return () => controller.abort();
  }, [api, projectId, selectedId]);

  return (
    <section className="panel">
      <h2>Approved outputs</h2>
      <p className="muted">Saved artifact versions. Content is displayed as text, not executed.</p>
      <div className="inline">
        <label>
          Output project{" "}
          <select aria-label="Output project" value={projectId}
            onChange={(event) => onProjectChange(event.target.value)}>
            {!projects.length && <option value="">No projects yet</option>}
            {projects.map((project) => (
              <option key={project.id} value={project.id}>{project.name}</option>
            ))}
          </select>
        </label>
        <button className="quiet" disabled={!projectId} onClick={() => setReload((n) => n + 1)}>
          Reload outputs
        </button>
      </div>
      {error && <p role="alert">Could not load output: {error}</p>}
      {loading && <p>Loading outputs…</p>}
      {!projectId && <p>Create a project to collect approved outputs.</p>}
      {projectId && !loading && !error && !versions.length && (
        <p>No approved outputs for this project yet.</p>
      )}
      <div className="chips">
        {versions.map((version) => (
          <button key={version.id} aria-pressed={selectedId === version.id}
            className={selectedId === version.id ? "chosen" : ""}
            onClick={() => setSelectedId(version.id)}>
            Artifact {version.artifact_id.slice(0, 8)} · version {version.version}
          </button>
        ))}
      </div>
      {selectedId && !artifact && !error && <p>Loading version…</p>}
      {artifact && artifact.id === selectedId && artifact.project_id === projectId && (
        <article className="artifact-detail">
          <h3>Version {artifact.version}</h3>
          <dl>
            <dt>SHA-256</dt><dd>{artifact.digest}</dd>
            <dt>Author</dt><dd>{artifact.author}</dd>
            <dt>Execution</dt><dd>{artifact.execution_id ?? "Not recorded"}</dd>
          </dl>
          <pre aria-label="Artifact content">{artifact.content}</pre>
        </article>
      )}
    </section>
  );
}
