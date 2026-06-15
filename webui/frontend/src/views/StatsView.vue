<script setup lang="ts">
import { computed } from 'vue';
import { useBirdsStore } from '@/stores/birds';
import StatsTimeline from '@/components/StatsTimeline.vue';
import { fmtN, pad } from '@/utils/format';

const birds = useBirdsStore();
const emit = defineEmits<{ open: [sci: string] }>();

const byPeriod = computed(() => {
  const s = birds.stats;
  return [
    { yr: 'NOW', label: 'last hour', ct: fmtN(s?.last_hour.detections ?? 0) },
    { yr: 'TODAY', label: 'today', ct: fmtN(s?.today.detections ?? 0) },
    { yr: 'WEEK', label: 'last 7 days', ct: fmtN(s?.week.detections ?? 0) },
    { yr: 'ALL', label: 'all time', ct: fmtN(s?.totals.detections ?? 0) },
  ];
});

const topSpecies = computed(() =>
  [...birds.recent]
    .sort((a, b) => b.n - a.n)
    .slice(0, 5)
    .map((s, i) => ({ yr: pad(i + 1), label: s.com, ct: fmtN(s.n), sci: s.sci })),
);

const firstDetections = computed(() => {
  const now = Date.now();
  return birds.firstseen.slice(0, 5).map((s) => {
    const t = Date.parse((s.first_seen || '').replace(' ', 'T'));
    let label = '-';
    if (!isNaN(t)) {
      const daysAgo = Math.floor((now - t) / 86400000);
      label = daysAgo === 0 ? 'today' : daysAgo + 'd ago';
    }
    return { yr: label, label: s.com, ct: '', sci: s.sci };
  });
});
</script>

<template>
  <section class="view" id="v1" aria-label="Stats">
    <div class="stats-grid">
      <StatsTimeline />
      <aside class="stats-side">
        <div class="grp">
          <h3>By Period</h3>
          <small>detections, grouped by recency</small>
          <ol id="statsByPeriod">
            <li v-for="r in byPeriod" :key="r.yr">
              <span class="yr">{{ r.yr }}</span><span>{{ r.label }}</span><span class="ct">{{ r.ct }}</span>
            </li>
          </ol>
        </div>
        <div class="grp">
          <h3>Top Species</h3>
          <small id="statsTopSpecCap">most-heard, {{ birds.windowLabel }}</small>
          <ol id="statsTopSpec">
            <li v-if="!topSpecies.length"><span class="yr">-</span><span>no detections in window</span><span class="ct"></span></li>
            <li v-for="r in topSpecies" v-else :key="r.sci" :data-sci="r.sci" @click="emit('open', r.sci)">
              <span class="yr">{{ r.yr }}</span><span>{{ r.label }}</span><span class="ct">{{ r.ct }}</span>
            </li>
          </ol>
        </div>
        <div class="grp">
          <h3>First Detections</h3>
          <small>newest additions to the life list</small>
          <ol id="statsFirstSeen">
            <li v-if="!firstDetections.length"><span class="yr">-</span><span>no detections yet</span><span class="ct"></span></li>
            <li v-for="r in firstDetections" v-else :key="r.sci" :data-sci="r.sci" @click="emit('open', r.sci)">
              <span class="yr">{{ r.yr }}</span><span>{{ r.label }}</span><span class="ct">{{ r.ct }}</span>
            </li>
          </ol>
        </div>
      </aside>
    </div>
  </section>
</template>
