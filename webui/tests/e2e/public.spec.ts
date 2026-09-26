import { test, expect, type Page } from '@playwright/test';

async function routeRecent(page: Page, recent: Array<{ sci: string; com: string; ago: number }>): Promise<void> {
  await page.route('**/api/collage/recent', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ recent }) }),
  );
}

test('renders the public collage and recent captures from the live api', async ({ page }) => {
  const apiPaths: string[] = [];
  page.on('request', (req) => {
    const path = new URL(req.url()).pathname;
    if (path.startsWith('/api')) {
      apiPaths.push(path);
    }
  });

  await page.goto('/public.html');

  await expect(page).toHaveTitle(/your birds/i);
  await expect(page.locator('.static-head h1')).toHaveText('Heard Recently');
  await expect(page.locator('#collage .gtile').first()).toBeVisible();
  await expect(page.locator('#collage .gtile[data-sci="Calypte anna"]')).toHaveCount(1);
  await expect(page.locator('#collage .gtile[data-sci="Turdus migratorius"]')).toHaveCount(0);
  await expect(page.locator('#collage .gtile img').first()).toHaveAttribute(
    'src',
    /^api\/collage\/illustration\?sci=/,
  );

  const rows = page.locator('.pub-log .log-row');
  await expect(rows).toHaveCount(4);
  await expect(page.locator('.pub-log')).toContainText("Anna's Hummingbird");
  await expect(page.locator('.pub-log')).toContainText('House Sparrow');
  await expect(page.locator('.pub-log')).not.toContainText('American Robin');
  for (const ago of await rows.locator('.log-ago').allTextContents()) {
    expect(ago).toMatch(/^(just now|\d+m ago|\d+h ago)$/);
  }

  expect(apiPaths.length).toBeGreaterThan(0);
  for (const path of apiPaths) {
    expect(path).toMatch(/^\/api\/collage(\/|$)/);
  }
});

test('ships none of the admin chrome', async ({ page }) => {
  await page.goto('/public.html');
  await expect(page.locator('#collage')).toBeVisible();

  for (const selector of ['#slider', '#winPick', '#aboutLink', '#detail-modal', '#about-modal', '.seg-pill']) {
    await expect(page.locator(selector)).toHaveCount(0);
  }
});

test('the scroll cue brings the capture log into view', async ({ page }) => {
  await page.goto('/public.html');
  const log = page.locator('.pub-log');
  await expect(log).not.toBeInViewport();

  await page.locator('.scroll-cue').click();
  await expect(log).toBeInViewport();
});

test('shows the empty nest and hides the log when the api fails', async ({ page }) => {
  await page.route('**/api/collage**', (route) => route.fulfill({ status: 503, body: '' }));
  await page.goto('/public.html');

  await expect(page.locator('#collage .empty-nest')).toBeVisible();
  await expect(page.locator('#collage .empty')).toHaveText('no birds heard in this window.');
  await expect(page.locator('#collage .gtile')).toHaveCount(0);
  await expect(page.locator('.scroll-cue')).toHaveCount(0);
  await expect(page.locator('.pub-log')).toHaveCount(0);
});

test('labels capture ages and caps the log at eight rows', async ({ page }) => {
  const recent = [
    { sci: 'Calypte anna', com: 'Fresh', ago: 5 },
    { sci: 'Calypte anna', com: 'Minutes', ago: 125 },
    { sci: 'Calypte anna', com: 'Hours', ago: 7300 },
    ...Array.from({ length: 7 }, (_, i) => ({ sci: 'Passer domesticus', com: `Extra ${i}`, ago: 4000 })),
  ];
  await routeRecent(page, recent);
  await page.goto('/public.html');

  const rows = page.locator('.pub-log .log-row');
  await expect(rows).toHaveCount(8);
  await expect(rows.nth(0)).toContainText('Fresh');
  await expect(rows.nth(0).locator('.log-ago')).toHaveText('just now');
  await expect(rows.nth(1).locator('.log-ago')).toHaveText('2m ago');
  await expect(rows.nth(2).locator('.log-ago')).toHaveText('2h ago');
  await expect(page.locator('.pub-log')).not.toContainText('Extra 5');
});

test('refreshes the collage on its thirty second interval', async ({ page }) => {
  await page.clock.install();
  let recentCalls = 0;
  await page.route('**/api/collage/recent', (route) => {
    recentCalls += 1;
    const com = recentCalls === 1 ? 'First Poll' : 'Second Poll';
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ recent: [{ sci: 'Calypte anna', com, ago: 0 }] }),
    });
  });

  await page.goto('/public.html');
  await expect(page.locator('.pub-log')).toContainText('First Poll');

  await page.clock.runFor(30_000);
  await expect(page.locator('.pub-log')).toContainText('Second Poll');
  expect(recentCalls).toBe(2);
});
