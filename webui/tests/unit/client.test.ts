import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  api,
  ApiError,
  cutoutUrl,
  fetchAudioObjectUrl,
  illustrationUrl,
  login,
  probeAuth,
  recordingFileUrl,
  recordingUrl,
} from '@/api/client';
import { setCredentials } from '@/api/credentials';

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
    blob: async () => ({ size: 3 }),
  } as unknown as Response;
}

function stubFetch(handler: (url: string, init: RequestInit) => unknown): void {
  vi.stubGlobal('fetch', (url: string, init: RequestInit = {}) => {
    calls.push({ url, init });
    const out = handler(url, init);
    return out instanceof Error ? Promise.reject(out) : Promise.resolve(out);
  });
}

function header(call: Call, name: string): string | undefined {
  return (call.init.headers as Record<string, string> | undefined)?.[name];
}

beforeEach(() => {
  calls = [];
  vi.stubGlobal('URL', { createObjectURL: () => 'blob:object-url' });
});

afterEach(() => {
  vi.unstubAllGlobals();
  setCredentials(null);
});

describe('url builders', () => {
  const cases: Array<[string, string, string]> = [
    ['recordingUrl', recordingUrl('Calypte anna'), '/api/recording?sci=Calypte%20anna'],
    ['recordingFileUrl', recordingFileUrl('a b/c.wav'), '/api/recording?file=a%20b%2Fc.wav'],
    [
      'cutoutUrl with a common name',
      cutoutUrl('Pica pica', 'Anna & Co', '7'),
      '/api/illustration?sci=Pica%20pica&com=Anna%20%26%20Co&v=7',
    ],
    ['cutoutUrl without one', cutoutUrl('Pica pica', '', '7'), '/api/illustration?sci=Pica%20pica&v=7'],
    ['illustrationUrl', illustrationUrl('Pica pica', '7'), '/api/illustration?sci=Pica%20pica&v=7'],
  ];

  for (const [name, actual, expected] of cases) {
    it(name, () => {
      expect(actual).toBe(expected);
    });
  }
});

describe('getJson', () => {
  it('returns the parsed body', async () => {
    stubFetch(() => respond(200, { totals: { detections: 4 } }));
    await expect(api.stats()).resolves.toEqual({ totals: { detections: 4 } });
  });

  it('throws ApiError carrying the status', async () => {
    stubFetch(() => respond(503));
    await expect(api.stats()).rejects.toMatchObject({
      name: 'ApiError',
      status: 503,
      message: '/stats -> 503',
    });
    await expect(api.stats()).rejects.toBeInstanceOf(ApiError);
  });

  it('sends same-origin credentials and no authorization by default', async () => {
    stubFetch(() => respond(200));
    await api.stats();
    expect(calls[0].init.credentials).toBe('same-origin');
    expect(header(calls[0], 'Authorization')).toBeUndefined();
  });

  it('attaches basic auth on the gated endpoints only', async () => {
    setCredentials('dXNlcjpwYXNz');
    stubFetch(() => respond(200, { items: [] }));
    await api.menu();
    await api.stats();
    expect(header(calls[0], 'Authorization')).toBe('Basic dXNlcjpwYXNz');
    expect(header(calls[1], 'Authorization')).toBeUndefined();
  });
});

describe('api paths', () => {
  const cases: Array<[string, () => Promise<unknown>, string]> = [
    ['stats', () => api.stats(), '/api/stats'],
    ['lifelist', () => api.lifelist(), '/api/lifelist'],
    ['recent', () => api.recent(24), '/api/recent?hours=24'],
    ['firstseen', () => api.firstseen(10), '/api/firstseen?limit=10'],
    ['timeseries', () => api.timeseries(7), '/api/timeseries?days=7'],
    ['species', () => api.species('Pica pica'), '/api/species?sci=Pica%20pica'],
    ['wiki', () => api.wiki('Pica pica'), '/api/wiki?sci=Pica%20pica'],
    ['menu', () => api.menu(), '/api/menu'],
    ['config', () => api.config(), '/api/config'],
    ['theme', () => api.theme(), '/api/theme'],
    ['status', () => api.status('diag'), '/api/status?action=diag'],
    ['logs', () => api.logs('php fpm', 50), '/api/status?action=logs&unit=php%20fpm&lines=50'],
  ];

  for (const [name, call, expected] of cases) {
    it(name, async () => {
      stubFetch(() => respond(200, { items: [], species: [] }));
      await call();
      expect(calls[0].url).toBe(expected);
    });
  }
});

describe('postJson', () => {
  it('posts the payload as json', async () => {
    stubFetch(() => respond(200, { ok: true }));
    await expect(api.saveConfig({ LATITUDE: 50 })).resolves.toEqual({ ok: true });
    expect(calls[0].init.method).toBe('POST');
    expect(header(calls[0], 'Content-Type')).toBe('application/json');
    expect(calls[0].init.body).toBe('{"LATITUDE":50}');
  });

  it('setTheme posts to the config endpoint', async () => {
    stubFetch(() => respond(200, {}));
    await api.setTheme('dark');
    expect(calls[0].url).toBe('/api/config');
    expect(calls[0].init.body).toBe('{"THEME":"dark"}');
  });

  it('restart encodes the unit', async () => {
    stubFetch(() => respond(200, {}));
    await api.restart('birdnet analysis');
    expect(calls[0].url).toBe('/api/status?action=restart&unit=birdnet%20analysis');
    expect(calls[0].init.body).toBe('{}');
  });

  it('does not check the status', async () => {
    stubFetch(() => respond(500, { error: 'nope' }));
    await expect(api.saveConfig({})).resolves.toEqual({ error: 'nope' });
  });
});

describe('fetchAudioObjectUrl', () => {
  it('turns the body into an object url', async () => {
    stubFetch(() => respond(200));
    await expect(fetchAudioObjectUrl('/api/recording?sci=x')).resolves.toBe('blob:object-url');
  });

  it('throws ApiError on a failure', async () => {
    stubFetch(() => respond(404));
    await expect(fetchAudioObjectUrl('/api/recording?sci=x')).rejects.toMatchObject({
      status: 404,
      message: '/api/recording?sci=x -> 404',
    });
  });
});

describe('probeAuth', () => {
  const cases: Array<[string, number | Error, string]> = [
    ['authed on 200', 200, 'authed'],
    ['required on 401', 401, 'required'],
    ['required on 403', 403, 'required'],
    ['offline when fetch rejects', new Error('down'), 'offline'],
  ];

  for (const [name, outcome, expected] of cases) {
    it(name, async () => {
      stubFetch(() => (outcome instanceof Error ? outcome : respond(outcome)));
      await expect(probeAuth()).resolves.toBe(expected);
    });
  }

  it('asks the menu endpoint without caching', async () => {
    stubFetch(() => respond(200));
    await probeAuth();
    expect(calls[0].url).toBe('/api/menu');
    expect(calls[0].init.cache).toBe('no-store');
  });
});

describe('login', () => {
  it('is true only on 200', async () => {
    stubFetch(() => respond(200));
    await expect(login('abc')).resolves.toBe(true);
    stubFetch(() => respond(401));
    await expect(login('abc')).resolves.toBe(false);
  });

  it('sends the credentials it was given rather than the stored ones', async () => {
    setCredentials('stored');
    stubFetch(() => respond(200));
    await login('supplied');
    expect(header(calls[0], 'Authorization')).toBe('Basic supplied');
    expect(calls[0].init.method).toBe('POST');
  });
});
