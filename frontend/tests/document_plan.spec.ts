import { test, expect } from "@playwright/test";
import { ownerPassword, workspaceOrigin } from "./workspace";

test("owner reviews a plan and explicitly runs a cited fixture draft with exact output approval", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Owner password").fill(ownerPassword());
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Projects", level: 1 })).toBeVisible();
  const csrf = (await page.context().cookies()).find((cookie) => cookie.name === "workforce_csrf")!.value;
  const headers = { Origin: workspaceOrigin, "X-CSRF-Token": csrf };
  const suffix = Date.now();
  const notes = "Document fixture notes: the review meeting needs an action list. Owners and dates are unknown.";
  await page.getByLabel("Walkthrough project name").fill(`Document plan ${suffix}`);
  await page.getByLabel("Walkthrough source notes").fill(notes);
  const setupResponse = page.waitForResponse(response => response.url().endsWith('/api/document-fixtures') && response.status() === 201);
  await page.getByRole('button', { name: 'Create document fixture setup' }).click();
  const setup = await (await setupResponse).json() as { project_id: string; manager_id: string; draft_agent_id: string; task_id: string };
  const project = { id: setup.project_id };
  const target = { id: setup.draft_agent_id };
  await expect(page.getByRole('status')).toContainText('Setup saved.');
  const unstarted = await (await page.request.get(`/api/tasks?project_id=${project.id}`)).json() as Array<{ status: string }>;
  expect(unstarted.map(row => row.status)).toEqual(['backlog']);
  await expect(page.getByLabel('Agent for fixture')).toHaveValue(setup.manager_id);
  await page.getByRole('button', { name: 'Run fixture', exact: true }).click();
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
  await expect(draft.getByText("Uses reviewed brief revision 1", { exact: false })).toBeVisible();
  await expect(draft.getByRole("button", { name: "Run fixture" })).toHaveCount(0);
  // Deliberately edit current notes after plan admission; the explicit action uses the reviewed version.
  await page.getByRole("button", { name: "Edit current brief" }).click();
  await page.getByLabel("Revised project brief").fill("Later notes must not silently replace the reviewed plan source.");
  await page.getByRole("button", { name: "Save brief revision" }).click();
  await expect(page.getByLabel("Saved brief content")).toHaveText("Later notes must not silently replace the reviewed plan source.");
  const dispatched = page.waitForResponse((response) => response.url().includes('/draft-fixture') && response.status() === 202);
  await draft.getByRole("button", { name: "Run reviewed draft fixture" }).click();
  const execution = (await (await dispatched).json() as { execution_id: string }).execution_id;
  await expect.poll(async () => {
    await page.getByRole("button", { name: "Refresh", exact: true }).click();
    return draft.getByText("review", { exact: true }).count();
  }).toBe(1);
  await page.getByRole("button", { name: "Approvals" }).click();
  const proposal = page.locator('.row').filter({ hasText: '# Synthetic document draft' })
    .filter({ hasText: planned[0].document_plan_id! });
  await expect(proposal).toContainText('[S1]');
  await expect(proposal).toContainText('brief revision 1');
  await expect(proposal).not.toContainText('Later notes must not silently replace');
  const unapproved = await (await page.request.get(`/api/artifacts?project_id=${project.id}`)).json() as unknown[];
  expect(unapproved).toHaveLength(0);
  await proposal.getByRole('button', { name: 'Approve artifact' }).click();
  await expect.poll(async () => (await (await page.request.get(`/api/artifacts?project_id=${project.id}`)).json()).length).toBe(1);
  await page.getByRole('button', { name: 'Artifacts', exact: true }).click();
  await page.getByLabel('Output project').selectOption(project.id);
  await expect(page.getByLabel('Artifact content')).toContainText('# Synthetic document draft');
  await expect(page.getByLabel('Artifact content')).toContainText('Prepared context SHA-256:');
  await page.getByText('Recorded source brief · revision 1', { exact: true }).click();
  await expect(page.getByLabel('Run source content')).toHaveText(notes);
  const recorded = await (await page.request.get(`/api/executions/${execution}/brief`)).json() as { revision: number };
  expect(recorded.revision).toBe(1);
  await page.getByRole('button', { name: 'Projects', exact: true }).click();
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await draft.getByRole('button', { name: 'Accept reviewed draft task' }).click();
  await expect(draft.getByText('completed', { exact: true })).toBeVisible();
});

test("fixture setup reports an uncertain failure without automatically retrying", async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Owner password').fill(ownerPassword());
  await page.getByRole('button', { name: 'Sign in' }).click();
  let requests = 0;
  await page.route('**/api/document-fixtures', async route => {
    requests += 1;
    await route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'Synthetic setup failure' }) });
  });
  await page.getByLabel('Walkthrough source notes').fill('Retain these notes after a failure.');
  await page.getByRole('button', { name: 'Create document fixture setup' }).click();
  await expect(page.getByRole('status')).toContainText('Refresh and inspect Projects and Agents');
  await expect(page.getByLabel('Walkthrough source notes')).toHaveValue('Retain these notes after a failure.');
  await expect(page.getByRole('button', { name: 'Create document fixture setup' })).toBeDisabled();
  expect(requests).toBe(1);
});
