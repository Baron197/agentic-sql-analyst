import { expect, test } from "@playwright/test";

// Keyless end to end: sign in, ask a demo question, see the steps, SQL, table, and answer.
// Everything but the model is real: API, retrieval, validator, read-only executor, RLS.
test("sign in, ask a demo question, see the evidence", async ({ page }) => {
  const password = process.env.DEMO_ANALYST_PASSWORD;
  test.skip(!password, "DEMO_ANALYST_PASSWORD is not set (in the environment or ../.env)");

  await page.goto("/");
  await expect(page).toHaveURL(/\/login$/);
  await page.getByLabel("Email").fill("analyst@demo");
  await page.getByLabel("Password").fill(password!);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();

  await expect(page.getByRole("heading", { name: "Ask the data" })).toBeVisible();
  await page
    .getByRole("button", { name: "What was net revenue by sales channel in Q1 2026?" })
    .click();

  const answer = page.getByRole("region", { name: "Answer" });
  await expect(answer).toContainText("In Q1 2026", { timeout: 30_000 });
  await expect(answer).toContainText("Numbers filled from the query result");

  const steps = page.getByRole("region", { name: "Steps" });
  for (const step of [
    "Check the question",
    "Write SQL",
    "Validate the SQL",
    "Fill in the numbers",
  ]) {
    await expect(steps).toContainText(step);
  }
  await expect(page.getByRole("region", { name: /SQL/ })).toContainText("analytics.fact_orders");
  const table = page.getByRole("table");
  await expect(table.getByRole("columnheader")).toContainText(["channel_name", "net_revenue_idr"]);
  await expect(table.getByRole("row")).toHaveCount(5); // header + 4 channels
  await expect(page.getByText("Keyless demo")).toBeVisible();
});
