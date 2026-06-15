<script setup lang="ts">
import { computed, ref } from 'vue';
import { cutoutUrl, recordingUrl } from '@/api/client';
import { useAuthStore } from '@/stores/auth';
import { useBirdsStore } from '@/stores/birds';
import { usePlayer } from '@/composables/usePlayer';
import type { LifelistSpecies } from '@/api/types';

const props = defineProps<{ species: LifelistSpecies }>();
const emit = defineEmits<{ open: [sci: string] }>();

const IMG_VERSION = 'r10';
const auth = useAuthStore();
const birds = useBirdsStore();
const player = usePlayer();

const locked = ref(false);

const windowCount = computed(() => birds.winBySci[props.species.sci] ?? 0);
const cutout = computed(() => cutoutUrl(props.species.sci, props.species.com, IMG_VERSION));
const isPlaying = computed(() => player.activeKey.value === props.species.sci && player.state.value === 'playing');

function wikiUrl(sci: string): string {
  return `https://en.wikipedia.org/wiki/${encodeURIComponent(sci.replace(/ /g, '_'))}`;
}
function ebirdUrl(sci: string): string {
  return `https://ebird.org/species/search?q=${encodeURIComponent(sci)}`;
}

function onPlay(): void {
  if (!auth.authed) {
    locked.value = true;
    setTimeout(() => (locked.value = false), 1500);
    return;
  }
  void player.toggle(props.species.sci, recordingUrl(props.species.sci));
}
</script>

<template>
  <article class="bird-card" :data-sci="species.sci" @click="emit('open', species.sci)">
    <div class="stat">
      <div v-if="!birds.isAllWindow">
        <span class="n">{{ windowCount }}</span><span class="lbl-inline">window</span>
      </div>
      <div><span class="n">{{ species.n }}</span><span class="lbl-inline">all time</span></div>
    </div>
    <div class="img-wrap">
      <img loading="lazy" decoding="async" :src="cutout" :alt="species.com" />
    </div>
    <h3>{{ species.com }}</h3>
    <div class="sci">{{ species.sci }}</div>
    <div class="actions" @click.stop>
      <button
        type="button"
        class="chip play"
        :data-state="isPlaying ? 'playing' : 'idle'"
        aria-label="play recording"
        @click="onPlay"
      >
        <svg viewBox="0 0 12 12" fill="currentColor"><path d="M3 2 L10 6 L3 10 Z" /></svg>
        <span>{{ locked ? 'locked' : isPlaying ? 'stop' : 'play' }}</span>
      </button>
      <a class="chip ext" :href="wikiUrl(species.sci)" target="_blank" rel="noopener">wiki</a>
      <a class="chip ext" :href="ebirdUrl(species.sci)" target="_blank" rel="noopener">ebird</a>
    </div>
  </article>
</template>
