<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue';
import { illustrationPoseUrl } from '@/api/client';
import { useBirdsStore } from '@/stores/birds';
import { layoutCollage, type Tile } from '@/collage/algorithm';
import { fmtN } from '@/utils/format';

const IMG_VERSION = 'r10';

const birds = useBirdsStore();
const emit = defineEmits<{ open: [sci: string] }>();

const root = ref<HTMLElement | null>(null);
const placed = ref<Tile[]>([]);
const delays = ref<Record<string, number>>({});
const entering = ref(false);
const hoveredSci = ref<string | null>(null);
const tip = ref<{ com: string; n: number } | null>(null);

const hitSets = new WeakMap<Tile, Set<string>>();
let observer: ResizeObserver | null = null;
let resizeTimer: number | undefined;
let enterTimer: number | undefined;

function imgFor(t: Tile): string {
  return illustrationPoseUrl(t.data.sci, IMG_VERSION, t.pose);
}

function relayout(): void {
  const el = root.value;
  if (!el) {
    return;
  }
  const W = el.clientWidth;
  const H = el.clientHeight;
  if (!W || !H || !birds.recent.length) {
    placed.value = [];
    return;
  }
  placed.value = layoutCollage(birds.recent, W, H);
  playEntrance();
}

function playEntrance(): void {
  const cx = (root.value?.clientWidth ?? 0) / 2;
  const cy = (root.value?.clientHeight ?? 0) / 2;
  let maxD = 1;
  const visible = placed.value.filter((t) => t.x > -1000);
  const dist: Record<string, number> = {};
  for (const t of visible) {
    const d = Math.hypot(t.x + t.fullW / 2 - cx, t.y + t.fullH / 2 - cy);
    dist[t.data.sci] = d;
    if (d > maxD) maxD = d;
  }
  const SPREAD = 520;
  const next: Record<string, number> = {};
  for (const t of visible) {
    next[t.data.sci] = Math.round((dist[t.data.sci] / maxD) * SPREAD);
  }
  delays.value = next;
  entering.value = true;
  clearTimeout(enterTimer);
  enterTimer = window.setTimeout(() => {
    entering.value = false;
  }, SPREAD + 520);
}

function hitTest(px: number, py: number): Tile | null {
  for (let i = placed.value.length - 1; i >= 0; i--) {
    const t = placed.value[i];
    if (t.x < -1000) continue;
    if (px < t.x || py < t.y || px > t.x + t.fullW || py > t.y + t.fullH) continue;
    const mx = ((px - t.x) / t.fullW * t.mask.w) | 0;
    const my = ((py - t.y) / t.fullH * t.mask.h) | 0;
    let set = hitSets.get(t);
    if (!set) {
      set = new Set(t.mask.cells.map((c) => c[0] + '|' + c[1]));
      hitSets.set(t, set);
    }
    if (set.has(mx + '|' + my)) return t;
  }
  return null;
}

function onMove(ev: MouseEvent): void {
  const el = root.value;
  if (!el) return;
  const box = el.getBoundingClientRect();
  const hit = hitTest(ev.clientX - box.left, ev.clientY - box.top);
  hoveredSci.value = hit ? hit.data.sci : null;
  tip.value = hit ? { com: hit.data.com || hit.data.sci, n: Number(hit.data.n) || 0 } : null;
  el.style.cursor = hit ? 'pointer' : 'default';
}

function onLeave(): void {
  hoveredSci.value = null;
  tip.value = null;
}

function onClick(ev: MouseEvent): void {
  const el = root.value;
  if (!el) return;
  const box = el.getBoundingClientRect();
  const hit = hitTest(ev.clientX - box.left, ev.clientY - box.top);
  if (hit) {
    emit('open', hit.data.sci);
  }
}

function scheduleRelayout(): void {
  clearTimeout(resizeTimer);
  resizeTimer = window.setTimeout(relayout, 120);
}

onMounted(() => {
  relayout();
  if (root.value) {
    observer = new ResizeObserver(() => scheduleRelayout());
    observer.observe(root.value);
  }
  birds.$subscribe(() => scheduleRelayout());
});

onBeforeUnmount(() => {
  observer?.disconnect();
  clearTimeout(resizeTimer);
  clearTimeout(enterTimer);
});
</script>

<template>
  <section class="view" id="v0" aria-label="Bird collage">
    <div
      class="gcollage"
      id="collage"
      ref="root"
      @mousemove="onMove"
      @mouseleave="onLeave"
      @click="onClick"
    >
      <p v-if="!placed.length" class="empty">no birds heard in this window.</p>
      <button
        v-for="t in placed"
        :key="t.data.sci"
        type="button"
        class="gtile"
        :class="{ 'is-hover': hoveredSci === t.data.sci, entering: entering && t.x > -1000 }"
        :data-sci="t.data.sci"
        :aria-label="t.data.com"
        :style="{
          left: t.x + 'px',
          top: t.y + 'px',
          width: t.fullW + 'px',
          height: t.fullH + 'px',
          animationDelay: entering ? (delays[t.data.sci] ?? 0) + 'ms' : '',
        }"
        tabindex="-1"
      >
        <img loading="lazy" decoding="async" :src="imgFor(t)" :alt="t.data.com" />
      </button>
      <div class="collage-tip" id="collageTip" :aria-hidden="tip ? 'false' : 'true'">
        <template v-if="tip">
          <span class="ct-name">{{ tip.com }}</span>
          <span class="ct-w"> - </span>
          <span class="ct-n">{{ fmtN(tip.n) }}</span>
          <span class="ct-w"> {{ tip.n === 1 ? 'call' : 'calls' }} {{ birds.windowLabel }}</span>
        </template>
      </div>
    </div>
  </section>
</template>
