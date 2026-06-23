// 视觉回归测试 — 关键页面截图对比
//
// 首次运行会生成基线截图（存储在 tests/e2e/__screenshots__ 目录）
// 后续运行会与基线对比，允许 1% 像素差异（maxDiffPixelRatio: 0.01）
//
// 注意：
// - 实际路由参考 src/App.tsx：/, /dashboard, /search, /documents, /crew
// - 项目中没有 /chat 路由，聊天功能集成在 Landing 页面
// - 受保护页面（/analytics, /admin, /cost）需要认证，不纳入视觉回归
// - 动态内容（时间戳、随机数据）通过 networkidle 等待稳定

import { test, expect } from "@playwright/test";

test.describe("视觉回归测试", () => {
  test("Landing 页面", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await expect(page).toHaveScreenshot("landing.png", {
      maxDiffPixelRatio: 0.01,
      fullPage: true,
    });
  });

  test("Dashboard 页面", async ({ page }) => {
    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");
    await expect(page).toHaveScreenshot("dashboard.png", {
      maxDiffPixelRatio: 0.01,
      fullPage: true,
    });
  });

  test("Search 页面", async ({ page }) => {
    await page.goto("/search");
    await page.waitForLoadState("networkidle");
    await expect(page).toHaveScreenshot("search.png", {
      maxDiffPixelRatio: 0.01,
      fullPage: true,
    });
  });

  test("Documents 页面", async ({ page }) => {
    await page.goto("/documents");
    await page.waitForLoadState("networkidle");
    await expect(page).toHaveScreenshot("documents.png", {
      maxDiffPixelRatio: 0.01,
      fullPage: true,
    });
  });

  test("Crew Generator 页面", async ({ page }) => {
    await page.goto("/crew");
    await page.waitForLoadState("networkidle");
    await expect(page).toHaveScreenshot("crew.png", {
      maxDiffPixelRatio: 0.01,
      fullPage: true,
    });
  });
});
