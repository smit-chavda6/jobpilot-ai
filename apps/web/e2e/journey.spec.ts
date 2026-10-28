/**
 * Definition-of-Done journey (spec §16/§19) through the real UI and API:
 * register -> onboard -> upload & confirm resume -> import job -> view match -> tailor -> review ->
 * approve -> hand-off -> confirm submission -> see it in the tracker with history -> analytics.
 */
import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const fixtures = resolve(dirname(fileURLToPath(import.meta.url)), "../../api/tests/fixtures");
const PASSWORD = "Sup3rSecurePass";

test("full user journey", async ({ page }) => {
  const email = `journey-${Date.now()}@example.com`;

  // Register
  await page.goto("/register");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByLabel("Confirm password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();

  // Onboarding: consent -> about you -> preferences -> resume -> confirm facts
  await expect(page.getByRole("heading", { name: "How JobPilot uses your data" })).toBeVisible();
  await page.getByRole("button", { name: "Allow AI processing and continue" }).click();

  await page.getByLabel("Full name").fill("Alex Rivera");
  await page.getByLabel("Years of experience").fill("4");
  await page.getByLabel("Highest education").selectOption("master");
  await page.getByRole("button", { name: "Continue" }).click();

  await page.getByLabel("Target job titles").fill("Machine Learning Engineer, Data Scientist");
  await page.getByLabel("Preferred locations").fill("Bengaluru, Remote");
  await page.getByRole("button", { name: "Continue" }).click();

  await page.getByLabel("Resume file").setInputFiles(resolve(fixtures, "resume_alex.txt"));
  await expect(page.getByText(/Found \d+ candidate facts/)).toBeVisible();
  await page.getByRole("button", { name: "Review facts" }).click();

  await expect(page.getByText(/never used in matching or generated documents/)).toBeVisible();
  await page.getByRole("button", { name: /Confirm all \d+/ }).click();
  await expect(page.getByText(/never used in matching/)).toBeHidden();
  await page.getByRole("button", { name: "Finish setup" }).click();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();

  // Import a job from a permitted source (paste)
  await page.goto("/jobs?import=1");
  await page.getByLabel("Job description").fill(readFileSync(resolve(fixtures, "job_ml_engineer.txt"), "utf-8"));
  await page.getByRole("button", { name: "Import", exact: true }).click();
  await expect(page.getByText("1 new · 0 updated · 0 failed")).toBeVisible();
  await page.getByRole("link", { name: /Machine Learning Engineer — Nimbus AI/ }).click();

  // Scored, explained match
  await expect(page.getByRole("heading", { name: "Why this score" })).toBeVisible();
  await expect(page.getByRole("list", { name: "Score components" })).toBeVisible();
  await expect(page.getByText("Fit reasons")).toBeVisible();

  // Tailor & prepare
  await page.getByRole("button", { name: "Tailor & prepare application" }).click();
  await expect(page.getByText("Step 1 · Prepare documents")).toBeVisible();
  await page.getByRole("button", { name: "Generate tailored documents" }).click();
  await expect(page.getByRole("link", { name: /^Resume — Machine Learning Engineer/ })).toBeVisible();
  await expect(page.getByText("Grounded").first()).toBeVisible();

  // Edit in Resume Studio: reorder, save, still grounded, export enabled
  await page.getByRole("link", { name: /^Resume — Machine Learning Engineer/ }).click();
  await expect(page.getByText(/items are supported by your confirmed facts/)).toBeVisible();
  await page.getByRole("button", { name: "Move down" }).first().click();
  await page.getByRole("button", { name: "Save & re-check" }).click();
  await expect(page.getByText(/Saved — all items grounded/)).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "PDF" }).click();
  expect((await download).suggestedFilename()).toMatch(/\.pdf$/);
  await page.goBack();

  // Review -> approval -> hand-off -> confirmation
  await page.getByRole("button", { name: "Mark ready for review" }).click();
  await expect(page.getByText("Step 2 · Review & pre-flight")).toBeVisible();
  await page.getByRole("button", { name: "Request approval" }).click();
  await expect(page.getByText("Step 3 · Approve this exact package")).toBeVisible();
  await expect(page.getByText(/Package hash:/)).toBeVisible();
  await page.getByRole("button", { name: "I approve this package" }).click();
  await expect(page.getByText("Step 4 · Submit on the employer's site")).toBeVisible();
  await page.getByRole("button", { name: "I'm applying now" }).click();
  await expect(page.getByText("Step 4 · Confirm you submitted")).toBeVisible();
  const confirm = page.getByRole("button", { name: "Confirm submission" });
  await expect(confirm).toBeDisabled();
  await page.getByLabel("I have submitted this application on the employer's site").check();
  await confirm.click();
  await expect(page.getByText(/^Submitted .* Track progress from the/)).toBeVisible();
  await expect(page.getByText("Submitted (confirmed)").first()).toBeVisible();

  // Tracker shows it with history
  await page.getByRole("link", { name: "Tracker" }).first().click();
  const applied = page.getByRole("region", { name: /Applied column, 1 applications/ });
  await expect(applied.getByText("Machine Learning Engineer")).toBeVisible();

  // Analytics derived from stored records
  await page.getByRole("link", { name: "Analytics" }).click();
  await expect(page.getByText(/1 submitted/)).toBeVisible();
  await expect(page.getByText("Insufficient data").first()).toBeVisible();
});

test("unauthenticated users are sent to sign in", async ({ page }) => {
  await page.goto("/tracker");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
});
