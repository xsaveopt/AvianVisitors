import { test, expect } from '@playwright/test';

const USER = process.env.AV_E2E_USER ?? 'admin';
const PASS = process.env.AV_E2E_PASSWORD ?? 'e2e-secret';
const basic = 'Basic ' + Buffer.from(`${USER}:${PASS}`).toString('base64');

test('listen-back is greyed out before login', async ({ page }) => {
  await page.goto('/');
  await page.click('#winPick button[data-h="1000000"]');
  await page.click('.slider button[data-i="2"]');

  await expect(page.locator('body')).not.toHaveClass(/\bauthed\b/);

  const play = page.locator('#atlasGrid .bird-card .chip.play').first();
  await expect(play).toBeVisible();
  const opacity = await play.evaluate((el) => parseFloat(getComputedStyle(el).opacity));
  expect(opacity).toBeLessThan(1);
});

test('the tools menu stays locked until the password is entered', async ({ page }) => {
  await page.goto('/');
  await page.click('#menuBtn');
  await expect(page.locator('#dd-locked')).toBeVisible();
  await expect(page.locator('#dd-items')).not.toHaveClass(/\bshow\b/);
});

test('logging in unlocks tools and enables listen-back', async ({ page }) => {
  await page.goto('/');
  await page.click('#menuBtn');
  await page.fill('#lockPass', PASS);
  await page.click('#unlockForm button[type="submit"]');

  await expect(page.locator('#dd-items')).toContainText('settings');
  await expect(page.locator('#dd-items')).toContainText('logs');
  await expect(page.locator('body')).toHaveClass(/\bauthed\b/);
});

test('wrong password keeps it locked', async ({ page }) => {
  await page.goto('/');
  await page.click('#menuBtn');
  await page.fill('#lockPass', 'not-the-password');
  await page.click('#unlockForm button[type="submit"]');

  await expect(page.locator('#lockHint')).toContainText('wrong password');
  await expect(page.locator('body')).not.toHaveClass(/\bauthed\b/);
});

test('protected API rejects anonymous and allows authenticated requests', async ({ request }) => {
  expect((await request.get('/api/menu')).status()).toBe(401);
  expect((await request.get('/api/recording?sci=Calypte%20anna')).status()).toBe(401);

  const authed = await request.get('/api/menu', { headers: { Authorization: basic } });
  expect(authed.status()).toBe(200);
});

test('public API stays open without credentials', async ({ request }) => {
  expect((await request.get('/api/stats')).status()).toBe(200);
  expect((await request.get('/api/illustration?sci=Calypte%20anna')).status()).toBe(200);
});
