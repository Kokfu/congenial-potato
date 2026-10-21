import { test, expect } from "@playwright/test";
import { ownerPassword, workspaceOrigin } from "./workspace";

test("owner inspects a source-bound fixture plan and admits only gated backlog work", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Owner password").fill(ownerPassword());
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Projects", level: 1 })).toBeVisible();
  const csrf = (await page.context().cookies()).find((cookie) => cookie.name === "workforce_csrf")!.value;
  const headers = { Origin: workspaceOrigin, "X-CSRF-Token": csrf };
  const post = async <T,>(path: string, data: unknown): Promise<T> => {
    const response = await page.request.post(path, { data, headers });
    expect(response.ok(), `${path}: ${await response.text()}`).toBeTruthy();
    return response.json() as Promise<T>;
  };
  const suffix = Date.now();
  const notes = "Document fixture notes: the review meeting needs an action list. Owners and dates are unknown.";
  const project = await post<{ id: string }>("/api/projects", { name: `Document plan ${suffix}`, objective: notes });
  const target = await post<{ id: string }>("/api/agents", {
    name: `Document target ${suffix}`, role: "specialist", instructions: "Synthetic only",
    provider_connection: "fixture", model_id: "fake-v1",
  });
  // Explicit structured fixture output; this is not a substantive model-generated plan.
  const candidate = { kind: "plan", proposal_key: `document-${suffix}`, expected_revision: 1, tasks: [
    { work_key: "draft", title: "Prepare a cited draft", assignee_id: target.id, depends_on: [] },
    { work_key: "review", title: "Review source citations", assignee_id: target.id, depends_on: ["draft"] },
  ] };
  const manager = await post<{ id: string }>("/api/agents", {
    name: `Document manager ${suffix}`, role: "Manager", instructions: `FIXTURE_COLLAB_JSON:${JSON.stringify(candidate)}`,
    provider_connection: "fixture-collaboration", model_id: "collaboration-v1", output_contract: "collaboration.v1",
  });
  for (const agent of [target, manager]) await post(`/api/agents/${agent.id}/grants`, {
    project_id: project.id, action: "project.execute", allowed: true,
  });
  const task = await post<{ id: string }>("/api/tasks", { project_id: project.id, title: "Propose fixture document plan" });
  await post(`/api/tasks/${task.id}/dispatch`, { agent_id: manager.id, root_cap: "1.0" });
  await expect.poll(async () => (await (await page.request.get(
    `/api/collaboration-proposals?project_id=${project.id}`)).json()).length).toBe(1);
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await page.getByRole("button", { name: `Document plan ${suffix}`, exact: true }).click();
  await page.getByRole("button", { name: "Collaboration", exact: true }).click();
  await expect(page.getByText("Source-bound document plan.", { exact: false })).toBeVisible();
  await page.getByText("Recorded source brief · revision 1", { exact: true }).click();
  await expect(page.getByLabel("Run source content")).toHaveText(notes);
  await expect(page.getByLabel("Prepared source context")).toContainText("Context prepared for fixture generation");
  const before = await (await page.request.get(`/api/tasks?project_id=${project.id}`)).json() as unknown[];
  expect(before).toHaveLength(1);
  await page.getByRole("button", { name: "Admit proposal", exact: true }).click();
  await expect(page.getByText("No pending collaboration proposals.")).toBeVisible();
  const tasks = await (await page.request.get(`/api/tasks?project_id=${project.id}`)).json() as Array<{
    id: string; title: string; status: string; document_plan_id: string | null;
  }>;
  const planned = tasks.filter((row) => row.document_plan_id);
  expect(planned).toHaveLength(2);
  expect(planned.every((row) => row.status === "backlog")).toBeTruthy();
  const refused = await page.request.post(`/api/tasks/${planned[0].id}/dispatch`, {
    data: { agent_id: target.id, root_cap: "1.0" }, headers,
  });
  expect(refused.status()).toBe(409);
  await page.getByRole("button", { name: "Projects", exact: true }).click();
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  const draft = page.getByText("Prepare a cited draft", { exact: true }).locator("..").locator("..");
  await expect(draft.getByText("Document draft execution is not enabled.")).toBeVisible();
  await expect(draft.getByRole("button", { name: "Run fixture" })).toHaveCount(0);
});
