#!/usr/bin/env node
/**
 * Browser end-to-end check against a running app. It also captures the screenshots in docs/screenshots.
 * Needs: backend on API_URL, frontend on APP_URL, and Microsoft Edge or Chrome installed.
 *   E2E_FIXTURES=<folder with sample images> npm run e2e
 * The account it creates uses example.com and a random password; run it against a throwaway database.
 */
import { randomBytes } from "node:crypto";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const here = dirname(fileURLToPath(import.meta.url));
const APP = process.env.APP_URL ?? "http://127.0.0.1:4173";
const FIXTURES = resolve(process.env.E2E_FIXTURES ?? join(here, "fixtures"));
const SHOTS = resolve(process.env.E2E_SHOTS ?? join(here, "..", "..", "docs", "screenshots"));
const CHANNEL = process.env.E2E_BROWSER ?? "msedge";
mkdirSync(SHOTS, { recursive: true });

const results = [];
const consoleErrors = [];
function pass(name) {
  results.push({ name, ok: true });
  console.log(`PASS  ${name}`);
}
function assert(condition, name) {
  if (!condition) throw new Error(`Assertion failed: ${name}`);
  pass(name);
}

const browser = await chromium.launch({ channel: CHANNEL, headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, acceptDownloads: true, colorScheme: "dark" });
const page = await context.newPage();
page.on("pageerror", (error) => consoleErrors.push(`pageerror: ${error.message}`));
page.on("console", (message) => {
  // The browser logs expected 4xx responses, which this test provokes on purpose, as console errors.
  if (message.type() === "error" && !/status of 4\d\d/.test(message.text())) consoleErrors.push(message.text());
});
const shot = async (name, options = {}) => {
  await page.locator("[data-toast]").first().waitFor({ state: "detached", timeout: 12000 }).catch(() => undefined);
  await page.screenshot({ path: join(SHOTS, `${name}.png`), ...options });
};
const nav = (name) => page.getByRole("navigation", { name: "Main" }).getByRole("link", { name, exact: true }).click();
const settle = () => page.waitForLoadState("networkidle");
const email = `reviewer-${randomBytes(4).toString("hex")}@example.com`;
const password = randomBytes(18).toString("base64url");

try {
  // Authentication ---------------------------------------------------------------------------------
  await page.goto(`${APP}/analytics`);
  await page.getByRole("heading", { name: "Sign in" }).waitFor();
  pass("Protected route redirects to sign-in");
  await page.getByLabel("E-mail").fill("nobody@example.com");
  await page.getByLabel("Password").fill("definitely-wrong");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByText("Incorrect e-mail or password.").waitFor();
  pass("Wrong password shows an error");
  await page.getByRole("link", { name: "Create an account" }).click();
  await page.getByLabel("Full name").fill("Demo Reviewer");
  await page.getByLabel("E-mail").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Create account" }).click();
  await page.getByText("Inspection History").waitFor();
  pass("Registration signs the user in");
  await nav("Analytics");
  await page.getByText("No inspection records yet").waitFor();
  pass("Analytics shows an empty state, not invented numbers");
  await nav("Overview");
  await page.getByText("No inspections yet").waitFor();
  pass("Dashboard shows an empty state for a new account");

  // Real inspection --------------------------------------------------------------------------------
  await nav("New Inspection");
  await page.getByLabel("Project name").fill("Workshop surface survey");
  await page.getByLabel("Inspection category").selectOption("surface_material");
  await page.getByTestId("file-input").setInputFiles([
    join(FIXTURES, "demo_steel_plate.png"), join(FIXTURES, "demo_concrete_wall.png"), join(FIXTURES, "not-an-image.png"), join(FIXTURES, "notes.txt"),
  ]);
  await page.getByText("Use JPEG, PNG or WebP. This file will not be uploaded.").waitFor();
  pass("Unsupported file is flagged before upload");
  await page.getByRole("button", { name: "Remove notes.txt" }).click();
  await page.getByLabel("Description for demo_steel_plate.png").fill("Fixture plate, front face");
  await settle();
  await shot("02-new-inspection");
  await page.getByRole("button", { name: /Run analysis on 3 images/ }).click();
  await page.waitForURL(/\/inspections\/[0-9a-f-]{36}$/);
  pass("Disguised file does not stop the valid uploads");
  await page.getByText("2 of 2 images").first().waitFor({ state: "attached", timeout: 3000 }).catch(() => undefined);
  await page.getByText("Requires review", { exact: true }).first().waitFor({ timeout: 90000 });
  pass("Background analysis finishes and the project needs review");
  const thumbs = await page.getByRole("option").count();
  assert(thumbs === 2, "Only the 2 valid images were stored");
  await settle();

  const rows = page.locator("aside button[aria-pressed]");
  await rows.first().waitFor();
  assert((await rows.count()) >= 1, "Findings are listed with bands and review status");
  await page.getByText("Not assessed", { exact: true }).waitFor();
  pass("Unsupported checks are stated");
  await page.getByRole("img", { name: "Detection overlays" }).waitFor();
  pass("Overlays are drawn over the image");
  await rows.first().click();
  await page.getByText("Decision history").waitFor({ state: "detached", timeout: 500 }).catch(() => undefined);
  await page.getByLabel("Review note (optional)").fill("Checked at the bench, marks are real.");
  await page.getByRole("button", { name: "Confirmed" }).click();
  await page.getByText("Decision history").waitFor();
  pass("A review decision is saved with its history");
  await page.waitForTimeout(400);
  await shot("03-inspection-workspace");

  await page.getByLabel("Zoom in").click();
  await page.getByLabel("Zoom in").click();
  await page.getByLabel("Fit to screen").click();
  await page.getByRole("button", { name: "Processed" }).click();
  await page.waitForTimeout(500);
  await page.getByRole("button", { name: "Original" }).click();
  await page.getByLabel("Findings").uncheck();
  assert((await page.locator("svg[aria-label='Detection overlays'] polygon").count()) === 0, "The findings overlay can be hidden");
  await page.getByLabel("Findings").check();

  await page.getByRole("tab", { name: /Assistant/ }).click();
  await page.getByRole("button", { name: "Can you summarise this inspection?" }).click();
  await page.getByText("From stored records").first().waitFor();
  await page.getByLabel("Question").fill("Which findings have not been reviewed?");
  await page.getByRole("button", { name: "Send" }).click();
  await page.getByText(/findings have not been reviewed:/).waitFor();
  pass("Assistant answers from inspection records without external AI");
  await page.waitForTimeout(300);
  await shot("07-ai-assistant");

  await page.reload();
  await page.getByRole("heading", { name: "Workshop surface survey" }).waitFor();
  pass("A deep link survives a browser refresh");

  // Report -----------------------------------------------------------------------------------------
  await page.getByRole("button", { name: "Generate report" }).click();
  await page.getByLabel("Final inspection notes").fill("Marks on the plate need a closer look before the next shift.");
  await page.getByRole("button", { name: "Generate PDF" }).click();
  await page.waitForURL(/\/reports/);
  await page.locator("iframe").waitFor({ timeout: 30000 });
  pass("A report is generated and opens for preview");
  await page.getByRole("button", { name: "Close" }).click();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download", exact: true }).first().click();
  const download = await downloadPromise;
  await download.saveAs(join(process.env.E2E_OUTPUT ?? SHOTS, "e2e-report.pdf"));
  assert(download.suggestedFilename().endsWith(".pdf"), "The report downloads as a PDF");
  await settle();
  await shot("08-reports");

  // Isolation between real data and the demo -------------------------------------------------------
  await nav("Overview");
  await page.getByText("Total inspections").waitFor();
  await nav("Settings");
  await page.getByRole("button", { name: "Create demo workspace" }).click();
  await page.getByText("You are viewing a demo workspace").waitFor({ timeout: 90000 });
  pass("Demo workspace is created and clearly labelled");
  await nav("Overview");
  await page.getByText("Total inspections").waitFor();
  await settle();
  await page.waitForTimeout(1200);
  await shot("01-dashboard");

  await nav("Inspection History");
  await page.getByLabel("Search projects").fill("recognition");
  await page.getByRole("link", { name: /Object recognition sample/ }).waitFor();
  await settle();
  await page.getByRole("link", { name: /Object recognition sample/ }).click();
  await page.getByRole("tab", { name: /Objects/ }).click();
  await settle();
  await page.getByRole("button", { name: /^cup/i }).or(page.getByRole("button", { name: /^cat/i })).first().waitFor();
  pass("The real YOLOX model detected objects in sample photos");
  await page.getByRole("button", { name: /^cup/i }).first().click().catch(() => undefined);
  await page.waitForTimeout(800);
  await shot("04-object-detection");

  await nav("Inspection History");
  await page.getByLabel("Search projects").fill("Surface condition");
  await settle();
  await page.getByRole("link", { name: /Surface condition survey/ }).click();
  await settle();
  await page.getByRole("option").nth(1).click();
  await settle();
  await page.waitForTimeout(800);
  await shot("05-defect-highlighting");

  await nav("Image Comparison");
  await page.getByRole("link", { name: /Wall before and after/ }).click();
  await page.getByRole("button", { name: "Side by side" }).waitFor();
  await settle();
  await shot("06-image-comparison");
  await page.getByRole("button", { name: "Overlay" }).click();
  await page.getByLabel("Overlay transparency").fill("0.7");
  await page.getByRole("button", { name: "Difference", exact: true }).click();
  await settle();
  await page.waitForTimeout(400);
  await shot("06b-comparison-difference");
  pass("All three comparison views work");

  await nav("Image Comparison");
  await page.getByTestId("file-input").first().setInputFiles(join(FIXTURES, "demo_before.png"));
  await page.getByTestId("file-input").first().setInputFiles(join(FIXTURES, "demo_after.png"));
  await page.getByRole("button", { name: "Compare" }).click();
  await page.waitForURL(/\/comparison\/[0-9a-f-]{36}$/);
  await page.getByText("Limitations", { exact: true }).waitFor({ timeout: 60000 });
  await page.getByText("Aligned", { exact: true }).waitFor();
  pass("A new comparison runs through the queue and aligns the images");

  for (const [name, heading, file] of [
    ["Defect Analysis", "Defect analysis", "10-defect-analysis"],
    ["Analytics", "Analytics", "09-analytics"],
    ["Model Information", "Model information", "11-model-information"],
    ["Settings", "Settings", "12-settings"],
  ]) {
    await nav(name);
    await page.getByRole("heading", { name: heading, exact: true }).waitFor();
    await settle();
    await page.waitForTimeout(1200);
    await shot(file);
  }
  pass("Every sidebar page opens");

  await nav("Model Information");
  await page.getByText("YOLOX-Tiny").first().waitFor();
  await page.getByText("Available").first().waitFor();
  pass("Model page shows real availability");

  // Responsive layout ------------------------------------------------------------------------------
  await page.setViewportSize({ width: 390, height: 844 });
  for (const path of ["/", "/inspections", "/comparison", "/analytics", "/settings", "/reports", "/defects", "/models", "/inspections/new"]) {
    await page.goto(`${APP}${path}`);
    await settle();
    const overflow = await page.evaluate(() => {
      const main = document.querySelector("main");
      const edge = window.innerWidth;
      const wide = [...document.querySelectorAll("main *")].filter((e) => e.getBoundingClientRect().right > edge + 1 && !e.closest(".overflow-x-auto, .overflow-auto, svg")).slice(0, 3);
      return { doc: document.documentElement.scrollWidth - edge, main: main ? main.scrollWidth - main.clientWidth : 0, wide: wide.map((e) => `${e.tagName}.${String(e.className).slice(0, 60)}`) };
    });
    assert(overflow.doc <= 1 && overflow.main <= 1, `No sideways overflow at phone width: ${path} ${overflow.doc > 1 || overflow.main > 1 ? JSON.stringify(overflow) : ""}`);
  }
  await page.goto(`${APP}/`);
  await settle();
  await page.waitForTimeout(800);
  await shot("13-mobile-dashboard");
  await page.getByRole("button", { name: "Open menu" }).click();
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Reports" }).click();
  await page.getByRole("heading", { name: "Reports", exact: true }).waitFor();
  pass("Phone menu works");
  await page.setViewportSize({ width: 1440, height: 900 });

  // Sign out and end -------------------------------------------------------------------------------
  await page.getByRole("button", { name: "Sign out" }).click();
  await page.getByRole("heading", { name: "Sign in" }).waitFor();
  await page.goto(`${APP}/`);
  await page.getByRole("heading", { name: "Sign in" }).waitFor();
  pass("Signing out ends the session");
  await shot("00-sign-in");

  assert(consoleErrors.length === 0, `No browser console errors${consoleErrors.length ? `: ${consoleErrors.join(" | ")}` : ""}`);
} catch (error) {
  results.push({ name: String(error.message).slice(0, 300), ok: false });
  console.error(`FAIL  ${error.message}`);
  if (consoleErrors.length) console.error("Console errors:", consoleErrors.slice(0, 5));
  await page.screenshot({ path: join(process.env.E2E_OUTPUT ?? SHOTS, "e2e-failure.png") }).catch(() => undefined);
  process.exitCode = 1;
} finally {
  await browser.close();
  if (process.env.E2E_OUTPUT) writeFileSync(join(process.env.E2E_OUTPUT, "e2e-results.json"), JSON.stringify(results, null, 2));
  console.log(`\n${results.filter((r) => r.ok).length} passed, ${results.filter((r) => !r.ok).length} failed`);
}
