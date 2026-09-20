import { createPinia, setActivePinia } from 'pinia';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { FirstSeenSpecies, LifelistSpecies, RecentSpecies, Stats } from '@/api/types';

const stats = vi.fn<() => Promise<Stats>>();
const lifelist = vi.fn<() => Promise<{ species: LifelistSpecies[] }>>();
const recent = vi.fn<(hours: number) => Promise<{ species: RecentSpecies[] }>>();
const firstseen = vi.fn<(limit: number) => Promise<{ species: FirstSeenSpecies[] }>>();

vi.mock('@/api/client', () => ({
  api: {
    stats: () => stats(),
    lifelist: () => lifelist(),
    recent: (hours: number) => recent(hours),
    firstseen: (limit: number) => firstseen(limit),
  },
}));

const { ALL_WINDOW, useBirdsStore } = await import('@/stores/birds');

function life(sci: string, com: string, n: number, lastSeen: string): LifelistSpecies {
  return { sci, com, n, last_seen: lastSeen, first_seen: '2024-01-01', best_conf: 0.9 };
}

function seen(sci: string, n: number): RecentSpecies {
  return { sci, com: sci, n, best_conf: 0.9, last_seen: '2024-02-24' };
}

const LIFELIST = [
  life('Pica pica', 'Eurasian Magpie', 3, '2024-02-20'),
  life('Parus major', 'Great Tit', 9, '2024-02-22'),
  life('Corvus corax', 'Common Raven', 5, '2024-02-24'),
];

const STATS = { totals: { detections: 17, species: 3 } } as unknown as Stats;

beforeEach(() => {
  setActivePinia(createPinia());
  for (const fn of [stats, lifelist, recent, firstseen]) {
    fn.mockReset();
  }
  stats.mockResolvedValue(STATS);
  lifelist.mockResolvedValue({ species: LIFELIST });
  recent.mockResolvedValue({ species: [seen('Parus major', 4), seen('Pica pica', 1)] });
  firstseen.mockResolvedValue({ species: [] });
});

describe('defaults', () => {
  it('opens on a day of detections sorted by count', () => {
    const store = useBirdsStore();
    expect(store.hours).toBe(24);
    expect(store.sort).toBe('count');
    expect(store.loaded).toBe(false);
    expect(store.isAllWindow).toBe(false);
    expect(store.windowLabel).toBe('today');
  });

  it('the all-time window is above the sentinel', () => {
    const store = useBirdsStore();
    store.hours = ALL_WINDOW;
    expect(store.isAllWindow).toBe(true);
    expect(store.windowLabel).toBe('all time');
  });
});

describe('winBySci', () => {
  it('is empty before a refresh', () => {
    expect(useBirdsStore().winBySci).toEqual({});
  });

  it('maps each scientific name to its count in the window', async () => {
    const store = useBirdsStore();
    await store.refresh();
    expect(store.winBySci).toEqual({ 'Parus major': 4, 'Pica pica': 1 });
  });
});

describe('atlasSpecies', () => {
  async function loaded(): Promise<ReturnType<typeof useBirdsStore>> {
    const store = useBirdsStore();
    await store.refresh();
    return store;
  }

  it('drops species with no detection in the window', async () => {
    const store = await loaded();
    expect(store.atlasSpecies.map((s) => s.sci)).toEqual(['Parus major', 'Pica pica']);
  });

  it('keeps every species on the all-time window', async () => {
    const store = await loaded();
    store.hours = ALL_WINDOW;
    expect(store.atlasSpecies).toHaveLength(3);
  });

  const orders: Array<['count' | 'recent' | 'alpha', string[]]> = [
    ['count', ['Parus major', 'Corvus corax', 'Pica pica']],
    ['recent', ['Corvus corax', 'Parus major', 'Pica pica']],
    ['alpha', ['Corvus corax', 'Pica pica', 'Parus major']],
  ];

  for (const [sort, expected] of orders) {
    it(`sorts by ${sort}`, async () => {
      const store = await loaded();
      store.hours = ALL_WINDOW;
      store.setSort(sort);
      expect(store.atlasSpecies.map((s) => s.sci)).toEqual(expected);
    });
  }

  it('does not mutate the lifelist while sorting', async () => {
    const store = await loaded();
    store.hours = ALL_WINDOW;
    store.setSort('alpha');
    void store.atlasSpecies;
    expect(store.lifelist.map((s) => s.sci)).toEqual(LIFELIST.map((s) => s.sci));
  });
});

describe('refresh', () => {
  it('asks for the current window and marks the store loaded', async () => {
    const store = useBirdsStore();
    await store.refresh();
    expect(recent).toHaveBeenCalledWith(24);
    expect(firstseen).toHaveBeenCalledWith(10);
    expect(store.stats).toEqual(STATS);
    expect(store.loaded).toBe(true);
  });

  it('keeps the last good value when one endpoint fails', async () => {
    const store = useBirdsStore();
    await store.refresh();
    lifelist.mockRejectedValue(new Error('500'));
    stats.mockRejectedValue(new Error('500'));
    await store.refresh();
    expect(store.lifelist).toHaveLength(3);
    expect(store.stats).toEqual(STATS);
    expect(store.loaded).toBe(true);
  });

  it('is loaded even when everything fails', async () => {
    for (const fn of [stats, lifelist, recent, firstseen]) {
      fn.mockRejectedValue(new Error('offline'));
    }
    const store = useBirdsStore();
    await store.refresh();
    expect(store.loaded).toBe(true);
    expect(store.lifelist).toEqual([]);
  });
});

describe('setWindow', () => {
  it('moves the window and refetches only the recent list', async () => {
    const store = useBirdsStore();
    recent.mockResolvedValue({ species: [seen('Corvus corax', 2)] });
    await store.setWindow(1);
    expect(store.hours).toBe(1);
    expect(store.windowLabel).toBe('this hour');
    expect(recent).toHaveBeenCalledWith(1);
    expect(stats).not.toHaveBeenCalled();
    expect(store.winBySci).toEqual({ 'Corvus corax': 2 });
  });

  it('keeps the previous list when the refetch fails', async () => {
    const store = useBirdsStore();
    await store.refresh();
    recent.mockRejectedValue(new Error('500'));
    await store.setWindow(ALL_WINDOW);
    expect(store.hours).toBe(ALL_WINDOW);
    expect(store.recent).toHaveLength(2);
  });
});
