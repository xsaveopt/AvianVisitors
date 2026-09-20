import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const getTheme = vi.fn<() => Promise<{ theme: string }>>();
const setThemeCall = vi.fn<(value: string) => Promise<unknown>>();

vi.mock('@/api/client', () => ({
  api: {
    theme: () => getTheme(),
    setTheme: (value: string) => setThemeCall(value),
  },
}));

interface Root {
  attrs: Record<string, string>;
}

let root: Root;
let store: Map<string, string>;
let storageThrows: 'none' | 'read' | 'write';

function stubEnvironment(initial?: string): void {
  root = { attrs: {} };
  store = new Map();
  if (initial !== undefined) {
    store.set('bird:theme', initial);
  }
  vi.stubGlobal('document', {
    createElement: () => ({ content: {}, innerHTML: '' }),
    createTextNode: (text: string) => ({ text }),
    createComment: (text: string) => ({ text }),
    querySelector: () => null,
    documentElement: {
      setAttribute: (name: string, value: string) => {
        root.attrs[name] = value;
      },
      removeAttribute: (name: string) => {
        delete root.attrs[name];
      },
      getAttribute: (name: string) => root.attrs[name] ?? null,
    },
  });
  vi.stubGlobal('localStorage', {
    getItem: (key: string) => {
      if (storageThrows === 'read') {
        throw new Error('blocked');
      }
      return store.get(key) ?? null;
    },
    setItem: (key: string, value: string) => {
      if (storageThrows === 'write') {
        throw new Error('blocked');
      }
      store.set(key, value);
    },
  });
}

async function load(initial?: string): Promise<ReturnType<typeof import('@/composables/useTheme').useTheme>> {
  stubEnvironment(initial);
  vi.resetModules();
  const { useTheme } = await import('@/composables/useTheme');
  return useTheme();
}

beforeEach(() => {
  storageThrows = 'none';
  getTheme.mockReset();
  setThemeCall.mockReset();
  setThemeCall.mockResolvedValue({});
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('initial read', () => {
  const cases: Array<[string, string | undefined, string, boolean]> = [
    ['nothing cached', undefined, 'light', false],
    ['a cached dark theme', 'dark', 'dark', true],
    ['a cached light theme', 'light', 'light', false],
    ['an unrecognised value', 'sepia', 'light', false],
  ];

  for (const [name, cached, expected, marked] of cases) {
    it(`starts from ${name}`, async () => {
      const theme = await load(cached);
      expect(theme.theme.value).toBe(expected);
      expect(root.attrs['data-theme']).toBe(marked ? 'dark' : undefined);
    });
  }

  it('falls back to light when storage is unreadable', async () => {
    stubEnvironment('dark');
    storageThrows = 'read';
    vi.resetModules();
    const { useTheme } = await import('@/composables/useTheme');
    expect(useTheme().theme.value).toBe('light');
  });
});

describe('set', () => {
  it('applies, caches and pushes to the server', async () => {
    const theme = await load();
    await theme.set('dark');
    expect(theme.theme.value).toBe('dark');
    expect(root.attrs['data-theme']).toBe('dark');
    expect(store.get('bird:theme')).toBe('dark');
    expect(setThemeCall).toHaveBeenCalledWith('dark');
  });

  it('removes the attribute going back to light', async () => {
    const theme = await load('dark');
    await theme.set('light');
    expect(root.attrs['data-theme']).toBeUndefined();
    expect(store.get('bird:theme')).toBe('light');
  });

  it('keeps the local change when the server call fails', async () => {
    const theme = await load();
    setThemeCall.mockRejectedValue(new Error('403'));
    await expect(theme.set('dark')).resolves.toBeUndefined();
    expect(theme.theme.value).toBe('dark');
    expect(root.attrs['data-theme']).toBe('dark');
  });

  it('applies even when the cache cannot be written', async () => {
    const theme = await load();
    storageThrows = 'write';
    await theme.set('dark');
    expect(theme.theme.value).toBe('dark');
    expect(root.attrs['data-theme']).toBe('dark');
  });
});

describe('sync', () => {
  const cases: Array<[string, string, boolean]> = [
    ['dark', 'dark', true],
    ['light', 'light', false],
    ['anything else', 'sepia', false],
  ];

  for (const [name, served, marked] of cases) {
    it(`adopts ${name} from the server`, async () => {
      const theme = await load('dark');
      getTheme.mockResolvedValue({ theme: served });
      await theme.sync();
      expect(theme.theme.value).toBe(marked ? 'dark' : 'light');
      expect(root.attrs['data-theme']).toBe(marked ? 'dark' : undefined);
      expect(store.get('bird:theme')).toBe(marked ? 'dark' : 'light');
    });
  }

  it('leaves the local theme alone when the server is unreachable', async () => {
    const theme = await load('dark');
    getTheme.mockRejectedValue(new Error('offline'));
    await expect(theme.sync()).resolves.toBeUndefined();
    expect(theme.theme.value).toBe('dark');
    expect(root.attrs['data-theme']).toBe('dark');
  });

  it('does not write back to the server', async () => {
    const theme = await load();
    getTheme.mockResolvedValue({ theme: 'dark' });
    await theme.sync();
    expect(setThemeCall).not.toHaveBeenCalled();
  });
});
