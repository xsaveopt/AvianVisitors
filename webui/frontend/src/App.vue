<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import WindowPicker from '@/components/WindowPicker.vue';
import ViewSlider from '@/components/ViewSlider.vue';
import TheMenu from '@/components/TheMenu.vue';
import DetailModal from '@/components/DetailModal.vue';
import AboutModal from '@/components/AboutModal.vue';
import AdminScreen from '@/components/AdminScreen.vue';
import CollageView from '@/views/CollageView.vue';
import StatsView from '@/views/StatsView.vue';
import AtlasView from '@/views/AtlasView.vue';
import { useBirdsStore } from '@/stores/birds';
import { useAuthStore } from '@/stores/auth';
import { useHashRoute } from '@/composables/useHashRoute';

const birds = useBirdsStore();
const auth = useAuthStore();
const { route, go, clear } = useHashRoute();

const view = ref(0);
const menuOpen = ref(false);

const TITLES = ['Heard Recently', 'Heard Recently', 'Avian Visitors'];
const title = computed(() => TITLES[view.value]);
const viewsTransform = computed(() => `translateX(-${view.value * 100}%)`);

const selectedSci = computed(() => route.value.sci);

function openSpecies(sci: string): void {
  go('#sci=' + encodeURIComponent(sci));
}

watch(
  () => route.value.sci,
  (sci) => {
    if (sci) {
      view.value = 2;
    }
  },
);

watch(
  () => route.value.admin,
  (section) => {
    document.body.classList.toggle('admin-on', !!section);
    if (section) {
      menuOpen.value = false;
    }
  },
  { immediate: true },
);

watch(() => auth.authed, (v) => document.body.classList.toggle('authed', v), { immediate: true });
watch(() => auth.required, (v) => document.body.classList.toggle('auth-required', v), { immediate: true });

onMounted(() => {
  void birds.refresh();
  void auth.probe();
});
</script>

<template>
  <header class="top">
    <WindowPicker />
    <button class="menu-btn" id="menuBtn" @click="menuOpen = !menuOpen">menu</button>
  </header>

  <TheMenu :open="menuOpen" />

  <main class="stage">
    <header class="static-head">
      <button type="button" class="pre" id="aboutLink" @click="go('#about')">your birds</button>
      <h1 id="staticTitle">{{ title }}</h1>
    </header>
    <div class="views" id="views" :style="{ transform: viewsTransform }">
      <CollageView @open="openSpecies" />
      <StatsView @open="openSpecies" />
      <AtlasView @open="openSpecies" />
    </div>
  </main>

  <ViewSlider v-model="view" />

  <DetailModal :sci="selectedSci" @close="clear" />
  <AboutModal :open="route.about" @close="clear" />
  <AdminScreen :section="route.admin" @close="clear" />
</template>
