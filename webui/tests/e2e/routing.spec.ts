import { test, expect } from '@playwright/test';

test('deep link to a species opens its modal', async ({ page }) => {
  await page.goto('/#sci=' + encodeURIComponent('Calypte anna'));
  await expect(page.locator('#detail-modal')).toHaveAttribute('aria-hidden', 'false');
  await expect(page.locator('#modalCommon')).toContainText("Anna's Hummingbird");
});

test('about modal opens from the title and closes', async ({ page }) => {
  await page.goto('/');
  await page.click('#aboutLink');
  await expect(page.locator('#about-modal')).toHaveAttribute('aria-hidden', 'false');
  await page.click('#about-modal .modal-close');
  await expect(page.locator('#about-modal')).toHaveAttribute('aria-hidden', 'true');
});
