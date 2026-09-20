import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useHashRoute } from '@/composables/useHashRoute';

const listeners: Array<[string, () => void]> = [];
const removed: Array<[string, () => void]> = [];

function setHash(hash: string): void {
  (globalThis as unknown as { location: { hash: string } }).location.hash = hash;
}

beforeEach(() => {
  listeners.length = 0;
  removed.length = 0;
  vi.stubGlobal('location', { hash: '' });
  vi.stubGlobal('window', {
    addEventListener: (name: string, fn: () => void) => listeners.push([name, fn]),
    removeEventListener: (name: string, fn: () => void) => removed.push([name, fn]),
  });
  vi.spyOn(console, 'warn').mockImplementation(() => {});
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('parsing the hash', () => {
  const cases: Array<[string, { sci: string | null; about: boolean; admin: string | null }]> = [
    ['', { sci: null, about: false, admin: null }],
    ['#', { sci: null, about: false, admin: null }],
    ['#about', { sci: null, about: true, admin: null }],
    ['#sci=Pica pica', { sci: 'Pica pica', about: false, admin: null }],
    ['#sci=Pica%20pica', { sci: 'Pica pica', about: false, admin: null }],
    ['#sci=', { sci: null, about: false, admin: null }],
    ['#admin=config', { sci: null, about: false, admin: 'config' }],
    ['#admin=logs&unit=caddy', { sci: null, about: false, admin: 'logs' }],
    ['#admin=Config', { sci: null, about: false, admin: null }],
    ['#aboutish', { sci: null, about: false, admin: null }],
  ];

  for (const [hash, expected] of cases) {
    it(`reads ${hash || 'an empty hash'}`, () => {
      setHash(hash);
      expect(useHashRoute().route.value).toEqual(expected);
    });
  }

  it('rejects a malformed escape rather than guessing', () => {
    setHash('#sci=100%');
    expect(() => useHashRoute()).toThrow(URIError);
  });
});

describe('lifecycle', () => {
  it('registers nothing outside a component', () => {
    useHashRoute();
    expect(listeners).toEqual([]);
    expect(removed).toEqual([]);
  });
});

describe('go', () => {
  it('writes the hash when it differs', () => {
    setHash('#about');
    const { route, go } = useHashRoute();
    go('#sci=Pica%20pica');
    expect(location.hash).toBe('#sci=Pica%20pica');
    expect(route.value.about).toBe(true);
  });

  it('reparses in place when the hash is already right', () => {
    setHash('#about');
    const { route, go } = useHashRoute();
    setHash('#sci=Pica%20pica');
    go('#sci=Pica%20pica');
    expect(route.value).toEqual({ sci: 'Pica pica', about: false, admin: null });
  });
});

describe('clear', () => {
  it('empties a set hash', () => {
    setHash('#about');
    const { clear } = useHashRoute();
    clear();
    expect(location.hash).toBe('');
  });

  it('reparses when there is nothing to clear', () => {
    setHash('#admin=config');
    const { route, clear } = useHashRoute();
    expect(route.value.admin).toBe('config');
    setHash('');
    clear();
    expect(route.value).toEqual({ sci: null, about: false, admin: null });
  });
});
