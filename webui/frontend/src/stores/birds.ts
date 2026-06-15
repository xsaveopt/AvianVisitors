import { computed, ref } from 'vue';
import { defineStore } from 'pinia';
import { api } from '@/api/client';
import { windowLabel as labelFor } from '@/utils/format';
import type { FirstSeenSpecies, LifelistSpecies, RecentSpecies, Stats } from '@/api/types';

export type AtlasSort = 'count' | 'recent' | 'alpha';
export const ALL_WINDOW = 1_000_000;

export const useBirdsStore = defineStore('birds', () => {
  const hours = ref(24);
  const sort = ref<AtlasSort>('count');
  const stats = ref<Stats | null>(null);
  const lifelist = ref<LifelistSpecies[]>([]);
  const recent = ref<RecentSpecies[]>([]);
  const firstseen = ref<FirstSeenSpecies[]>([]);
  const loaded = ref(false);

  const winBySci = computed<Record<string, number>>(() => {
    const map: Record<string, number> = {};
    for (const s of recent.value) {
      map[s.sci] = s.n;
    }
    return map;
  });

  const isAllWindow = computed(() => hours.value >= ALL_WINDOW);
  const windowLabel = computed(() => labelFor(hours.value));

  const atlasSpecies = computed<LifelistSpecies[]>(() => {
    const list = isAllWindow.value
      ? lifelist.value
      : lifelist.value.filter((s) => (winBySci.value[s.sci] ?? 0) > 0);
    const sorted = [...list];
    if (sort.value === 'alpha') {
      sorted.sort((a, b) => a.com.localeCompare(b.com));
    } else if (sort.value === 'recent') {
      sorted.sort((a, b) => b.last_seen.localeCompare(a.last_seen));
    } else {
      sorted.sort((a, b) => b.n - a.n);
    }
    return sorted;
  });

  async function refresh(): Promise<void> {
    const [statsRes, lifeRes, recentRes, firstRes] = await Promise.all([
      api.stats().catch(() => null),
      api.lifelist().catch(() => null),
      api.recent(hours.value).catch(() => null),
      api.firstseen(10).catch(() => null),
    ]);
    if (statsRes) stats.value = statsRes;
    if (lifeRes) lifelist.value = lifeRes.species;
    if (recentRes) recent.value = recentRes.species;
    if (firstRes) firstseen.value = firstRes.species;
    loaded.value = true;
  }

  async function setWindow(value: number): Promise<void> {
    hours.value = value;
    const recentRes = await api.recent(value).catch(() => null);
    if (recentRes) recent.value = recentRes.species;
  }

  function setSort(value: AtlasSort): void {
    sort.value = value;
  }

  return {
    hours,
    sort,
    stats,
    lifelist,
    recent,
    firstseen,
    loaded,
    winBySci,
    isAllWindow,
    windowLabel,
    atlasSpecies,
    refresh,
    setWindow,
    setSort,
  };
});
