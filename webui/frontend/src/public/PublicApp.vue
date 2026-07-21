<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import CollageView from '@/views/CollageView.vue';
import type { CollageSpecies } from '@/collage/algorithm';
import { collageIllustrationUrl, fetchCollage, fetchCollageRecent, type RecentCapture } from './api';

const species = ref<CollageSpecies[]>([]);
const recent = ref<RecentCapture[]>([]);
const fetchedAt = ref(Date.now());
const now = ref(Date.now());
const nestSrc = 'nest.webp';
const log = ref<HTMLElement | null>(null);

let refresh: ReturnType<typeof setInterval> | undefined;
let tick: ReturnType<typeof setInterval> | undefined;

async function load() {
  const [s, r] = await Promise.all([fetchCollage(), fetchCollageRecent()]);
  species.value = s;
  recent.value = r;
  fetchedAt.value = Date.now();
  now.value = Date.now();
}

function relative(ago: number): string {
  const secs = ago + Math.floor((now.value - fetchedAt.value) / 1000);
  if (secs < 60) {
    return 'just now';
  }
  if (secs < 3600) {
    return `${Math.floor(secs / 60)}m ago`;
  }
  return `${Math.floor(secs / 3600)}h ago`;
}

const captures = computed(() => recent.value.slice(0, 8));

function toLog() {
  log.value?.scrollIntoView({ behavior: 'smooth' });
}

onMounted(() => {
  void load();
  refresh = setInterval(() => void load(), 30_000);
  tick = setInterval(() => (now.value = Date.now()), 15_000);
});

onUnmounted(() => {
  if (refresh) {
    clearInterval(refresh);
  }
  if (tick) {
    clearInterval(tick);
  }
});
</script>

<template>
  <div class="pub">
    <section class="pub-hero">
      <header class="static-head">
        <h1>Heard Recently</h1>
      </header>
      <div class="pub-collage">
        <CollageView
          :species="species"
          :illustration="collageIllustrationUrl"
          :nest-src="nestSrc"
          window-label="today"
        />
      </div>
      <button v-if="captures.length" type="button" class="scroll-cue" @click="toLog">
        <span>Recent captures</span>
        <span class="chev" aria-hidden="true">&#8595;</span>
      </button>
    </section>

    <section v-if="captures.length" ref="log" class="pub-log" aria-label="Recent captures">
      <h2>Recent captures</h2>
      <ol class="log-list">
        <li v-for="(c, i) in captures" :key="`${c.sci}-${i}`" class="log-row">
          <span class="log-name">{{ c.com }}</span>
          <span class="log-ago mono">{{ relative(c.ago) }}</span>
        </li>
      </ol>
    </section>
  </div>
</template>

<style>
html {
  height: auto;
  overflow-x: hidden;
}
body {
  height: auto;
  min-height: 100%;
  overflow: visible;
}
</style>

<style scoped>
.pub {
  min-height: 100dvh;
}
.pub-hero {
  height: 100dvh;
  display: flex;
  flex-direction: column;
}
.pub-collage {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
}
.scroll-cue {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin: 0 auto 22px;
  padding: 10px 18px;
  background: var(--pill);
  border: 0;
  border-radius: 999px;
  box-shadow: var(--raised);
  cursor: pointer;
  color: var(--ink-2);
  font:
    italic 400 clamp(13px, 1.4vw, 16px)/1 ui-serif,
    "Iowan Old Style",
    Georgia,
    serif;
  letter-spacing: 0.04em;
  transition:
    color 140ms ease,
    transform 140ms ease;
}
.scroll-cue:hover {
  color: var(--ink);
  transform: translateY(2px);
}
.scroll-cue .chev {
  animation: cue-bob 1.6s ease-in-out infinite;
}
@keyframes cue-bob {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(3px);
  }
}

.pub-log {
  max-width: 640px;
  margin: 0 auto;
  padding: 24px 24px 96px;
}
.pub-log h2 {
  margin: 0 0 8px;
  padding: 0;
  font:
    700 clamp(18px, 2.2vw, 26px)/1.1 ui-serif,
    "Iowan Old Style",
    Georgia,
    serif;
  letter-spacing: 0.06em;
  color: var(--ink);
  text-transform: uppercase;
}
.log-list {
  margin: 0;
  padding: 0;
  list-style: none;
}
.log-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 2px;
  border-top: 1px solid var(--hairline);
}
.log-name {
  color: var(--ink);
  font-size: clamp(15px, 2vw, 17px);
  line-height: 1.3;
}
.log-ago {
  flex: 0 0 auto;
  color: var(--ink-soft);
  font-size: 12px;
  white-space: nowrap;
}
@media (max-width: 700px) {
  .pub-log {
    padding: 20px 18px 88px;
  }
}
</style>
