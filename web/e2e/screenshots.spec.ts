import { expect, test } from "@playwright/test";

// Screenshots for review and the README: `npm run screenshots` (writes docs/screenshots/).
const OUT = "../docs/screenshots";
const QUESTION = "What was net revenue by sales channel in Q1 2026?";

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
