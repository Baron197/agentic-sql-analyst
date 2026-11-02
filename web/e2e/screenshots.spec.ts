import { expect, test } from "@playwright/test";

// Screenshots for review and the README: `npm run screenshots` (writes docs/screenshots/).
const OUT = "../docs/screenshots";
const QUESTION = "What was net revenue by sales channel in Q1 2026?";

// Real gpt-6-luna runs, replayed from data/recorded_runs.json: public and free (no model call).
// The README uses these. Run against the live stack so the header shows the live model:
// PLAYWRIGHT_BASE_URL=http://127.0.0.1:8088 npx playwright test screenshots -g recorded
for (const { name, question, width, height } of [
  { name: "recorded-answer-desktop-1280", question: QUESTION, width: 1280, height: 900 },
  { name: "recorded-answer-mobile-375", question: QUESTION, width: 375, height: 812 },
  {
    name: "recorded-refusal-desktop-1280",
    question: "Delete all orders from 2024.",
    width: 1280,
    height: 900,
  },
]) {
  test(`recorded run ${name}`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await page.goto("/recorded");
    await page.getByRole("link", { name: question }).click();
    await expect(page.getByRole("heading", { name: question })).toBeVisible();
    if (question === QUESTION) {
      await expect(page.locator(".recharts-bar-rectangle").first()).toBeVisible();
    }
    await page.mouse.move(0, 0);
    await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true });
  });
}

for (const { name, width, height } of [
  { name: "desktop-1280", width: 1280, height: 900 },
  { name: "mobile-375", width: 375, height: 812 },
]) {
  test(`ask page at ${width}px`, async ({ page }) => {
    const password = process.env.DEMO_ANALYST_PASSWORD;
    test.skip(!password, "DEMO_ANALYST_PASSWORD is not set");
    await page.setViewportSize({ width, height });

    await page.goto("/login");
    await page.screenshot({ path: `${OUT}/login-${name}.png` });
    await page.getByLabel("Email").fill("analyst@demo");
    await page.getByLabel("Password").fill(password!);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();

    await page.getByRole("button", { name: QUESTION }).click();
    await expect(page.getByRole("region", { name: "Answer" })).toContainText("In Q1 2026", {
      timeout: 30_000,
    });
    await expect(page.locator(".recharts-bar-rectangle").first()).toBeVisible();
    await page.mouse.move(0, 0);
    await page.screenshot({ path: `${OUT}/ask-${name}.png`, fullPage: true });
  });
}
