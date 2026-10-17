import { test, expect } from "@playwright/test";
import { createHash } from "node:crypto";
import { ownerPassword, workspaceOrigin } from "./workspace";

test("artifact text stays inert and project changes discard delayed replies", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Owner password").fill(ownerPassword());
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Projects", level: 1 })).toBeVisible();
  const csrf = (await page.context().cookies()).find((cookie) => cookie.name === "workforce_csrf")!.value;
  const createProject = async (name: string) => {
    const response = await page.request.post("/api/projects", {
      data: { name }, headers: { Origin: workspaceOrigin, "X-CSRF-Token": csrf },
    });
    expect(response.status()).toBe(201);
    return response.json() as Promise<{ id: string; name: string }>;
  };
  const a = await createProject(`Output scope A ${Date.now()}`);
  const b = await createProject(`Output scope B ${Date.now()}`);
  const hostile = '<script>window.__artifactExecuted=true</script><img src=x onerror="window.__artifactExecuted=true">';
  const makeArtifact = (id: string, projectId: string, content: string) => ({
    id, project_id: projectId, artifact_id: id, version: 1, content,
    digest: createHash("sha256").update(content).digest("hex"),
    author: "render-fixture", execution_id: null,
  });
  const first = makeArtifact("render-a", a.id, hostile);
  const second = makeArtifact("render-b", b.id, "Delayed output from project B");
  let entered!: () => void;
  let release!: () => void;
  let finished!: () => void;
  const enteredB = new Promise<void>((resolve) => { entered = resolve; });
  const releaseB = new Promise<void>((resolve) => { release = resolve; });
  const finishedB = new Promise<void>((resolve) => { finished = resolve; });
  await page.route("**/api/artifacts?*", async (route) => {
    const id = new URL(route.request().url()).searchParams.get("project_id");
    await route.fulfill({ json: id === a.id ? [first] : id === b.id ? [second] : [] });
  });
  await page.route("**/api/artifacts/versions/render-*", async (route) => {
    if (route.request().url().endsWith("render-b")) {
      entered();
      await releaseB;
      await route.fulfill({ json: second });
      finished();
    } else {
      await route.fulfill({ json: first });
    }
  });
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await page.getByRole("button", { name: a.name, exact: true }).click();
  await page.getByRole("button", { name: "Artifacts", exact: true }).click();
  await expect(page.getByLabel("Artifact content")).toHaveText(hostile);
  expect(await page.evaluate(() => (window as Window & { __artifactExecuted?: boolean }).__artifactExecuted)).toBeUndefined();
  await expect(page.locator(".artifact-detail img, .artifact-detail script")).toHaveCount(0);
  await page.getByLabel("Output project").selectOption(b.id);
  await enteredB;
  await expect(page.getByLabel("Artifact content")).toHaveCount(0);
  await page.getByLabel("Output project").selectOption(a.id);
  await expect(page.getByLabel("Artifact content")).toHaveText(hostile);
  release();
  await finishedB;
  await expect(page.getByLabel("Artifact content")).toHaveText(hostile);
  await expect(page.getByText(second.content, { exact: true })).toHaveCount(0);
});
