<script setup lang="ts">
import { useBirdsStore } from '@/stores/birds';
import BirdCard from '@/components/BirdCard.vue';

const birds = useBirdsStore();
const emit = defineEmits<{ open: [sci: string] }>();
</script>

<template>
  <section class="view" id="v2" aria-label="Atlas">
    <div class="atlas-controls">
      <div v-seg-pill class="atlas-sort" id="atlasSort" role="tablist" aria-label="sort atlas">
        <i class="seg-pill" aria-hidden="true"></i>
        <button
          type="button"
          data-sort="count"
          :aria-current="birds.sort === 'count' ? 'true' : 'false'"
          aria-label="most heard"
          @click="birds.setSort('count')"
        >
          <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
            <path d="M2 12 V8" /><path d="M6 12 V5" /><path d="M10 12 V3" />
          </svg>
          <span class="tip">most heard</span>
        </button>
        <button
          type="button"
          data-sort="recent"
          :aria-current="birds.sort === 'recent' ? 'true' : 'false'"
          aria-label="most recent"
          @click="birds.setSort('recent')"
        >
          <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="7" cy="7" r="5.2" /><path d="M7 4 V7 L9.2 8.3" />
          </svg>
          <span class="tip">most recent</span>
        </button>
        <button
          type="button"
          data-sort="alpha"
          :aria-current="birds.sort === 'alpha' ? 'true' : 'false'"
          aria-label="alphabetical"
          @click="birds.setSort('alpha')"
        >
          <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round">
            <path d="M2.4 11.5 L4 4.5 L5.6 11.5" /><path d="M2.9 9.2 H5.1" />
            <path d="M8.2 11.5 V4.5 H10.4 a1.3 1.3 0 0 1 0 2.6 H8.2" /><path d="M8.2 7.1 H10.6 a1.5 1.5 0 0 1 0 3 H8.2" />
          </svg>
          <span class="tip">a → z</span>
        </button>
      </div>
    </div>
    <div class="atlas-grid" id="atlasGrid">
      <BirdCard
        v-for="s in birds.atlasSpecies"
        :key="s.sci"
        :species="s"
        @open="emit('open', $event)"
      />
    </div>
  </section>
</template>
