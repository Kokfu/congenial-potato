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
