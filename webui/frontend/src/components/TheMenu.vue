<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue';
import { useAuthStore } from '@/stores/auth';
import { authHeaders, getCredentials } from '@/api/credentials';
import { audioClaim, audioRelease } from '@/audio/claim';

defineProps<{ open: boolean }>();
const auth = useAuthStore();

const username = ref('');
const password = ref('');
const hint = ref('enter username and password to unlock tools.');
const hintError = ref(false);

async function submit(): Promise<void> {
  const ok = await auth.login(username.value.trim(), password.value);
  if (ok) {
    password.value = '';
    hint.value = '';
    hintError.value = false;
  } else {
    hint.value = 'wrong username or password.';
    hintError.value = true;
  }
}

const liveOn = ref(false);
const status = ref('');
const statusErr = ref(false);
const liveSpectro = ref<HTMLCanvasElement | null>(null);

let liveEl: HTMLAudioElement | null = null;
let audioCtx: AudioContext | null = null;
let srcNode: MediaElementAudioSourceNode | null = null;
let analyser: AnalyserNode | null = null;
let specRaf: number | null = null;
let liveMs: MediaSource | null = null;
let liveReader: ReadableStreamDefaultReader<Uint8Array> | null = null;

function setStatus(msg: string, isErr = false): void {
  status.value = msg;
  statusErr.value = isErr;
}

function paintBlank(): void {
  const el = liveSpectro.value;
  if (!el) {
    return;
  }
  const ctx = el.getContext('2d');
  if (!ctx) {
    return;
  }
  ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--paper-2').trim() || '#efe8d8';
  ctx.fillRect(0, 0, el.width, el.height);
}

function pipeAuthedStream(el: HTMLAudioElement, reject: (e: Error) => void): void {
  if (!window.MediaSource || !MediaSource.isTypeSupported('audio/mpeg')) {
    reject(new Error('live audio needs a modern browser'));
    return;
  }
  liveMs = new MediaSource();
  el.src = URL.createObjectURL(liveMs);
  liveMs.addEventListener('sourceopen', () => {
    let sb: SourceBuffer;
    try {
      sb = liveMs!.addSourceBuffer('audio/mpeg');
    } catch (e) {
      reject(e as Error);
      return;
    }
    const queue: BufferSource[] = [];
    const flush = (): void => {
      if (sb.updating || !queue.length) {
        return;
      }
      try {
        sb.appendBuffer(queue.shift()!);
      } catch {
        return;
      }
    };
    sb.addEventListener('updateend', flush);
    fetch('/stream?t=' + Date.now(), { headers: authHeaders() })
      .then((r) => {
        if (!r.ok) {
          reject(new Error('HTTP ' + r.status));
          return;
        }
        liveReader = r.body!.getReader();
        const pump = (): void => {
          liveReader!
            .read()
            .then((res) => {
              if (res.done) {
                return;
              }
              queue.push(res.value as BufferSource);
              flush();
              pump();
            })
            .catch(() => {});
        };
        pump();
      })
      .catch(reject);
  });
}

function startAudio(): Promise<void> {
  return new Promise((resolve, reject) => {
    liveEl = new Audio();
    let settled = false;
    liveEl.addEventListener('playing', () => {
      if (settled) {
        return;
      }
      settled = true;
      resolve();
    });
    liveEl.addEventListener('error', () => {
      if (settled) {
        return;
      }
      settled = true;
      reject(new Error('stream error - check /#admin=system'));
    });
    audioClaim(stopAudio);
    if (getCredentials()) {
      pipeAuthedStream(liveEl, (e) => {
        if (!settled) {
          settled = true;
          reject(e);
        }
      });
    } else {
      liveEl.src = '/stream?t=' + Date.now();
    }
    liveEl.play().catch((e) => {
      if (settled) {
        return;
      }
      settled = true;
      reject(e);
    });
  });
}

function stopAudio(): void {
  audioRelease(stopAudio);
  if (specRaf) {
    cancelAnimationFrame(specRaf);
    specRaf = null;
  }
  if (liveReader) {
    try {
      void liveReader.cancel();
    } catch {
      liveReader = null;
    }
    liveReader = null;
  }
  if (liveMs) {
    try {
      if (liveMs.readyState === 'open') {
        liveMs.endOfStream();
      }
    } catch {
      liveMs = null;
    }
    liveMs = null;
  }
  if (liveEl) {
    try {
      liveEl.pause();
    } catch {
      liveEl = null;
    }
    if (liveEl) {
      liveEl.src = '';
    }
    liveEl = null;
  }
  if (srcNode) {
    try {
      srcNode.disconnect();
    } catch {
      srcNode = null;
    }
    srcNode = null;
  }
  if (analyser) {
    try {
      analyser.disconnect();
    } catch {
      analyser = null;
    }
    analyser = null;
  }
  liveOn.value = false;
  paintBlank();
}

function attachSpectrogram(): void {
  if (!liveEl) {
    return;
  }
  if (!audioCtx) {
    const Ctx = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctx) {
      return;
    }
    audioCtx = new Ctx();
  }
  if (audioCtx.state === 'suspended') {
    void audioCtx.resume();
  }
  try {
    srcNode = audioCtx.createMediaElementSource(liveEl);
  } catch {
    return;
  }
  analyser = audioCtx.createAnalyser();
  analyser.fftSize = 1024;
  analyser.smoothingTimeConstant = 0.7;
  srcNode.connect(analyser);
  analyser.connect(audioCtx.destination);
  drawSpectrogram();
}

function toRGB(str: string, fallback: string): [number, number, number] {
  const c = liveSpectro.value?.getContext('2d');
  if (!c) {
    return [0, 0, 0];
  }
  c.fillStyle = fallback;
  c.fillStyle = str;
  const s = c.fillStyle;
  if (s.charAt(0) === '#') {
    return [parseInt(s.substr(1, 2), 16), parseInt(s.substr(3, 2), 16), parseInt(s.substr(5, 2), 16)];
  }
  const m = s.match(/(\d+)[,\s]+(\d+)[,\s]+(\d+)/);
  return m ? [+m[1], +m[2], +m[3]] : [0, 0, 0];
}

function drawSpectrogram(): void {
  const el = liveSpectro.value;
  const ctx = el?.getContext('2d');
  if (!el || !ctx || !analyser) {
    return;
  }
  const W = el.width;
  const H = el.height;
  const cs = getComputedStyle(document.documentElement);
  const paper = cs.getPropertyValue('--paper-2').trim() || '#efe8d8';
  const bg = toRGB(paper, '#efe8d8');
  const fg = toRGB(cs.getPropertyValue('--ink').trim() || '#1a1612', '#1a1612');
  ctx.fillStyle = paper;
  ctx.fillRect(0, 0, W, H);
  const bins = new Uint8Array(analyser.frequencyBinCount);
  const tick = (): void => {
    if (!analyser) {
      return;
    }
    const img = ctx.getImageData(1, 0, W - 1, H);
    ctx.putImageData(img, 0, 0);
    ctx.clearRect(W - 1, 0, 1, H);
    analyser.getByteFrequencyData(bins);
    const n = bins.length;
    const lo = Math.floor((n * 250) / 24000);
    const hi = Math.floor((n * 12000) / 24000);
    for (let y = 0; y < H; y++) {
      const t = 1 - y / H;
      const idx = Math.round(lo + (hi - lo) * Math.pow(t, 1.6));
      const v = (bins[idx] || 0) / 255;
      const e = v * v * (3 - 2 * v);
      const r = bg[0] + Math.round((fg[0] - bg[0]) * e);
      const g = bg[1] + Math.round((fg[1] - bg[1]) * e);
      const b = bg[2] + Math.round((fg[2] - bg[2]) * e);
      ctx.fillStyle = 'rgb(' + r + ',' + g + ',' + b + ')';
      ctx.fillRect(W - 1, y, 1, 1);
    }
    specRaf = requestAnimationFrame(tick);
  };
  tick();
}

function toggleLive(): void {
  if (liveOn.value) {
    setStatus('');
    stopAudio();
    return;
  }
  liveOn.value = true;
  setStatus('connecting...');
  startAudio()
    .then(() => {
      setStatus('streaming from pi');
      attachSpectrogram();
    })
    .catch((err: unknown) => {
      stopAudio();
      const msg = (err instanceof Error && err.message) || 'stream unavailable';
      if (msg.indexOf('NotAllowed') !== -1 || msg.indexOf('user') !== -1) {
        setStatus('browser blocked autoplay - tap listen again', true);
      } else {
        setStatus(msg, true);
      }
    });
}

onBeforeUnmount(() => stopAudio());
</script>

<template>
  <aside id="menu-dd" :class="{ open }" :aria-hidden="open ? 'false' : 'true'">
    <div id="dd-locked">
      <form class="lock-row" id="unlockForm" @submit.prevent="submit">
        <input
          id="lockUser"
          v-model="username"
          type="text"
          placeholder="username"
          autocomplete="username"
        />
        <input
          id="lockPass"
          v-model="password"
          type="password"
          placeholder="password"
          autocomplete="current-password"
        />
        <button type="submit" aria-label="unlock">→</button>
      </form>
      <p class="lock-hint" id="lockHint" :class="{ 'lock-err': hintError }">{{ hint }}</p>
    </div>
    <nav class="menu-items" :class="{ show: auth.authed }" id="dd-items">
      <div class="live-audio" id="liveAudio" :data-on="liveOn ? 'true' : 'false'">
        <div class="pulse"></div>
        <div class="label">Live audio<span class="hint">stream from the mic</span></div>
        <button type="button" id="liveAudioBtn" @click.stop="toggleLive">
          <svg v-if="liveOn" viewBox="0 0 12 12" fill="currentColor"><rect x="3" y="3" width="6" height="6" /></svg>
          <svg v-else viewBox="0 0 12 12" fill="currentColor"><path d="M3 2 L10 6 L3 10 Z" /></svg>
          <span>{{ liveOn ? 'stop' : 'listen' }}</span>
        </button>
      </div>
      <canvas class="live-spectro" id="liveSpectro" ref="liveSpectro" width="600" height="120" aria-label="live spectrogram"></canvas>
      <div class="live-status" id="liveStatus" :class="{ err: statusErr }">{{ status }}</div>
      <div class="menu-links">
        <a v-for="item in auth.menu" :key="item.href" :href="item.href">
          <span>{{ item.label }}</span>
        </a>
      </div>
    </nav>
  </aside>
</template>
