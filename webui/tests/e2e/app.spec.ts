import { test, expect } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.goto('/');
});

test('loads the collage view', async ({ page }) => {
  await expect(page).toHaveTitle(/birds/i);
  await expect(page.locator('#collage')).toBeVisible();
  await expect(page.locator('#collage .gtile').first()).toBeVisible();
  await expect(page.locator('.slider button[data-i="2"]')).toBeVisible();
});

test('atlas lists every species in the ALL window', async ({ page }) => {
  await page.click('#winPick button[data-h="1000000"]');
  await page.click('.slider button[data-i="2"]');

  const cards = page.locator('#atlasGrid .bird-card');
  await expect(cards.first()).toBeVisible();
  expect(await cards.count()).toBeGreaterThanOrEqual(4);
  await expect(page.locator('#atlasGrid')).toContainText('American Crow');
});

test('opens a species detail modal with its recordings', async ({ page }) => {
  await page.click('#winPick button[data-h="1000000"]');
  await page.click('.slider button[data-i="2"]');

  await page.locator('#atlasGrid .bird-card', { hasText: "Anna's Hummingbird" }).first().click();

  const modal = page.locator('#detail-modal');
  await expect(modal).toHaveAttribute('aria-hidden', 'false');
  await expect(modal.locator('#modalRecordings .rec-row').first()).toBeVisible();
});
