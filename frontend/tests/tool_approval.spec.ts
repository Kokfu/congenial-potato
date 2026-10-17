import { test, expect } from "@playwright/test";
import { ownerPassword, workspaceOrigin } from "./workspace";
import { randomUUID } from "node:crypto";

test("owner reviews exact synthetic tool arguments", async ({ page }) => {
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
  const projectName = `Tool browser ${suffix}`;
  const project = await post<{ id: string }>("/api/projects", { name: projectName });
  const artifactId = randomUUID();
  const output = { version: 1, action: "project.artifact.write", arguments: {
    project_id: project.id, artifact_id: artifactId,
    content: "Browser synthetic write", expected_parent: null,
  } };
  const agent = await post<{ id: string }>("/api/agents", {
    name: `Tool source ${suffix}`, role: "specialist",
    instructions: `FIXTURE_TOOL_JSON:${JSON.stringify(output)}`,
    provider_connection: "fixture-tool", model_id: "tool-v1",
    output_contract: "tool.v1",
  });
  await post(`/api/agents/${agent.id}/grants`, {
    project_id: project.id, action: "project.execute", allowed: true,
  });
  for (const agentId of [null, agent.id]) {
    await post("/api/tool-policies", {
      project_id: project.id, agent_id: agentId,
      action: "project.artifact.write", effect: "allow",
    });
  }
  const task = await post<{ id: string }>("/api/tasks", {
    project_id: project.id, title: "Review tool effect",
  });
  await post(`/api/tasks/${task.id}/dispatch`, { agent_id: agent.id, root_cap: "1.0" });
  await expect.poll(async () => {
    const response = await page.request.get(`/api/tool-invocations?project_id=${project.id}`);
    const rows = (await response.json()) as { status: string }[];
    return rows[0]?.status;
  }).toBe("awaiting_approval");
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await page.getByRole("button", { name: "Projects", exact: true }).click();
  await page.getByRole("button", { name: projectName }).click();
  await page.getByRole("button", { name: /^Approvals/ }).click();
  await expect(page.getByText("Browser synthetic write")).toBeVisible();
  await expect(page.locator(".proposal-content").getByText(artifactId)).toBeVisible();
  await page.getByRole("button", { name: "Approve tool" }).click();
  await expect(page.getByText("No pending tool approvals for this project.")).toBeVisible();
  await expect.poll(async () => {
    const rows = await (await page.request.get(
      `/api/tool-invocations?project_id=${project.id}`)).json() as { status: string }[];
    return rows[0]?.status;
  }).toBe("succeeded");
  const artifacts = await (await page.request.get(
    `/api/artifacts?project_id=${project.id}`)).json() as unknown[];
  expect(artifacts).toHaveLength(0);
});
