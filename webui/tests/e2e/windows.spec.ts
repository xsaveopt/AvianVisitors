import { test, expect, type Page } from '@playwright/test';

async function selectWindow(page: Page, hours: string): Promise<void> {
  await page.click(`#winPick button[data-h="${hours}"]`);
  await page.click('.slider button[data-i="2"]');
  await expect(page.locator('#atlasGrid .bird-card').first()).toBeVisible();
}

test('the window picker narrows the atlas to the selected period', async ({ page }) => {
  await page.goto('/');

  await selectWindow(page, '24');
  await expect(page.locator('#atlasGrid .bird-card')).toHaveCount(2);

  await selectWindow(page, '168');
  await expect(page.locator('#atlasGrid .bird-card')).toHaveCount(3);

  await selectWindow(page, '1000000');
  await expect(page.locator('#atlasGrid .bird-card')).toHaveCount(4);
});

test('the selected window button is marked current', async ({ page }) => {
  await page.goto('/');
  await page.click('#winPick button[data-h="168"]');
  await expect(page.locator('#winPick button[data-h="168"]')).toHaveAttribute('aria-current', 'true');
  await expect(page.locator('#winPick button[data-h="24"]')).toHaveAttribute('aria-current', 'false');
});
