import { test, expect, type Page } from '@playwright/test';

const USER = process.env.AV_E2E_USER ?? 'admin';
const PASS = process.env.AV_E2E_PASSWORD ?? 'e2e-secret';

async function login(page: Page): Promise<void> {
  await page.goto('/');
  await page.click('#menuBtn');
  await page.fill('#lockUser', USER);
  await page.fill('#lockPass', PASS);
  await page.click('#unlockForm button[type="submit"]');
  await expect(page.locator('body')).toHaveClass(/\bauthed\b/);
}

test('settings panel saves a pending change', async ({ page }) => {
  await login(page);
  await page.evaluate(() => {
    location.hash = '#admin=settings';
  });

  await expect(page.locator('#adminScreen')).toHaveAttribute('aria-hidden', 'false');
  await expect(page.locator('.admin-settings .switch')).toBeVisible();
  await expect(page.locator('#saveBtn')).toBeDisabled();

  await page.click('.admin-settings .switch');
  await expect(page.locator('#saveBtn')).toBeEnabled();

  await page.click('#saveBtn');
  await expect(page.locator('#saveState')).toContainText('saved');
});

test('system panel lists managed services', async ({ page }) => {
  await login(page);
  await page.evaluate(() => {
    location.hash = '#admin=system';
  });

  await expect(page.locator('#adminScreen')).toHaveAttribute('aria-hidden', 'false');
  await expect(page.locator('#adminServices')).toBeVisible();
});

test('admin config requires authentication', async ({ request }) => {
  expect((await request.get('/api/config')).status()).toBe(401);
});

test('logs panel polls and shows journal text', async ({ page }) => {
  await login(page);
  await page.evaluate(() => {
    location.hash = '#admin=logs';
  });

  await expect(page.locator('#adminScreen')).toHaveAttribute('aria-hidden', 'false');
  await expect(page.locator('#adminLogsUnit')).toBeVisible();
  await expect(page.locator('#adminLogsOut')).not.toHaveText('loading...');
});

test('tools panel restart button issues a request', async ({ page }) => {
  await login(page);
  await page.evaluate(() => {
    location.hash = '#admin=tools';
  });

  await expect(page.locator('#adminScreen')).toHaveAttribute('aria-hidden', 'false');
  const run = page.locator('.admin-action .run[data-unit="recording"]');
  await expect(run).toBeVisible();

  page.once('dialog', (d) => d.accept());
  const [res] = await Promise.all([
    page.waitForResponse((r) => r.url().includes('action=restart') && r.request().method() === 'POST'),
    run.click(),
  ]);
  expect(res.status()).toBe(200);
  await expect(page.locator('.out[data-out="recording"]')).not.toHaveText('');
});

test('theme switch toggles dark mode', async ({ page }) => {
  await login(page);
  await page.evaluate(() => {
    location.hash = '#admin=settings';
  });
  await expect(page.locator('#adminScreen')).toHaveAttribute('aria-hidden', 'false');

  await page.locator('[data-theme-seg] button', { hasText: 'dark' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');

  await page.locator('[data-theme-seg] button', { hasText: 'light' }).click();
  await expect(page.locator('html')).not.toHaveAttribute('data-theme', 'dark');
});
