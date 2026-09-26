import { afterEach, describe, expect, it, vi } from 'vitest';
import { collageIllustrationUrl, fetchCollage, fetchCollageRecent } from '@/public/api';

interface Call {
  url: string;
  init: RequestInit;
}

let calls: Call[] = [];

function respond(status: number, body: unknown = {}): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response;
}

function stubFetch(response: Response): void {
  vi.stubGlobal('fetch', (url: string, init: RequestInit = {}) => {
    calls.push({ url, init });
    return Promise.resolve(response);
  });
}

afterEach(() => {
  calls = [];
  vi.unstubAllGlobals();
});

describe('fetchCollage', () => {
  it('requests the relative collage path with same-origin credentials', async () => {
    const species = [{ sci: 'Pica pica', com: 'Eurasian Magpie', n: 3 }];
    stubFetch(respond(200, { species }));

    await expect(fetchCollage()).resolves.toEqual(species);
    expect(calls).toEqual([{ url: 'api/collage', init: { credentials: 'same-origin' } }]);
  });

  it('returns an empty list when the body has no species key', async () => {
    stubFetch(respond(200, {}));
    await expect(fetchCollage()).resolves.toEqual([]);
  });

  it('returns an empty list on a failed response instead of throwing', async () => {
    stubFetch(respond(503, { species: [{ sci: 'x', com: 'y', n: 1 }] }));
    await expect(fetchCollage()).resolves.toEqual([]);
  });
});

describe('fetchCollageRecent', () => {
  it('requests the relative recent path with same-origin credentials', async () => {
    const recent = [{ sci: 'Pica pica', com: 'Eurasian Magpie', ago: 42 }];
    stubFetch(respond(200, { recent }));

    await expect(fetchCollageRecent()).resolves.toEqual(recent);
    expect(calls).toEqual([{ url: 'api/collage/recent', init: { credentials: 'same-origin' } }]);
  });

  it('returns an empty list when the body has no recent key', async () => {
    stubFetch(respond(200, { species: [] }));
    await expect(fetchCollageRecent()).resolves.toEqual([]);
  });

  it('returns an empty list on a failed response instead of throwing', async () => {
    stubFetch(respond(404));
    await expect(fetchCollageRecent()).resolves.toEqual([]);
  });
});

describe('collageIllustrationUrl', () => {
  const cases: Array<[string, string]> = [
    ['Pica pica', 'api/collage/illustration?sci=Pica%20pica'],
    ["Anna's & co/x?y", "api/collage/illustration?sci=Anna's%20%26%20co%2Fx%3Fy"],
    ['', 'api/collage/illustration?sci='],
  ];

  for (const [sci, expected] of cases) {
    it(`encodes ${JSON.stringify(sci)}`, () => {
      expect(collageIllustrationUrl(sci)).toBe(expected);
    });
  }
});
