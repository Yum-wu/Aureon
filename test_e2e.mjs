import { chromium } from 'playwright';

const BASE = 'https://aureon-production-659a.up.railway.app';
const results = [];
const record = (page, test, status, detail = '') =>
  results.push({ page, test, status, detail });

(async () => {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await ctx.newPage();

  const consoleErrors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });

  // ── 1. Landing ──
  console.log('=== 1. Landing ===');
  try {
    await page.goto(BASE, { waitUntil: 'networkidle', timeout: 20000 });
    await page.screenshot({ path: '/tmp/aureon_01_landing.png', fullPage: true });
    record('Landing', 'Hero visible', (await page.locator('text=企业 AI 知识库平台').first().isVisible()) ? 'PASS' : 'FAIL');
    record('Landing', 'CTA visible', (await page.locator('text=开始搜索').first().isVisible()) ? 'PASS' : 'FAIL');
    record('Landing', 'Features visible', (await page.locator('text=核心功能').first().isVisible()) ? 'PASS' : 'FAIL');
    record('Landing', 'Logo visible', (await page.locator('text=Aureon').first().isVisible()) ? 'PASS' : 'FAIL');
  } catch (e) { record('Landing', 'Load', 'FAIL', e.message.slice(0,200)); }

  // ── 2. Login + Demo ──
  console.log('=== 2. Login ===');
  try {
    await page.goto(`${BASE}/login`, { waitUntil: 'networkidle', timeout: 20000 });
    await page.screenshot({ path: '/tmp/aureon_02_login.png' });
    record('Login', 'Email input', (await page.locator('input[type="email"]').isVisible()) ? 'PASS' : 'FAIL');
    record('Login', 'Password input', (await page.locator('input[type="password"]').isVisible()) ? 'PASS' : 'FAIL');
    record('Login', 'Submit button', (await page.locator('button[type="submit"]').isVisible()) ? 'PASS' : 'FAIL');
    const demoBtn = page.locator('text=使用演示账号登录').first();
    record('Login', 'Demo account button', (await demoBtn.isVisible()) ? 'PASS' : 'FAIL');
    if (await demoBtn.isVisible()) {
      await demoBtn.click();
      await page.waitForTimeout(5000);
      await page.screenshot({ path: '/tmp/aureon_02b_after_demo.png' });
      const url = page.url();
      record('Login', 'Demo redirects', (url.includes('/dashboard') || url.includes('/search')) ? 'PASS' : 'FAIL', `url=${url}`);
    }
  } catch (e) { record('Login', 'Load', 'FAIL', e.message.slice(0,200)); }

  // ── 3. Dashboard ──
  console.log('=== 3. Dashboard ===');
  try {
    await page.goto(`${BASE}/dashboard`, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(2000);
    await page.screenshot({ path: '/tmp/aureon_03_dashboard.png', fullPage: true });
    const title = await page.locator('text=系统总览').first().isVisible();
    const gate = await page.locator('text=需要管理员权限').first().isVisible();
    if (title) record('Dashboard', 'Dashboard loaded', 'PASS');
    else if (gate) record('Dashboard', 'AdminGate (needs login)', 'PASS');
    else record('Dashboard', 'Loaded (unknown)', 'WARN');
  } catch (e) { record('Dashboard', 'Load', 'FAIL', e.message.slice(0,200)); }

  // ── 4. Search (uses SearchBar + StreamingAnswer, not ChatWidget) ──
  console.log('=== 4. Search ===');
  try {
    await page.goto(`${BASE}/search`, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(2000);
    await page.screenshot({ path: '/tmp/aureon_04_search.png' });
    // Search page uses SearchBar component, not ChatWidget
    const searchInput = page.locator('input[type="text"], input[placeholder]').first();
    const textarea = page.locator('textarea').first();
    const hasInput = await searchInput.isVisible().catch(() => false) || await textarea.isVisible().catch(() => false);
    record('Search', 'Input element visible', hasInput ? 'PASS' : 'FAIL');
    // Try to find suggestion cards or any interactive elements
    const body = await page.textContent('body');
    const hasSuggestions = body.includes('试试这样问') || body.includes('总结') || body.includes('搜索');
    record('Search', 'Content rendered', hasSuggestions ? 'PASS' : 'FAIL');
    if (hasInput) {
      const input = await searchInput.isVisible().catch(() => false) ? searchInput : textarea;
      await input.fill('RAG 检索准确率是多少？');
      // Find and click search/submit button
      const searchBtn = page.locator('button[type="submit"], button:has-text("搜索"), button:has-text("Search")').first();
      if (await searchBtn.isVisible().catch(() => false)) {
        await searchBtn.click();
      } else {
        await page.keyboard.press('Enter');
      }
      await page.waitForTimeout(5000);
      await page.screenshot({ path: '/tmp/aureon_04b_after_search.png' });
      record('Search', 'Query submitted', 'PASS');
    }
  } catch (e) { record('Search', 'Load', 'FAIL', e.message.slice(0,200)); }

  // ── 5. Documents ──
  console.log('=== 5. Documents ===');
  try {
    await page.goto(`${BASE}/documents`, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(2000);
    await page.screenshot({ path: '/tmp/aureon_05_documents.png', fullPage: true });
    const title = await page.locator('text=文档管理').first().isVisible();
    const gate = await page.locator('text=需要管理员权限').first().isVisible();
    if (title) record('Documents', 'Page loaded', 'PASS');
    else if (gate) record('Documents', 'AdminGate', 'PASS');
    else record('Documents', 'Loaded (unknown)', 'WARN');
  } catch (e) { record('Documents', 'Load', 'FAIL', e.message.slice(0,200)); }

  // ── 6. Admin ──
  console.log('=== 6. Admin ===');
  try {
    await page.goto(`${BASE}/admin`, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(1500);
    await page.screenshot({ path: '/tmp/aureon_06_admin.png' });
    const gate = await page.locator('text=需要管理员权限').first().isVisible();
    const layout = await page.locator('text=用户管理').first().isVisible();
    record('Admin', gate ? 'AdminGate shown' : 'Admin page loaded', (gate || layout) ? 'PASS' : 'FAIL');
  } catch (e) { record('Admin', 'Load', 'FAIL', e.message.slice(0,200)); }

  // ── 7. Cost ──
  console.log('=== 7. Cost ===');
  try {
    await page.goto(`${BASE}/cost`, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(1500);
    await page.screenshot({ path: '/tmp/aureon_07_cost.png' });
    const gate = await page.locator('text=需要管理员权限').first().isVisible();
    const title = await page.locator('text=成本治理').first().isVisible();
    record('Cost', (gate || title) ? 'OK' : 'FAIL', gate ? 'AdminGate' : title ? 'Page loaded' : 'unknown');
  } catch (e) { record('Cost', 'Load', 'FAIL', e.message.slice(0,200)); }

  // ── 8. Architecture ──
  console.log('=== 8. Architecture ===');
  try {
    await page.goto(`${BASE}/architecture`, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(1500);
    await page.screenshot({ path: '/tmp/aureon_08_architecture.png' });
    const gate = await page.locator('text=需要管理员权限').first().isVisible();
    const title = await page.locator('text=架构').first().isVisible();
    record('Architecture', (gate || title) ? 'OK' : 'FAIL', gate ? 'AdminGate' : 'Page loaded');
  } catch (e) { record('Architecture', 'Load', 'FAIL', e.message.slice(0,200)); }

  // ── 9. Mobile ──
  console.log('=== 9. Mobile ===');
  try {
    const mobile = await browser.newContext({ viewport: { width: 375, height: 812 } });
    const mp = await mobile.newPage();
    await mp.goto(BASE, { waitUntil: 'networkidle', timeout: 15000 });
    await mp.screenshot({ path: '/tmp/aureon_09_mobile.png', fullPage: true });
    record('Mobile', 'Landing loads', 'PASS');
    await mp.goto(`${BASE}/search`, { waitUntil: 'networkidle', timeout: 15000 });
    await mp.waitForTimeout(1500);
    await mp.screenshot({ path: '/tmp/aureon_09b_mobile_search.png' });
    record('Mobile', 'Search loads', 'PASS');
    const hamburger = await mp.locator('button[aria-label]').first().isVisible().catch(() => false);
    record('Mobile', 'Hamburger menu', hamburger ? 'PASS' : 'FAIL');
    await mobile.close();
  } catch (e) { record('Mobile', 'Load', 'FAIL', e.message.slice(0,200)); }

  // ── 10. 404 ──
  console.log('=== 10. 404 ===');
  try {
    await page.goto(`${BASE}/nonexistent-xyz-123`, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(1000);
    await page.screenshot({ path: '/tmp/aureon_10_404.png' });
    const nf = await page.locator('text=404').first().isVisible();
    record('404', 'Not found page', nf ? 'PASS' : 'FAIL');
  } catch (e) { record('404', 'Load', 'FAIL', e.message.slice(0,200)); }

  // ── Console Errors ──
  console.log('\n=== Console Errors ===');
  const critical = consoleErrors.filter(e => !e.includes('favicon') && !e.includes('401'));
  if (critical.length) {
    for (const err of critical.slice(0, 10)) record('Console', 'ERROR', 'FAIL', err.slice(0, 200));
  } else {
    record('Console', 'No critical errors', 'PASS');
  }

  await browser.close();

  // ── Summary ──
  console.log('\n' + '='.repeat(60));
  console.log('AUREON E2E TEST RESULTS');
  console.log('='.repeat(60));
  const pass = results.filter(r => r.status === 'PASS').length;
  const fail = results.filter(r => r.status === 'FAIL').length;
  const warn = results.filter(r => r.status === 'WARN').length;
  for (const r of results) {
    const icon = r.status === 'PASS' ? '✅' : r.status === 'FAIL' ? '❌' : '⚠️';
    const d = r.detail ? ` (${r.detail})` : '';
    console.log(`  ${icon} [${r.page}] ${r.test}${d}`);
  }
  console.log(`\n  Total: ${pass+fail+warn} | PASS: ${pass} | FAIL: ${fail} | WARN: ${warn}`);
  process.exit(fail > 0 ? 1 : 0);
})();
