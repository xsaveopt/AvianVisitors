<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';
import { api, fetchAudioObjectUrl, illustrationPoseUrl, recordingFileUrl } from '@/api/client';
import { useAuthStore } from '@/stores/auth';
import { useBirdsStore } from '@/stores/birds';
import { audioClaim, audioRelease } from '@/audio/claim';
import { cachedBuffer, decodeRecording, getSpecCtx, paintSpectrogram } from '@/audio/spectrogram';
import { ebirdUrl, fmtDateLine, fmtN, fmtRecTime, rarityLabel, wikiUrl } from '@/utils/format';
import type { SpeciesDetail, WikiSummary } from '@/api/types';

const IMG_VERSION = 'r11';

const props = defineProps<{ sci: string | null }>();
const emit = defineEmits<{ close: [] }>();

const auth = useAuthStore();
const birds = useBirdsStore();

const detail = ref<SpeciesDetail | null>(null);
const wiki = ref<WikiSummary | null>(null);
const loading = ref(false);
const pose = ref(2);

const recList = ref<HTMLElement | null>(null);
const expanded = reactive(new Set<string>());
const activeFile = ref<string | null>(null);
const isPaused = ref(false);

let modalAudio: HTMLAudioElement | null = null;
let cursorRaf: number | null = null;

function rowEl(file: string): HTMLElement | null {
  return recList.value?.querySelector<HTMLElement>(`.rec-row[data-file="${CSS.escape(file)}"]`) ?? null;
}

function ensureSpectro(file: string): void {
  const row = rowEl(file);
  if (!row) {
    return;
  }
  const strip = row.querySelector<HTMLElement>('.rec-spectro');
  if (!strip) {
    return;
  }
  const loadingEl = strip.querySelector<HTMLElement>('.rec-spectro-loading');
  let canvas = strip.querySelector('canvas');
  if (canvas && canvas.classList.contains('ready')) {
    if (loadingEl) {
      loadingEl.style.display = 'none';
    }
    return;
  }
  if (!canvas) {
    canvas = document.createElement('canvas');
    const played = strip.querySelector('.rec-spectro-played');
    strip.insertBefore(canvas, played);
  }
  if (loadingEl) {
    loadingEl.style.display = '';
    loadingEl.textContent = 'rendering spectrogram...';
  }
  const done = (): void => {
    if (loadingEl) {
      loadingEl.style.display = 'none';
    }
  };
  const fail = (reason: string): void => {
    if (loadingEl) {
      loadingEl.style.display = '';
      loadingEl.textContent = reason;
    }
  };
  const cached = cachedBuffer(file);
  if (cached) {
    paintSpectrogram(canvas, cached);
    done();
    return;
  }
  if (!auth.authed) {
    fail('log in to view');
    return;
  }
  if (!getSpecCtx()) {
    fail('WebAudio not available');
    return;
  }
  decodeRecording(file)
    .then((audioBuffer) => {
      const c = strip.querySelector('canvas');
      if (c) {
        paintSpectrogram(c, audioBuffer);
      }
      done();
    })
    .catch((e: unknown) => {
      fail('spectrogram failed: ' + (e instanceof Error ? e.message : ''));
    });
}

function startCursorLoop(): void {
  if (cursorRaf) {
    return;
  }
  const tick = (): void => {
    if (!modalAudio || !activeFile.value) {
      cursorRaf = null;
      return;
    }
    const strip = rowEl(activeFile.value)?.querySelector<HTMLElement>('.rec-spectro');
    if (strip && modalAudio.duration) {
      const played = strip.querySelector<HTMLElement>('.rec-spectro-played');
      const cursor = strip.querySelector<HTMLElement>('.rec-spectro-cursor');
      const pct = (modalAudio.currentTime / modalAudio.duration) * 100;
      if (played) {
        played.style.width = pct.toFixed(3) + '%';
      }
      if (cursor) {
        cursor.style.left = pct.toFixed(3) + '%';
      }
    }
    cursorRaf = requestAnimationFrame(tick);
  };
  cursorRaf = requestAnimationFrame(tick);
}

function stopCursorLoop(): void {
  if (cursorRaf) {
    cancelAnimationFrame(cursorRaf);
    cursorRaf = null;
  }
}

function resetStrip(file: string): void {
  const strip = rowEl(file)?.querySelector<HTMLElement>('.rec-spectro');
  if (!strip) {
    return;
  }
  strip.classList.remove('armed');
  const played = strip.querySelector<HTMLElement>('.rec-spectro-played');
  const cur = strip.querySelector<HTMLElement>('.rec-spectro-cursor');
  if (played) {
    played.style.width = '0%';
  }
  if (cur) {
    cur.style.left = '0%';
  }
}

function pauseModalAudio(): void {
  stopCursorLoop();
  if (modalAudio) {
    try {
      modalAudio.pause();
    } catch {
      modalAudio = null;
    }
  }
  isPaused.value = true;
}

function stopModalAudio(): void {
  audioRelease(stopModalAudio);
  stopCursorLoop();
  if (modalAudio) {
    try {
      modalAudio.pause();
    } catch {
      modalAudio = null;
    }
    modalAudio = null;
  }
  if (activeFile.value) {
    resetStrip(activeFile.value);
    activeFile.value = null;
  }
  isPaused.value = false;
}

function playFile(file: string): void {
  if (!auth.authed) {
    return;
  }
  if (activeFile.value === file && modalAudio) {
    if (modalAudio.paused) {
      isPaused.value = false;
      audioClaim(stopModalAudio);
      void modalAudio.play().catch(() => {});
    } else {
      pauseModalAudio();
    }
    return;
  }

  stopModalAudio();
  audioClaim(stopModalAudio);
  activeFile.value = file;
  isPaused.value = false;
  expanded.add(file);
  void ensureStripThen(file);
}

async function ensureStripThen(file: string): Promise<void> {
  await Promise.resolve();
  ensureSpectro(file);
  const strip = rowEl(file)?.querySelector<HTMLElement>('.rec-spectro');
  try {
    const url = await fetchAudioObjectUrl(recordingFileUrl(file));
    if (activeFile.value !== file) {
      URL.revokeObjectURL(url);
      return;
    }
    const audio = new Audio(url);
    modalAudio = audio;
    audio.addEventListener('loadedmetadata', () => strip?.classList.add('armed'));
    audio.addEventListener('playing', startCursorLoop);
    audio.addEventListener('pause', stopCursorLoop);
    audio.addEventListener('ended', () => {
      stopCursorLoop();
      resetStrip(file);
      if (modalAudio) {
        modalAudio.currentTime = 0;
      }
      isPaused.value = true;
    });
    audio.addEventListener('error', () => stopModalAudio());
    await audio.play().catch(() => stopModalAudio());
  } catch {
    stopModalAudio();
  }
}

function toggleExpand(file: string): void {
  if (expanded.has(file)) {
    if (activeFile.value === file) {
      stopModalAudio();
    }
    expanded.delete(file);
  } else {
    expanded.add(file);
    ensureSpectro(file);
  }
}

let dragFile: string | null = null;

function seekFrom(file: string, clientX: number): void {
  if (!modalAudio || !modalAudio.duration || activeFile.value !== file) {
    return;
  }
  const strip = rowEl(file)?.querySelector<HTMLElement>('.rec-spectro');
  if (!strip) {
    return;
  }
  const rect = strip.getBoundingClientRect();
  const pct = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
  modalAudio.currentTime = pct * modalAudio.duration;
  const pctStr = (pct * 100).toFixed(2) + '%';
  const played = strip.querySelector<HTMLElement>('.rec-spectro-played');
  const cur = strip.querySelector<HTMLElement>('.rec-spectro-cursor');
  if (played) {
    played.style.width = pctStr;
  }
  if (cur) {
    cur.style.left = pctStr;
  }
}

function onScrubDown(file: string, clientX: number): void {
  if (!expanded.has(file)) {
    return;
  }
  dragFile = file;
  seekFrom(file, clientX);
}

function onMouseMove(ev: MouseEvent): void {
  if (dragFile) {
    seekFrom(dragFile, ev.clientX);
  }
}

function onTouchMove(ev: TouchEvent): void {
  if (dragFile) {
    seekFrom(dragFile, ev.touches[0].clientX);
  }
}

function onPointerUp(): void {
  dragFile = null;
}

onMounted(() => {
  document.addEventListener('mousemove', onMouseMove);
  document.addEventListener('mouseup', onPointerUp);
  document.addEventListener('touchmove', onTouchMove);
  document.addEventListener('touchend', onPointerUp);
});

onBeforeUnmount(() => {
  stopModalAudio();
  document.removeEventListener('mousemove', onMouseMove);
  document.removeEventListener('mouseup', onPointerUp);
  document.removeEventListener('touchmove', onTouchMove);
  document.removeEventListener('touchend', onPointerUp);
});

const genus = computed(() => (props.sci ? props.sci.split(' ')[0] : '-'));
const imgSrc = computed(() => (props.sci ? illustrationPoseUrl(props.sci, IMG_VERSION, pose.value) : ''));
const summary = computed(() => detail.value?.summary ?? null);
const allTime = computed(() => fmtN(summary.value ? Number(summary.value.total) : 0));
const windowCount = computed(() => (props.sci ? (birds.winBySci[props.sci] ?? 0) : 0));
const firstSeen = computed(() => {
  const fs = summary.value?.first_seen;
  if (!fs) {
    return '-';
  }
  const [d, t] = fs.split(' ');
  return fmtRecTime(d, t);
});
const rarity = computed(() => rarityLabel(summary.value ? Number(summary.value.total) : 0, summary.value?.first_seen));

watch(
  () => props.sci,
  async (sci) => {
    stopModalAudio();
    expanded.clear();
    detail.value = null;
    wiki.value = null;
    pose.value = 2;
    if (!sci) {
      return;
    }
    loading.value = true;
    const [d, w] = await Promise.all([
      api.species(sci).catch(() => null),
      api.wiki(sci).catch(() => null),
    ]);
    detail.value = d;
    wiki.value = w;
    loading.value = false;
  },
  { immediate: true },
);

</script>

<template>
  <div id="detail-modal" :class="{ 'is-open': sci }" :aria-hidden="sci ? 'false' : 'true'" role="dialog" aria-labelledby="modalCommon">
    <div class="modal-backdrop" @click="emit('close')"></div>
    <article class="modal-card">
      <button class="modal-close" type="button" aria-label="Close" @click="emit('close')">×</button>
      <div class="modal-grid">
        <div class="modal-img">
          <img id="modalImg" :src="imgSrc" :alt="sci ?? ''" />
          <div v-seg-pill class="pose-toggle" id="modalPoseToggle" role="tablist" aria-label="Pose">
            <i class="seg-pill" aria-hidden="true"></i>
            <button type="button" data-pose="1" :aria-current="pose === 1 ? 'true' : 'false'" aria-label="perched" @click="pose = 1">
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">
                <path d="M3.5 6.5 C 4 4, 6 3, 8 4 C 10 3.6, 11.6 4.6, 12 6.5 L 11.5 8 C 11 9.6, 9.4 10.4, 8 10.4 C 6.4 10.4, 4.8 9.6, 4.2 8 Z" />
                <circle cx="10.6" cy="5.7" r=".4" fill="currentColor" />
                <path d="M12 6.2 L 13.6 5.8" />
                <path d="M7.5 10.4 L 7.2 12.2" />
                <path d="M8.6 10.4 L 8.9 12.2" />
                <path d="M2 12.6 H 13" />
              </svg>
              <span class="tip">perched</span>
            </button>
            <button type="button" data-pose="2" :aria-current="pose === 2 ? 'true' : 'false'" aria-label="in flight" @click="pose = 2">
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">
                <path d="M1.5 8 Q 4.5 4, 7.5 7.5 Q 11 4, 14.5 8" />
                <path d="M7.5 7.5 L 8 9.5" />
                <circle cx="8.5" cy="7.2" r=".4" fill="currentColor" />
                <path d="M8.6 7 L 10 6.6" />
              </svg>
              <span class="tip">in flight</span>
            </button>
          </div>
        </div>
        <div class="modal-info">
          <h2 id="modalCommon">{{ summary?.com ?? sci }}</h2>
          <p class="sci" id="modalSci">{{ sci }}</p>
          <div class="modal-stats">
            <div><span class="n" id="modalAllTime">{{ allTime }}</span><span class="lbl">all time</span></div>
            <div v-show="!birds.isAllWindow" id="modalWindowStat">
              <span class="n" id="modalWindow">{{ fmtN(windowCount) }}</span>
              <span class="lbl" id="modalWindowLbl">{{ birds.windowLabel }}</span>
            </div>
            <div><span class="n" id="modalFirstSeen">{{ firstSeen }}</span><span class="lbl">first heard</span></div>
          </div>
          <p class="desc" id="modalDesc" :class="{ placeholder: !wiki?.extract }">
            {{ loading ? 'Loading description...' : (wiki?.extract ?? 'No description available.') }}
          </p>
          <div class="modal-meta">
            <span class="meta-item"><span class="k">genus</span><span class="v" id="modalGenus">{{ genus }}</span></span>
            <span class="meta-item"><span class="k">rarity</span><span class="v" id="modalRarity" :class="{ rare: rarity === 'rare' }">{{ rarity }}</span></span>
          </div>
        </div>
      </div>
      <div class="modal-recordings">
        <div class="rec-head">
          <h3>Recordings</h3>
          <span class="rec-count" id="modalRecCount">{{ detail ? detail.detections.length + ' captured' : '' }}</span>
        </div>
        <ol id="modalRecordings" ref="recList">
          <li v-if="loading" class="rec-empty">Loading recordings...</li>
          <li v-else-if="!detail?.detections.length" class="rec-empty">No recordings yet.</li>
          <li
            v-for="row in detail?.detections ?? []"
            v-else
            :key="row.file"
            class="rec-row"
            :class="{ expanded: expanded.has(row.file) }"
            :data-file="row.file"
            :data-date="row.d"
            @click="toggleExpand(row.file)"
          >
            <button
              class="play"
              type="button"
              aria-label="play"
              :data-active="activeFile === row.file && !isPaused ? 'true' : null"
              @click.stop="playFile(row.file)"
            >
              <svg v-if="activeFile === row.file && !isPaused" viewBox="0 0 12 12" fill="currentColor">
                <rect x="3" y="2" width="2.5" height="8" /><rect x="6.5" y="2" width="2.5" height="8" />
              </svg>
              <svg v-else viewBox="0 0 12 12" fill="currentColor"><path d="M3 2 L10 6 L3 10 Z" /></svg>
            </button>
            <span class="when">{{ fmtRecTime(row.d, row.t) }}<small>{{ fmtDateLine(row.d, row.t) }}</small></span>
            <span class="conf">{{ Math.round((Number(row.conf) || 0) * 100) }}%</span>
            <div class="rec-spectro" aria-hidden="true" @click.stop>
              <div class="rec-spectro-loading">loading spectrogram...</div>
              <div class="rec-spectro-played"></div>
              <div class="rec-spectro-cursor"></div>
              <div
                class="rec-spectro-scrub"
                role="slider"
                aria-label="scrub"
                tabindex="0"
                @mousedown.prevent="onScrubDown(row.file, $event.clientX)"
                @touchstart.prevent="onScrubDown(row.file, $event.touches[0].clientX)"
              ></div>
            </div>
          </li>
        </ol>
      </div>
      <div class="modal-actions">
        <a id="modalWiki" class="chip ext" :href="sci ? wikiUrl(sci) : '#'" target="_blank" rel="noopener">wiki</a>
        <a id="modalEbird" class="chip ext" :href="sci ? ebirdUrl(sci) : '#'" target="_blank" rel="noopener">ebird</a>
      </div>
    </article>
  </div>
</template>
