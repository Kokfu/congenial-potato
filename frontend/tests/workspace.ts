import { readFileSync } from "node:fs";

export const workspaceOrigin = new URL(
  process.env.WORKFORCE_BASE_URL ?? "http://localhost:8080",
).origin;

export function ownerPassword() {
  return readFileSync(
    process.env.WORKFORCE_PASSWORD_FILE ?? "../.local/initial_admin_password",
    "utf8",
  ).trim();
}
