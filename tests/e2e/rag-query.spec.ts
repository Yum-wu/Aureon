import { test, expect } from "@playwright/test";

test.describe("RAG Query Flow", () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to the RAG/search page
    await page.goto("/search");
  });

  test("RAG query page loads correctly", async ({ page }) => {
    // Title should be visible
    await expect(page.locator("h1")).toBeVisible();
  });

  test("search input accepts query", async ({ page }) => {
    const input = page.locator('input[type="text"]').first();
    await expect(input).toBeVisible();

    await input.fill("What is Aureon?");
    await expect(input).toHaveValue("What is Aureon?");
  });

  test("example query buttons are present", async ({ page }) => {
    // Should have example query buttons
    const exampleButtons = page.locator("button.rounded-full");
    const count = await exampleButtons.count();
    expect(count).toBeGreaterThan(0);
  });

  test("clicking example query fills the input", async ({ page }) => {
    const exampleButtons = page.locator("button.rounded-full");
    if (await exampleButtons.count() > 0) {
      await exampleButtons.first().click();

      const input = page.locator('input[type="text"]').first();
      const value = await input.inputValue();
      expect(value.length).toBeGreaterThan(0);
    }
  });

  test("upload panel toggles on button click", async ({ page }) => {
    const toggleButton = page.locator('button:has-text("upload"), button:has-text("Upload")').first();
    if (await toggleButton.count() > 0) {
      await toggleButton.click();
      // Upload area should appear
      await expect(page.locator('input[type="file"]')).toBeAttached();
    }
  });

  test("search history is shown when available", async ({ page }) => {
    // Set history in localStorage
    await page.evaluate(() => {
      localStorage.setItem(
        "aureon_search_history",
        JSON.stringify(["test query 1", "test query 2"]),
      );
    });

    // Reload to pick up localStorage
    await page.reload();

    // History items should appear
    await expect(page.locator('button:has-text("test query 1")')).toBeVisible();
    await expect(page.locator('button:has-text("test query 2")')).toBeVisible();
  });
});
