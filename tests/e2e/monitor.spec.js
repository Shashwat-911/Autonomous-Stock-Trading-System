const { test, expect } = require('@playwright/test');

test('health and runner status expose a monitor without a trading worker', async ({ request }) => {
  const health = await request.get('/');
  expect(health.ok()).toBeTruthy();
  expect(await health.json()).toEqual({ status: 'healthy', service: 'Autonomous-Stock-Trading-System' });
  const status = await (await request.get('/status')).json();
  expect(status.source).toBe('playwright-fixture');
  expect(status.worker_running).toBe(false);
  expect(status.phase).toBe('MONITOR_ONLY');
});

test('session history renders the real monitor and escapes log HTML', async ({ page }) => {
  await page.goto('/logs');
  await expect(page).toHaveTitle('Trading Logs — Autonomous Stock Trader');
  await expect(page.getByRole('heading', { name: /Autonomous Stock Trader/ })).toBeVisible();
  await expect(page.locator('.log-content')).toContainText('PLAYWRIGHT SYNTHETIC SESSION');
  await expect(page.locator('.log-content')).toContainText('<script>window.logInjected=true</script>');
  expect(await page.evaluate(() => window.logInjected)).toBeUndefined();
  await page.getByRole('link', { name: 'session_2000_01_01.txt', exact: true }).click();
  await expect(page).toHaveURL(/\/logs\/session_2000_01_01.txt$/);
  await expect(page.locator('.log-content')).toContainText('AAPL');
});

test('missing session returns 404 and debug empty state remains usable', async ({ page, request }) => {
  expect((await request.get('/logs/session_missing.txt')).status()).toBe(404);
  await page.goto('/logs');
  await page.getByRole('link', { name: 'Debug Log' }).click();
  await expect(page.locator('.log-content')).toContainText('No debug log found.');
  await page.getByRole('link', { name: 'Latest Log' }).click();
  await expect(page.locator('.log-content')).toContainText('SYNTHETIC SESSION');
});

test('mobile log monitor keeps navigation visible', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/logs');
  await expect(page.getByRole('link', { name: 'Health', exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Latest Log' })).toBeVisible();
});
