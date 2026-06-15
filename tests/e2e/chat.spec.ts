import { test, expect } from "@playwright/test";

test.describe("Chat Flow", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
  });

  test("landing page loads correctly", async ({ page }) => {
    // Check that the page title or main heading is present
    await expect(page.locator("h1, [data-testid='landing-heading']")).toBeVisible();
  });

  test("can navigate to chat page", async ({ page }) => {
    // Look for a chat link/button and navigate
    const chatLink = page.locator('a[href*="chat"], button:has-text("Chat"), a:has-text("Chat")');
    if (await chatLink.count() > 0) {
      await chatLink.first().click();
      await page.waitForURL("**/chat**");
    } else {
      // Direct navigation fallback
      await page.goto("/chat");
    }

    // Chat input should be visible
    await expect(page.locator('textarea, input[type="text"], [contenteditable]')).toBeVisible();
  });

  test("chat input accepts text", async ({ page }) => {
    await page.goto("/chat");

    const input = page.locator('textarea, input[type="text"]').first();
    await expect(input).toBeVisible();

    await input.fill("Hello, Aureon!");
    await expect(input).toHaveValue("Hello, Aureon!");
  });

  test("chat send button is disabled when input is empty", async ({ page }) => {
    await page.goto("/chat");

    const sendButton = page.locator('button[type="submit"], button:has-text("Send")').first();
    if (await sendButton.count() > 0) {
      await expect(sendButton).toBeDisabled();
    }
  });
});
