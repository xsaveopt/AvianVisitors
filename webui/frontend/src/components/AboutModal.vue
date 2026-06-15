<script setup lang="ts">
defineProps<{ open: boolean }>();
const emit = defineEmits<{ close: [] }>();
</script>

<template>
  <div id="about-modal" :aria-hidden="open ? 'false' : 'true'" role="dialog">
    <div class="modal-backdrop" @click="emit('close')"></div>
    <div class="about-card" role="document">
      <button type="button" class="modal-close" aria-label="close" @click="emit('close')">×</button>
      <p class="about-eyebrow">your birds</p>
      <h2 id="aboutTitle">The birds outside your window</h2>
      <p class="about-body">
        A tiny microphone identifies every passing bird with Cornell's
        <a href="https://birdnet.cornell.edu/" target="_blank" rel="noopener">BirdNET</a>. Each
        species shows up as an illustration in the collage, sized by how often it's been heard.
      </p>
      <button type="button" class="about-explore" @click="emit('close')">explore the birds →</button>
    </div>
  </div>
</template>
