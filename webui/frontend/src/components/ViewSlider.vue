<script setup lang="ts">
const model = defineModel<number>({ required: true });

const labels = ['collage', 'stats', 'atlas'];
</script>

<template>
  <nav v-seg-pill class="slider" id="slider" aria-label="View">
    <i class="seg-pill" aria-hidden="true"></i>
    <button
      v-for="(label, i) in labels"
      :key="i"
      type="button"
      :data-i="i"
      :aria-current="model === i ? 'true' : 'false'"
      @click="model = i"
    >
      {{ label }}
    </button>
  </nav>
</template>
