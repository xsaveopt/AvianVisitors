<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { useBirdsStore } from '@/stores/birds';
import { pad } from '@/utils/format';

const birds = useBirdsStore();
const root = ref<HTMLElement | null>(null);
const tlWidth = ref(0);
const viewportWidth = ref(typeof window !== 'undefined' ? window.innerWidth : 800);

let observer: ResizeObserver | null = null;

function onResize(): void {
  viewportWidth.value = window.innerWidth || 800;
}

onMounted(() => {
  if (root.value) {
    tlWidth.value = root.value.clientWidth;
    observer = new ResizeObserver((entries) => {
      tlWidth.value = entries[0].contentRect.width;
    });
    observer.observe(root.value);
  }
  window.addEventListener('resize', onResize);
});

onBeforeUnmount(() => {
  observer?.disconnect();
  window.removeEventListener('resize', onResize);
});

function parseTs(s: string): number {
  return s ? Date.parse(s.replace(' ', 'T')) : NaN;
}

const model = computed(() => {
  const all = [...birds.recent];
  if (!all.length || tlWidth.value === 0) {
    return null;
  }
  const isMobile = viewportWidth.value <= 700;
  const containerW = Math.max(140, tlWidth.value - 34);
  const MIN_COL = isMobile ? 52 : 22;
  const cap = isMobile ? all.length : Math.max(3, Math.floor(containerW / MIN_COL));
  const trimmed = all.length > cap;
  let species = [...all];
  if (trimmed) {
    species.sort((a, b) => (b.n || 0) - (a.n || 0));
    species = species.slice(0, cap);
  }
  species.sort((a, b) => {
    const ta = parseTs(a.last_seen);
    const tb = parseTs(b.last_seen);
    if (isNaN(ta)) return 1;
    if (isNaN(tb)) return -1;
    return ta - tb;
  });

  const C = species.length;
  const maxN = species.reduce((m, s) => Math.max(m, s.n || 0), 1);
  const colW = isMobile ? MIN_COL : containerW / C;
  const plotW = isMobile ? Math.max(containerW, C * colW) : containerW;
  const sq = Math.max(6, Math.min(colW, isMobile ? 60 : 48));
  const LABEL_GAP = 6;
  const SPAN = 0.55;

  const ticks: number[] = [];
  if (maxN <= 8) {
    for (let v = 0; v <= maxN; v++) ticks.push(v);
  } else {
    const divs = 4;
    for (let di = 0; di <= divs; di++) ticks.push(Math.round((maxN * di) / divs));
    ticks[ticks.length - 1] = maxN;
  }
  const yaxis = ticks.map((v) => ({ v, bottom: ((v / maxN) * SPAN * 100).toFixed(1) }));

  const fmtTs = (ms: number): string => {
    if (isNaN(ms)) return '';
    const d = new Date(ms);
    if (birds.hours <= 36) return pad(d.getHours()) + ':' + pad(d.getMinutes());
    if (birds.hours <= 75 * 24) return d.getMonth() + 1 + '/' + d.getDate();
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  };

  const cols = species.map((s, i) => {
    const centerPct = ((i + 0.5) / C) * 100;
    const n = s.n || 0;
    const bottomPct = (n / maxN) * SPAN * 100;
    return {
      sci: s.sci,
      com: s.com || s.sci,
      left: centerPct.toFixed(3),
      colW: colW.toFixed(2),
      squareBottom: bottomPct.toFixed(1),
      sq: sq.toFixed(1),
      labelBottom: `calc(${bottomPct.toFixed(1)}% + ${sq + LABEL_GAP}px)`,
      xtick: fmtTs(parseTs(s.last_seen)),
    };
  });

  const gridlines = Array.from({ length: C }, (_, gi) => (((gi + 1) / C) * 100).toFixed(3));

  return {
    isMobile,
    plotW: Math.round(plotW),
    yaxis,
    cols,
    gridlines,
    note: trimmed ? `${C} most-heard of ${all.length}` : '',
  };
});
</script>

<template>
  <div class="stats-timeline" id="statsTimeline" ref="root">
    <div v-if="!model" class="stats-tl-empty">no detections in this window</div>
    <template v-else>
      <div class="stats-tl-yaxis">
        <span
          v-for="tick in model.yaxis"
          :key="tick.v"
          class="stats-tl-ytick"
          :style="{ bottom: tick.bottom + '%' }"
        >{{ tick.v }}</span>
      </div>
      <div class="stats-tl-plot" :style="model.isMobile ? { width: model.plotW + 'px' } : undefined">
        <i
          v-for="(g, i) in model.gridlines"
          :key="'g' + i"
          class="stats-tl-gridline"
          :style="{ left: g + '%' }"
        ></i>
        <div
          v-for="col in model.cols"
          :key="col.sci"
          class="stats-tl-col"
          :data-sci="col.sci"
          :style="{ left: col.left + '%', width: col.colW + 'px' }"
        >
          <div class="stats-tl-square" :style="{ bottom: col.squareBottom + '%', width: col.sq + 'px', height: col.sq + 'px' }"></div>
          <div class="stats-tl-label" :style="{ bottom: col.labelBottom }">
            <span class="com">{{ col.com }}</span><span class="sci">{{ col.sci }}</span>
          </div>
        </div>
        <span
          v-for="col in model.cols"
          :key="'x' + col.sci"
          class="stats-tl-xtick"
          :style="{ left: col.left + '%' }"
        >{{ col.xtick }}</span>
      </div>
      <div v-if="model.note" class="stats-tl-cap">{{ model.note }}</div>
    </template>
  </div>
</template>
