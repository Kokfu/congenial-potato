import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { CollaborationReview } from "./CollaborationReview";
import { ToolReview } from "./ToolReview";
import { ActivityTimeline } from "./ActivityTimeline";
import { ArtifactBrowser } from "./ArtifactBrowser";
import "./style.css";

type Project = { id: string; name: string; objective: string };
type Agent = {
  id: string;
  name: string;
  role: string;
  status: string;
  provider_connection: string;
  model_id: string;
  config_version: number;
};
type Catalog = { connection_id: string; models: { model_id: string }[] };
type AgentConfig = { versions: { version: number; instructions: string }[] };
type Task = { id: string; title: string; status: string };
type Approval = {
  id: string;
  resource: string;
  status: string;
  payload_hash: string;
  content: string;
};
type Tab = "Projects" | "Agents" | "Approvals" | "Artifacts" | "Collaboration" | "Activity" | "Settings";
const tabs: Tab[] = ["Projects", "Agents", "Approvals", "Artifacts", "Collaboration", "Activity", "Settings"];
const csrf = () =>
  decodeURIComponent(
    document.cookie
      .split("; ")
      .find((x) => x.startsWith("workforce_csrf="))
      ?.split("=")[1] ?? "",
  );
async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    ...((init.headers as Record<string, string>) ?? {}),
  };
  if (init.method && init.method !== "GET") {
    headers["Content-Type"] = "application/json";
    headers["X-CSRF-Token"] = csrf();
  }
  const r = await fetch(path, { ...init, headers, credentials: "same-origin" });
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : `Request failed (${r.status})`,
    );
  }
  return r.json() as Promise<T>;
}
function App() {
  const [loggedIn, setLoggedIn] = useState<boolean | null>(null);
  const [password, setPassword] = useState("");
  const [tab, setTab] = useState<Tab>("Projects");
  const [projects, setProjects] = useState<Project[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [catalogs, setCatalogs] = useState<Catalog[]>([]);
  const [newConnection, setNewConnection] = useState("fixture");
  const [newModel, setNewModel] = useState("fake-v1");
  const [switchTargets, setSwitchTargets] = useState<
    Record<string, { connection: string; model: string }>
  >({});
  const [tasks, setTasks] = useState<Task[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [projectId, setProjectId] = useState("");
  const [projectName, setProjectName] = useState("");
  const [projectBrief, setProjectBrief] = useState("");
  const [taskTitle, setTaskTitle] = useState("");
  const [agentName, setAgentName] = useState("");
  const [runAgentId, setRunAgentId] = useState("");
  const [message, setMessage] = useState("");
  const [ready, setReady] = useState("checking");
  async function refresh() {
    const [p, a, r, c] = await Promise.all([
      api<Project[]>("/api/projects"),
      api<Agent[]>("/api/agents"),
      api<Approval[]>("/api/approvals"),
      api<Catalog[]>("/api/provider-connections"),
    ]);
    setProjects(p);
    setAgents(a);
    setRunAgentId((id) => id || a[0]?.id || "");
    setApprovals(r);
    setCatalogs(c);
    setProjectId((id) => id || p[0]?.id || "");
  }
  useEffect(() => {
    api("/api/auth/me")
      .then(() => {
        setLoggedIn(true);
        refresh().catch((e) => setMessage(e.message));
      })
      .catch(() => setLoggedIn(false));
    api<{ status: string }>("/health/ready")
      .then((x) => setReady(x.status))
      .catch(() => setReady("unavailable"));
  }, []);
  useEffect(() => {
    if (loggedIn && projectId)
      api<Task[]>(`/api/tasks?project_id=${encodeURIComponent(projectId)}`)
        .then(setTasks)
        .catch((e) => setMessage(e.message));
  }, [loggedIn, projectId]);
  async function act(fn: () => Promise<unknown>) {
    try {
      setMessage("");
      await fn();
      await refresh();
      if (projectId)
        setTasks(
          await api(`/api/tasks?project_id=${encodeURIComponent(projectId)}`),
        );
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Request failed");
    }
  }
  if (loggedIn === null)
    return <main className="center">Loading workspace…</main>;
  if (!loggedIn)
    return (
      <main className="center">
        <form
          className="login"
          onSubmit={async (e) => {
            e.preventDefault();
            try {
              await api("/api/auth/login", {
                method: "POST",
                body: JSON.stringify({ password }),
              });
              setPassword("");
              setLoggedIn(true);
              await refresh();
            } catch (error) {
              setMessage(
                error instanceof Error ? error.message : "Login failed",
              );
            }
          }}
        >
          <span className="eyebrow">PRIVATE WORKSPACE</span>
          <h1>Workforce</h1>
          <p>Sign in to manage agents and projects.</p>
          <label>
            Owner password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </label>
          <button>Sign in</button>
          {message && (
            <p className="error" role="alert">
              {message}
            </p>
          )}
        </form>
      </main>
    );
  return (
    <div className="shell">
      <aside>
        <div className="brand">
          <span className="mark">W</span>
          <div>
            <b>Workforce</b>
            <small>Control workspace</small>
          </div>
        </div>
        <nav>
          {tabs.map((item) => (
            <button
              key={item}
              className={tab === item ? "active" : ""}
              onClick={() => setTab(item)}
            >
              {item}
              {item === "Approvals" && approvals.length > 0 && (
                <em>{approvals.length}</em>
              )}
            </button>
          ))}
        </nav>
        <div className="foot">● &nbsp; Local workspace</div>
      </aside>
      <main>
        <header>
          <div>
            <span className="eyebrow">WORKSPACE / {tab.toUpperCase()}</span>
            <h1>{tab}</h1>
          </div>
          <button className="quiet" onClick={() => act(refresh)}>
            Refresh
          </button>
        </header>
        {message && (
          <div className="banner" role="alert">
            {message}
            <button onClick={() => setMessage("")}>Dismiss</button>
          </div>
        )}
        {tab === "Projects" && (
          <>
            <section className="panel">
              <h2>Projects</h2>
              <form
                className="inline project-create"
                onSubmit={(e) => {
                  e.preventDefault();
                  act(async () => {
                    const p = await api<Project>("/api/projects", {
                      method: "POST",
                      body: JSON.stringify({ name: projectName, objective: projectBrief }),
                    });
                    setProjectName("");
                    setProjectBrief("");
                    setProjectId(p.id);
                  });
                }}
              >
                <input
                  placeholder="New project name"
                  aria-label="New project name"
                  maxLength={160}
                  value={projectName}
                  onChange={(e) => setProjectName(e.target.value)}
                  required
                />
                <label className="project-brief-input">
                  Project brief (optional)
                  <textarea
                    value={projectBrief}
                    onChange={(e) => setProjectBrief(e.target.value)}
                    maxLength={20000}
                    rows={6}
                    aria-describedby="brief-help"
                    placeholder="Goal, source notes, intended reader, constraints and expected output"
                  />
                </label>
                <p className="muted" id="brief-help">
                  Up to 20,000 characters. Saved for owner reference; fixture runs do not use this brief.
                  Keep passwords and credentials out of source notes.
                </p>
                <button>Create project</button>
              </form>
              <div className="chips">
                {projects.map((p) => (
                  <button
                    key={p.id}
                    className={projectId === p.id ? "chosen" : ""}
                    onClick={() => setProjectId(p.id)}
                  >
                    {p.name}
                  </button>
                ))}
              </div>
              {projectId && (
                <section className="project-brief" aria-label="Selected project brief">
                  <h3>Saved project brief</h3>
                  {projects.find((p) => p.id === projectId)?.objective ? (
                    <pre aria-label="Saved brief content">
                      {projects.find((p) => p.id === projectId)?.objective}
                    </pre>
                  ) : (
                    <p className="muted">No brief was saved for this project.</p>
                  )}
                </section>
              )}
            </section>
            {projectId && (
              <section className="panel">
                <h2>Tasks</h2>
                {agents.length > 0 && (
                  <label className="run-agent">
                    Agent for fixture
                    <select
                      value={runAgentId}
                      onChange={(e) => setRunAgentId(e.target.value)}
                    >
                      {agents.map((agent) => (
                        <option key={agent.id} value={agent.id}>
                          {agent.name}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
                <form
                  className="inline"
                  onSubmit={(e) => {
                    e.preventDefault();
                    act(async () => {
                      await api("/api/tasks", {
                        method: "POST",
                        body: JSON.stringify({
                          project_id: projectId,
                          title: taskTitle,
                        }),
                      });
                      setTaskTitle("");
                    });
                  }}
                >
                  <input
                    placeholder="New task"
                    value={taskTitle}
                    onChange={(e) => setTaskTitle(e.target.value)}
                    required
                  />
                  <button>Add task</button>
                </form>
                {tasks.length === 0 && <p className="muted">No tasks yet.</p>}
                {tasks.map((t) => (
                  <div className="row" key={t.id}>
                    <div>
                      <strong>{t.title}</strong>
                      <small>{t.id.slice(0, 8)}</small>
                    </div>
                    <div className="actions">
                      <span className="badge">{t.status}</span>
                      {t.status === "backlog" && agents.length > 0 && (
                        <button
                          className="quiet"
                          onClick={() =>
                            act(async () => {
                              await api(`/api/tasks/${t.id}/dispatch`, {
                                method: "POST",
                                body: JSON.stringify({
                                  agent_id: runAgentId,
                                  root_cap: "1.00",
                                }),
                              });
                            })
                          }
                        >
                          Run fixture
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </section>
            )}
          </>
        )}
        {tab === "Agents" && (
          <section className="panel">
            <h2>Agents</h2>
            <p className="muted">
              Stable identities and versioned config. Only synthetic adapters
              are available.
            </p>
            <form
              className="inline"
              onSubmit={(e) => {
                e.preventDefault();
                act(async () => {
                  await api("/api/agents", {
                    method: "POST",
                    body: JSON.stringify({
                      name: agentName,
                      role: "specialist",
                      instructions: "Work only on assigned project tasks.",
                      provider_connection: newConnection,
                      model_id: newModel,
                    }),
                  });
                  setAgentName("");
                });
              }}
            >
              <input
                placeholder="Agent name"
                value={agentName}
                onChange={(e) => setAgentName(e.target.value)}
                required
              />
              <select
                aria-label="New agent provider"
                value={newConnection}
                onChange={(e) => {
                  const connection = e.target.value;
                  setNewConnection(connection);
                  setNewModel(
                    catalogs.find((item) => item.connection_id === connection)
                      ?.models[0]?.model_id ?? "",
                  );
                }}
              >
                {catalogs.map((item) => (
                  <option key={item.connection_id} value={item.connection_id}>
                    {item.connection_id}
                  </option>
                ))}
              </select>
              <select
                aria-label="New agent model"
                value={newModel}
                onChange={(e) => setNewModel(e.target.value)}
              >
                {catalogs
                  .find((item) => item.connection_id === newConnection)
                  ?.models.map((model) => (
                    <option key={model.model_id} value={model.model_id}>
                      {model.model_id}
                    </option>
                  ))}
              </select>
              <button>Add agent</button>
            </form>
            {agents.map((a) => {
              const target = switchTargets[a.id] ?? {
                connection: a.provider_connection,
                model: a.model_id,
              };
              const models =
                catalogs.find(
                  (item) => item.connection_id === target.connection,
                )?.models ?? [];
              return (
                <div className="row" key={a.id}>
                  <div>
                    <strong>{a.name}</strong>
                    <small>
                      {a.role} · {a.id.slice(0, 8)} · revision{" "}
                      {a.config_version} · {a.provider_connection}/{a.model_id}
                    </small>
                  </div>
                  <div className="actions">
                    <span className="badge">{a.status}</span>
                    <select
                      aria-label={`Provider for ${a.name}`}
                      value={target.connection}
                      onChange={(e) => {
                        const connection = e.target.value;
                        setSwitchTargets((current) => ({
                          ...current,
                          [a.id]: {
                            connection,
                            model:
                              catalogs.find(
                                (item) => item.connection_id === connection,
                              )?.models[0]?.model_id ?? "",
                          },
                        }));
                      }}
                    >
                      {catalogs.map((item) => (
                        <option
                          key={item.connection_id}
                          value={item.connection_id}
                        >
                          {item.connection_id}
                        </option>
                      ))}
                    </select>
                    <select
                      aria-label={`Model for ${a.name}`}
                      value={target.model}
                      onChange={(e) =>
                        setSwitchTargets((current) => ({
                          ...current,
                          [a.id]: { ...target, model: e.target.value },
                        }))
                      }
                    >
                      {models.map((model) => (
                        <option key={model.model_id} value={model.model_id}>
                          {model.model_id}
                        </option>
                      ))}
                    </select>
                    <button
                      className="quiet"
                      disabled={
                        target.connection === a.provider_connection &&
                        target.model === a.model_id
                      }
                      onClick={() =>
                        act(async () => {
                          const config = await api<AgentConfig>(
                            `/api/agents/${a.id}/config`,
                          );
                          const latest = config.versions.at(-1);
                          if (!latest)
                            throw new Error("Agent configuration missing");
                          await api(`/api/agents/${a.id}/config`, {
                            method: "PUT",
                            body: JSON.stringify({
                              expected_version: latest.version,
                              instructions: latest.instructions,
                              provider_connection: target.connection,
                              model_id: target.model,
                            }),
                          });
                        })
                      }
                    >
                      Update provider
                    </button>
                    {projectId && (
                      <button
                        className="quiet"
                        onClick={() =>
                          act(async () => {
                            await api(`/api/agents/${a.id}/grants`, {
                              method: "POST",
                              body: JSON.stringify({
                                project_id: projectId,
                                action: "project.execute",
                                allowed: true,
                              }),
                            });
                          })
                        }
                      >
                        Grant project execution
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </section>
        )}
        {tab === "Approvals" && (
          <>
          <section className="panel">
            <h2>Pending approvals</h2>
            <p className="muted">
              Review the exact synthetic artifact content before authorizing its
              immutable version.
            </p>
            {approvals.length === 0 ? (
              <p className="empty">Nothing needs approval.</p>
            ) : (
              approvals.map((a) => (
                <div className="row" key={a.id}>
                  <div>
                    <strong>{a.resource}</strong>
                    <small>{a.content}</small>
                    <small>SHA-256 proposal: {a.payload_hash}</small>
                  </div>
                  <div className="actions">
                    {([true, false] as const).map((approved) => (
                      <button
                        key={String(approved)}
                        className="quiet"
                        onClick={() =>
                          act(() =>
                            api(`/api/approvals/${a.id}/decision`, {
                              method: "POST",
                              body: JSON.stringify({
                                approved,
                                payload_hash: a.payload_hash,
                              }),
                            }),
                          )
                        }
                      >
                        {approved ? "Approve artifact" : "Reject"}
                      </button>
                    ))}
                  </div>
                </div>
              ))
            )}
          </section>
          <ToolReview projectId={projectId} api={api} onError={setMessage} />
          </>
        )}
        {tab === "Artifacts" && (
          <ArtifactBrowser key={projectId} projectId={projectId} projects={projects}
            onProjectChange={setProjectId} api={api} />
        )}
        {tab === "Collaboration" && (
          <CollaborationReview
            projectId={projectId}
            projectName={projects.find((project) => project.id === projectId)?.name ?? ""}
            api={api}
            onError={setMessage}
          />
        )}
        {tab === "Activity" && (
          <ActivityTimeline projectId={projectId} api={api} onError={setMessage} />
        )}
        {tab === "Settings" && (
          <section className="panel">
            <h2>Workspace status</h2>
            <div className="row">
              API readiness<strong>{ready}</strong>
            </div>
            <div className="row">
              Model calls<strong>Fixture only</strong>
            </div>
            <div className="row">
              Access<strong>Private owner</strong>
            </div>
            <button
              className="quiet logout"
              onClick={() =>
                act(async () => {
                  await api("/api/auth/logout", { method: "POST" });
                  setLoggedIn(false);
                })
              }
            >
              Sign out
            </button>
          </section>
        )}
      </main>
    </div>
  );
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
