import { test, expect } from "@playwright/test";
import { ownerPassword, workspaceOrigin } from "./workspace";

test("owner reviews a runtime-originated child proposal", async ({ page }) => {
  const password = ownerPassword();
  await page.goto("/");
  await page.getByLabel("Owner password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Projects", level: 1 })).toBeVisible();
  const csrf = (await page.context().cookies()).find((cookie) => cookie.name === "workforce_csrf")?.value;
  expect(csrf).toBeTruthy();
  const post = async <T,>(path: string, body: unknown): Promise<T> => {
    const response = await page.request.post(path, {
      data: body,
      headers: { Origin: workspaceOrigin, "X-CSRF-Token": csrf! },
    });
    expect(response.ok(), `${path}: ${await response.text()}`).toBeTruthy();
    return response.json() as Promise<T>;
  };
  const suffix = Date.now().toString();
  const projectName = `Collaboration browser ${suffix}`;
  const project = await post<{ id: string }>("/api/projects", { name: projectName });
  const target = await post<{ id: string }>("/api/agents", {
    name: `Target ${suffix}`, role: "specialist", instructions: "Synthetic",
    provider_connection: "fixture", model_id: "fake-v1",
  });
  const candidate = { kind: "delegation", request_key: `browser-${suffix}`,
    work_key: `browser-${suffix}`, title: "Reviewed child", agent_id: target.id };
  const source = await post<{ id: string }>("/api/agents", {
    name: `Source ${suffix}`, role: "Manager",
    instructions: `FIXTURE_COLLAB_JSON:${JSON.stringify(candidate)}`,
    provider_connection: "fixture-collaboration", model_id: "collaboration-v1",
    output_contract: "collaboration.v1",
  });
  for (const agent of [target, source]) {
    await post(`/api/agents/${agent.id}/grants`, {
      project_id: project.id, action: "project.execute", allowed: true,
    });
  }
  const task = await post<{ id: string }>("/api/tasks", {
    project_id: project.id, title: "Propose child",
  });
  const run = await post<{ execution_id: string }>(`/api/tasks/${task.id}/dispatch`, {
    agent_id: source.id, root_cap: "1.0",
  });
  await expect.poll(async () => {
    const response = await page.request.get(`/api/collaboration-proposals?project_id=${project.id}`);
    const proposals = (await response.json()) as unknown[];
    return proposals.length;
  }).toBe(1);
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await page.getByRole("button", { name: "Projects", exact: true }).click();
  await page.getByRole("button", { name: projectName }).click();
  await page.getByRole("button", { name: "Collaboration", exact: true }).click();
  await expect(page.getByText("Reviewed child", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Admit proposal" }).click();
  await expect(page.getByText("No pending collaboration proposals.")).toBeVisible();
  const children = await (await page.request.get(`/api/executions/${run.execution_id}/children`)).json() as unknown[];
  expect(children).toHaveLength(1);
});
