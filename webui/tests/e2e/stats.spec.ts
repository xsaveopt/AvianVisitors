import { test, expect } from '@playwright/test';

test('stats view shows period totals and the timeline', async ({ page }) => {
  await page.goto('/');
  await page.click('.slider button[data-i="1"]');

  await expect(page.locator('#statsByPeriod li')).toHaveCount(4);
  await expect(page.locator('#statsByPeriod')).toContainText('7');
  await expect(page.locator('#statsTimeline .stats-tl-col').first()).toBeVisible();
});

test('species modal shows genus/rarity meta', async ({ page }) => {
  await page.goto('/#sci=' + encodeURIComponent('Calypte anna'));
  await expect(page.locator('#detail-modal')).toHaveAttribute('aria-hidden', 'false');
  await expect(page.locator('#modalGenus')).toHaveText('Calypte');
  await expect(page.locator('#modalRarity')).toBeVisible();
});
