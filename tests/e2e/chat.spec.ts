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

  test("full chat conversation with SSE mock", async ({ page }) => {
    // Build SSE response chunks
    const sseChunks = [
      `data: ${JSON.stringify({ type: "session", content: { session_id: "test-session-123" } })}\n\n`,
      `data: ${JSON.stringify({ type: "text", content: "Hello! " })}\n\n`,
      `data: ${JSON.stringify({ type: "text", content: "I am Aureon. " })}\n\n`,
      `data: ${JSON.stringify({ type: "text", content: "How can I help?" })}\n\n`,
      `data: ${JSON.stringify({ type: "sources", content: [{ title: "Guide", slug: "guide", score: 0.95 }] })}\n\n`,
      `data: ${JSON.stringify({ type: "done" })}\n\n`,
    ];

    // Mock the SSE endpoint
    await page.route("**/api/chat/**", async (route) => {
      await route.fulfill({
        status: 200,
        headers: {
          "Content-Type": "text/event-stream",
          "Cache-Control": "no-cache",
          Connection: "keep-alive",
        },
        body: sseChunks.join(""),
      });
    });

    await page.goto("/chat");

    // Wait for the chat input to be visible
    const input = page.locator('[data-testid="chat-input"], textarea').first();
    await expect(input).toBeVisible({ timeout: 10000 });

    // Type and send a message
    await input.fill("What is RAG?");
    await input.press("Enter");

    // Wait for the response text to appear
    await expect(page.locator("body")).toContainText("How can I help?", { timeout: 15000 });

    // Verify user message appeared
    await expect(page.locator("body")).toContainText("What is RAG?");
  });
});
