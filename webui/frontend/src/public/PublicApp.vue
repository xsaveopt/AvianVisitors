<script setup lang="ts">
import { onMounted, ref } from 'vue';
import CollageView from '@/views/CollageView.vue';
import type { CollageSpecies } from '@/collage/algorithm';
import { collageIllustrationUrl, fetchCollage } from './api';

const species = ref<CollageSpecies[]>([]);
const nestSrc = 'nest.webp';

onMounted(async () => {
  species.value = await fetchCollage();
});
</script>

<template>
  <main class="stage">
    <header class="static-head">
      <h1>Heard Recently</h1>
    </header>
    <div class="views">
      <CollageView
        :species="species"
        :illustration="collageIllustrationUrl"
        :nest-src="nestSrc"
        window-label="today"
      />
    </div>
  </main>
</template>
