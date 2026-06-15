<script setup lang="ts">
import { ALL_WINDOW, useBirdsStore } from '@/stores/birds';

const birds = useBirdsStore();

const options: Array<{ h: number; label: string }> = [
  { h: 1, label: '1H' },
  { h: 12, label: '12H' },
  { h: 24, label: '24H' },
  { h: 168, label: '7D' },
  { h: ALL_WINDOW, label: 'ALL' },
];
</script>

<template>
  <div v-seg-pill class="window-pick" id="winPick" role="tablist">
    <i class="seg-pill" aria-hidden="true"></i>
    <button
      v-for="o in options"
      :key="o.h"
      type="button"
      :data-h="o.h"
      :aria-current="birds.hours === o.h ? 'true' : 'false'"
      @click="birds.setWindow(o.h)"
    >
      {{ o.label }}
    </button>
  </div>
</template>
