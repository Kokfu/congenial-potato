import { test, expect } from "@playwright/test";
import { ownerPassword } from "./workspace";

test("project briefs survive save failures and reload, and stay scoped as literal text", async ({ page }) => {
  const name = `Brief fixture ${Date.now()}`;
  const brief = 'Goal: draft a garden guide.\nSource: <script>window.briefExecuted=true</script>\n<img src=x onerror="window.briefExecuted=true">\nReader: a beginner 🌱\nConstraint: cite missing facts; do not invent them.';
  await page.goto("/");
  await page.getByLabel("Owner password").fill(ownerPassword());
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByLabel("New project name").fill(name);
  const input = page.getByLabel("Project brief (optional)");
  await expect(input).toHaveAttribute("maxlength", "20000");
  await input.fill(brief);

  // Explicit HTTP fault: a failed create must retain the owner's draft.
  await page.route("**/api/projects", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({ status: 503, contentType: "application/json",
        body: JSON.stringify({ detail: "Brief save unavailable (test fault)" }) });
    } else await route.continue();
  });
  await page.getByRole("button", { name: "Create project" }).click();
  await expect(page.getByRole("alert")).toContainText("Brief save unavailable");
  await expect(input).toHaveValue(brief);
  await expect(page.getByLabel("New project name")).toHaveValue(name);
  await page.unroute("**/api/projects");

  // Everything after removing the fault uses the real authenticated API/database.
  await page.getByRole("button", { name: "Create project" }).click();
  const content = page.getByLabel("Saved brief content");
  await expect(content).toHaveText(brief);
  await expect(input).toHaveValue("");
  await expect(page.getByLabel("New project name")).toHaveValue("");
  await page.reload();
  await page.getByRole("button", { name, exact: true }).click();
  await expect(content).toHaveText(brief);
  await expect(content.locator("script, img")).toHaveCount(0);
  expect(await page.evaluate(() => (window as unknown as { briefExecuted?: boolean }).briefExecuted)).toBeUndefined();
  const rows = await (await page.request.get("/api/projects")).json() as Array<{ name: string; objective: string }>;
  expect(rows.find((row) => row.name === name)?.objective).toBe(brief);

  const emptyName = `${name} empty`;
  await page.getByLabel("New project name").fill(emptyName);
  await page.getByRole("button", { name: "Create project" }).click();
  await expect(page.getByText("No brief was saved for this project.")).toBeVisible();
  await expect(content).toHaveCount(0);
  await page.getByRole("button", { name, exact: true }).click();
  await expect(content).toHaveText(brief);
});

test("two owner tabs retain a stale draft and explicitly rebase while old revisions stay readable", async ({ page, context }) => {
  const name = `Versioned brief ${Date.now()}`;
  await page.goto("/");
  await page.getByLabel("Owner password").fill(ownerPassword());
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByLabel("New project name").fill(name);
  await page.getByLabel("Project brief (optional)").fill("Original source notes 🌱");
  await page.getByRole("button", { name: "Create project" }).click();
  await expect(page.getByLabel("Saved brief content")).toHaveText("Original source notes 🌱");
  const other = await context.newPage();
  await other.goto("/");
  await other.getByRole("button", { name, exact: true }).click();
  for (const tab of [page, other]) {
    await tab.getByRole("button", { name: "Edit current brief" }).click();
  }
  await page.getByLabel("Revised project brief").fill("Saved from first tab");
  await other.getByLabel("Revised project brief").fill("Retained draft from second tab");
  await page.getByRole("button", { name: "Save brief revision" }).click();
  await expect(page.getByLabel("Saved brief content")).toHaveText("Saved from first tab");
  await other.getByRole("button", { name: "Save brief revision" }).click();
  await expect(other.getByRole("alert")).toContainText("Brief changed");
  await expect(other.getByLabel("Revised project brief")).toHaveValue("Retained draft from second tab");
  await other.getByRole("button", { name: "Reload brief history" }).click();
  await expect(other.getByLabel("Saved brief content")).toHaveText("Saved from first tab");
  await expect(other.getByLabel("Revised project brief")).toHaveValue("Retained draft from second tab");
  await other.getByRole("button", { name: "Use displayed revision as draft base" }).click();
  await other.getByRole("button", { name: "Save brief revision" }).click();
  await expect(other.getByLabel("Saved brief content")).toHaveText("Retained draft from second tab");
  await other.reload();
  await other.getByRole("button", { name, exact: true }).click();
  await expect(other.getByLabel("Saved brief content")).toHaveText("Retained draft from second tab");
  await other.getByLabel("Brief revision", { exact: true }).selectOption("1");
  await expect(other.getByLabel("Saved brief content")).toHaveText("Original source notes 🌱");
  await expect(other.getByRole("button", { name: "Edit current brief" })).toHaveCount(0);
  await other.getByLabel("Brief revision", { exact: true }).selectOption("2");
  await expect(other.getByLabel("Saved brief content")).toHaveText("Saved from first tab");
  await expect(other.locator(".brief-digest code")).toHaveText(/^[a-f0-9]{64}$/);
  await other.close();
});
