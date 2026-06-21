import { test, expect, type Page } from '@playwright/test';

const USER = process.env.AV_E2E_USER ?? 'admin';
const PASS = process.env.AV_E2E_PASSWORD ?? 'e2e-secret';

async function login(page: Page): Promise<void> {
  await page.click('#menuBtn');
  await page.fill('#lockUser', USER);
  await page.fill('#lockPass', PASS);
  await page.click('#unlockForm button[type="submit"]');
  await expect(page.locator('body')).toHaveClass(/\bauthed\b/);
  await page.click('#menuBtn');
}

async function openAnna(page: Page): Promise<void> {
  await page.click('#winPick button[data-h="1000000"]');
  await page.click('.slider button[data-i="2"]');
  await page.locator('#atlasGrid .bird-card', { hasText: "Anna's Hummingbird" }).first().click();
  await expect(page.locator('#detail-modal')).toHaveAttribute('aria-hidden', 'false');
}

test('a recording row expands to reveal its spectrogram strip', async ({ page }) => {
  await page.goto('/');
  await login(page);
  await openAnna(page);

  const row = page.locator('#modalRecordings .rec-row').first();
  await expect(row).toBeVisible();
  await expect(row).not.toHaveClass(/\bexpanded\b/);

  await row.locator('.when').click();
  await expect(row).toHaveClass(/\bexpanded\b/);
  await expect(row.locator('.rec-spectro')).toBeVisible();

  await row.locator('.when').click();
  await expect(row).not.toHaveClass(/\bexpanded\b/);
});

test('the play control is interactive once authed', async ({ page }) => {
  await page.goto('/');
  await login(page);
  await openAnna(page);

  const play = page.locator('#modalRecordings .rec-row .play').first();
  await expect(play).toBeVisible();
  const opacity = await play.evaluate((el) => parseFloat(getComputedStyle(el).opacity));
  expect(opacity).toBeCloseTo(1, 1);

  await play.click();
  await expect(page.locator('#modalRecordings .rec-row').first()).toHaveClass(/\bexpanded\b/);
});

test('live audio control is hidden until login and appears after', async ({ page }) => {
  await page.goto('/');
  await page.click('#menuBtn');
  await expect(page.locator('#dd-items')).not.toHaveClass(/\bshow\b/);

  await page.fill('#lockUser', USER);
  await page.fill('#lockPass', PASS);
  await page.click('#unlockForm button[type="submit"]');
  await expect(page.locator('#dd-items')).toHaveClass(/\bshow\b/);

  await expect(page.locator('#liveAudio')).toBeVisible();
  await expect(page.locator('#liveAudioBtn')).toContainText('listen');
});
