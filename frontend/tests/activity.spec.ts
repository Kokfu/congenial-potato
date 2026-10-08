import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";

test("project activity reconnects from a persisted cursor", async ({ page }) => {
  const password = readFileSync("../.local/initial_admin_password", "utf8").trim();
  await page.goto("/");
  await page.getByLabel("Owner password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Projects", level: 1 })).toBeVisible();
  const csrf = (await page.context().cookies()).find(
    (cookie) => cookie.name === "workforce_csrf")?.value;
  expect(csrf).toBeTruthy();
  const post = async (path: string, body: unknown) => {
    const response = await page.request.post(path, {
      data: body, headers: { Origin: "http://localhost:8080", "X-CSRF-Token": csrf! },
    });
    expect(response.ok(), `${path}: ${await response.text()}`).toBeTruthy();
    return response.json();
  };
  const name = `Activity browser ${Date.now()}`;
  const project = await post("/api/projects", { name }) as { id: string };
  await post("/api/tasks", { project_id: project.id, title: "First activity task" });
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await page.getByRole("button", { name }).click();
  await page.getByRole("button", { name: "Activity", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Project activity" })).toBeVisible();
  await expect(page.getByText(/Persisted events.*live/)).toBeVisible();
  await expect(page.getByText("task.create", { exact: true })).toHaveCount(1);
  await post("/api/tasks", { project_id: project.id, title: "Live activity task" });
  await expect(page.getByText("task.create", { exact: true })).toHaveCount(2);

  await page.getByRole("button", { name: "Projects", exact: true }).click();
  await post("/api/tasks", { project_id: project.id, title: "Disconnected task" });
  await page.getByRole("button", { name: "Activity", exact: true }).click();
  await expect(page.getByText("task.create", { exact: true })).toHaveCount(3);
  const resumed = await page.evaluate((projectId) => new Promise<number>((resolve, reject) => {
    const source = new EventSource(`/api/projects/${projectId}/activity/stream?after=2`);
    const timer = setTimeout(() => { source.close(); reject(new Error("SSE timeout")); }, 5000);
    source.addEventListener("activity", (event) => {
      clearTimeout(timer);
      const sequence = JSON.parse((event as MessageEvent).data).sequence as number;
      source.close();
      resolve(sequence);
    });
  }), project.id);
  expect(resumed).toBe(3);
  const headerResume = await page.evaluate(async (projectId) => {
    const controller = new AbortController();
    const response = await fetch(`/api/projects/${projectId}/activity/stream`, {
      headers: { "Last-Event-ID": "2" }, signal: controller.signal,
    });
    const reader = response.body!.getReader();
    const decoder = new TextDecoder();
    let output = "";
    while (!output.includes("id: 3")) {
      const chunk = await reader.read();
      if (chunk.done) break;
      output += decoder.decode(chunk.value);
    }
    controller.abort();
    return { status: response.status, output };
  }, project.id);
  expect(headerResume.status).toBe(200);
  expect(headerResume.output).toContain("id: 3");
});
