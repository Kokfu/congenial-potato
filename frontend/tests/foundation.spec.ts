import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";

test("owner can create project, grant a fixture agent, and review completed task", async ({
  page,
}) => {
  const password = readFileSync(
    "../.local/initial_admin_password",
    "utf8",
  ).trim();
  const suffix = Date.now().toString();
  const project = `Browser fixture ${suffix}`;
  const agent = `Browser agent ${suffix}`;
  const task = `Browser task ${suffix}`;
  await page.goto("/");
  await page.getByLabel("Owner password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(
    page.getByRole("heading", { name: "Projects", level: 1 }),
  ).toBeVisible();
  await page.getByPlaceholder("New project name").fill(project);
  await page.getByRole("button", { name: "Create project" }).click();
  await expect(page.getByRole("button", { name: project })).toBeVisible();
  await page.getByRole("button", { name: "Agents", exact: true }).click();
  await page.getByPlaceholder("Agent name").fill(agent);
  await page.getByRole("button", { name: "Add agent" }).click();
  const agentRow = page
    .getByText(agent, { exact: true })
    .locator("..")
    .locator("..");
  await expect(
    agentRow.getByRole("button", { name: "Grant project execution" }),
  ).toBeVisible();
  await agentRow
    .getByRole("button", { name: "Grant project execution" })
    .click();
  await page.getByRole("button", { name: "Projects", exact: true }).click();
  await page.getByLabel("Agent for fixture").selectOption({ label: agent });
  await page.getByPlaceholder("New task").fill(task);
  await page.getByRole("button", { name: "Add task" }).click();
  const taskRow = page
    .getByText(task, { exact: true })
    .locator("..")
    .locator("..");
  const dispatchResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/dispatch") && response.status() === 202,
  );
  await taskRow.getByRole("button", { name: "Run fixture" }).click();
  const executionId = (
    (await (await dispatchResponse).json()) as { execution_id: string }
  ).execution_id;
  await expect
    .poll(async () => {
      await page.getByRole("button", { name: "Refresh" }).click();
      return taskRow.getByText("review", { exact: true }).count();
    })
    .toBe(1);
  await page.getByRole("button", { name: "Refresh" }).click();
  await page.getByRole("button", { name: "Approvals" }).click();
  const proposal = page
    .getByText(`Synthetic result for execution ${executionId}`, { exact: true })
    .locator("..")
    .locator("..");
  await expect(proposal).toBeVisible();
  await proposal.getByRole("button", { name: "Approve artifact" }).click();
  await expect
    .poll(async () => {
      const projects = (await (
        await page.request.get("/api/projects")
      ).json()) as Array<{ id: string; name: string }>;
      const id = projects.find((p) => p.name === project)?.id;
      if (!id) return 0;
      const versions = (await (
        await page.request.get(`/api/artifacts?project_id=${id}`)
      ).json()) as unknown[];
      return versions.length;
    })
    .toBe(1);
  await page.getByRole("button", { name: "Agents", exact: true }).click();
  await page.getByLabel(`Provider for ${agent}`).selectOption("fixture-beta");
  await agentRow.getByRole("button", { name: "Update provider" }).click();
  await expect(
    agentRow.getByText("revision 2", { exact: false }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Projects", exact: true }).click();
  const nextTask = `Switched task ${suffix}`;
  await page.getByPlaceholder("New task").fill(nextTask);
  await page.getByRole("button", { name: "Add task" }).click();
  const nextRow = page
    .getByText(nextTask, { exact: true })
    .locator("..")
    .locator("..");
  const switchedResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/dispatch") && response.status() === 202,
  );
  await nextRow.getByRole("button", { name: "Run fixture" }).click();
  const switchedId = (
    (await (await switchedResponse).json()) as { execution_id: string }
  ).execution_id;
  await expect
    .poll(async () => {
      const response = await page.request.get(
        `/api/executions/${switchedId}/model-call`,
      );
      return response.status();
    })
    .toBe(200);
  const call = (await (
    await page.request.get(`/api/executions/${switchedId}/model-call`)
  ).json()) as { provider_connection: string; model_id: string };
  expect(call.provider_connection).toBe("fixture-beta");
  expect(call.model_id).toBe("beta-tools-v1");
});
