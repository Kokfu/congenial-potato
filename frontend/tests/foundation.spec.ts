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
  await expect(page.getByRole("heading", { name: "Projects", level: 1 })).toBeVisible();
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
  await taskRow.getByRole("button", { name: "Run fixture" }).click();
  await expect
    .poll(async () => {
      await page.getByRole("button", { name: "Refresh" }).click();
      return taskRow.getByText("review", { exact: true }).count();
    })
    .toBe(1);
});
