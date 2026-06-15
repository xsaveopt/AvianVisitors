<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue';
import { api } from '@/api/client';
import { useTheme } from '@/composables/useTheme';
import type { SystemDiag } from '@/api/types';

const { theme, set: setTheme } = useTheme();

const props = defineProps<{ section: string | null }>();
const emit = defineEmits<{ close: [] }>();

const TITLES: Record<string, string> = {
  settings: 'settings',
  system: 'system',
  logs: 'logs',
  tools: 'tools',
};

type SliderKey = 'CONFIDENCE' | 'SENSITIVITY' | 'OVERLAP';
const sliders = reactive<Record<SliderKey, number>>({ CONFIDENCE: 0, SENSITIVITY: 0, OVERLAP: 0 });
const preserveOn = ref(false);
const fullDisk = ref('purge');
const pending = reactive<Record<string, unknown>>({});
const saveState = ref('');
const saveCls = ref('');
const dirty = computed(() => Object.keys(pending).length > 0);
const diag = ref<SystemDiag | null>(null);
const error = ref('');

const LOG_UNITS = ['recording', 'analysis', 'charts', 'stats', 'caddy', 'php-fpm', 'icecast', 'livestream'];
const logUnit = ref('recording');
const logLines = ref(120);
const logText = ref('loading...');
const logsPane = ref<HTMLElement | null>(null);
let autoScroll = true;
let pollT: number | undefined;

const TOOLS: Array<[string, string, string]> = [
  ['restart recording', 'captures live audio from the mic. restart this first if detections stall.', 'recording'],
  ['restart analysis', 'runs the neural net on recorded chunks. restart if detections are stuck.', 'analysis'],
  ['restart charts', 'renders the daily charts. restart if charts stop updating.', 'charts'],
  ['restart stats', 'the /stats page (streamlit). restart if stats stops loading.', 'stats'],
  ['restart livestream', 'icecast feed for the drawer live-audio button.', 'livestream'],
  ['restart icecast', 'web audio streaming server (fronts livestream).', 'icecast'],
];
const DEPLOY: Array<{ title: string; desc: string; lines: string[] }> = [
  {
    title: 'update to the latest version',
    desc: 'pulls the newest code and rebuilds the container. run this on the host where docker compose lives.',
    lines: ['cd AvianVisitors && git pull', 'docker compose up -d --build'],
  },
  {
    title: 'restart the container',
    desc: 'recreates the container without rebuilding. handy if things get stuck.',
    lines: ['docker compose restart'],
  },
];
const toolOut = reactive<Record<string, string>>({});
const toolBusy = reactive<Record<string, boolean>>({});

watch(
  () => props.section,
  async (section) => {
    error.value = '';
    stopLogs();
    if (section === 'settings') {
      await loadSettings();
    } else if (section === 'system') {
      await loadSystem();
    } else if (section === 'logs') {
      startLogs();
    }
  },
  { immediate: true },
);

watch([logUnit, logLines], () => {
  if (props.section === 'logs') {
    void tickLogs();
  }
});

async function tickLogs(): Promise<void> {
  try {
    const j = await api.logs(logUnit.value, logLines.value);
    logText.value = j.text || '(empty)';
    await nextTick();
    if (autoScroll && logsPane.value) {
      logsPane.value.scrollTop = logsPane.value.scrollHeight;
    }
  } catch {
    logText.value = 'pi unreachable - no data';
  }
}

function onLogsScroll(): void {
  const p = logsPane.value;
  if (!p) {
    return;
  }
  autoScroll = p.scrollTop + p.clientHeight >= p.scrollHeight - 20;
}

function startLogs(): void {
  stopLogs();
  logText.value = 'loading...';
  autoScroll = true;
  void tickLogs();
  pollT = window.setInterval(tickLogs, 4000);
}

function stopLogs(): void {
  if (pollT) {
    clearInterval(pollT);
    pollT = undefined;
  }
}

async function runRestart(unit: string): Promise<void> {
  if (!window.confirm('restart ' + unit + '?')) {
    return;
  }
  toolBusy[unit] = true;
  toolOut[unit] = '';
  try {
    const j = await api.restart(unit);
    toolOut[unit] = (j.ok ? 'ok' : 'rc=' + j.rc) + (j.out ? '\n' + j.out : '');
  } catch (e) {
    toolOut[unit] = e instanceof Error ? e.message : 'request failed';
  } finally {
    window.setTimeout(() => {
      toolBusy[unit] = false;
    }, 2000);
  }
}

async function copyDeploy(lines: string[]): Promise<void> {
  try {
    await navigator.clipboard.writeText(lines.join('\n'));
  } catch {
    error.value = '';
  }
}

onBeforeUnmount(() => stopLogs());

async function loadSettings(): Promise<void> {
  try {
    const cfg = await api.config();
    const v = cfg.values;
    sliders.CONFIDENCE = Number(v.CONFIDENCE) || 0;
    sliders.SENSITIVITY = Number(v.SENSITIVITY) || 0;
    sliders.OVERLAP = Number(v.OVERLAP) || 0;
    fullDisk.value = String(v.FULL_DISK ?? 'purge');
    preserveOn.value = cfg.preserve;
    for (const k of Object.keys(pending)) {
      delete pending[k];
    }
    setSaveState('');
  } catch {
    error.value = 'settings load failed';
  }
}

async function loadSystem(): Promise<void> {
  try {
    diag.value = await api.status('diag');
  } catch {
    error.value = 'system unreachable';
  }
}

function setSaveState(msg: string, cls = ''): void {
  saveState.value = msg;
  saveCls.value = cls;
}

function onSlider(key: SliderKey, raw: string): void {
  const v = Number(raw);
  sliders[key] = v;
  pending[key] = v;
  setSaveState('change pending');
}

function togglePreserve(): void {
  preserveOn.value = !preserveOn.value;
  pending.preserve = preserveOn.value;
  setSaveState('change pending');
}

function setFullDisk(v: string): void {
  fullDisk.value = v;
  pending.FULL_DISK = v;
  setSaveState('change pending');
}

async function saveSettings(): Promise<void> {
  if (!dirty.value) {
    return;
  }
  setSaveState('saving...');
  try {
    const result = await api.saveConfig({ ...pending });
    if (result.ok) {
      for (const k of Object.keys(pending)) {
        delete pending[k];
      }
      setSaveState('saved ✓', 'ok');
      window.setTimeout(() => setSaveState(''), 1800);
    } else {
      setSaveState('save failed', 'err');
    }
  } catch {
    setSaveState('network error', 'err');
  }
}
</script>

<template>
  <section
    class="admin-screen"
    id="adminScreen"
    :aria-hidden="section ? 'false' : 'true'"
  >
    <div class="admin-frame">
      <header class="admin-title">
        <a class="return-to-atlas" href="#" @click.prevent="emit('close')">‹ collage</a>
        <h1 id="adminTitle">{{ section ? TITLES[section] ?? section : '' }}</h1>
      </header>
      <div class="admin-body" id="adminBody">
        <p v-if="error" class="admin-unreachable">{{ error }}</p>

        <div v-else-if="section === 'settings'" class="admin-settings">
          <div class="menu-row">
            <div><span class="label">Theme</span><span class="hint">saved on this device</span></div>
            <div class="seg" data-theme-seg>
              <button type="button" data-theme="light" :aria-current="theme === 'light' ? 'true' : 'false'" @click="setTheme('light')">light</button>
              <button type="button" data-theme="dark" :aria-current="theme === 'dark' ? 'true' : 'false'" @click="setTheme('dark')">dark</button>
            </div>
          </div>

          <div class="menu-row">
            <div>
              <span class="label">Preserve all recordings</span>
              <span class="hint">don't auto-delete</span>
            </div>
            <button class="switch" type="button" role="switch" :aria-checked="preserveOn ? 'true' : 'false'" @click="togglePreserve"></button>
          </div>

          <div class="slider-row">
            <div class="head">
              <div class="label-block">
                <span class="label">Confidence threshold</span>
                <span class="hint">min score to log a detection</span>
              </div>
              <span class="value" data-value-for="CONFIDENCE">{{ sliders.CONFIDENCE.toFixed(2) }}</span>
            </div>
            <div class="slider-track">
              <input
                type="range"
                min="0.1"
                max="0.95"
                step="0.05"
                :value="sliders.CONFIDENCE"
                @input="onSlider('CONFIDENCE', ($event.target as HTMLInputElement).value)"
              />
            </div>
          </div>

          <div class="slider-row">
            <div class="head">
              <div class="label-block">
                <span class="label">Sensitivity</span>
                <span class="hint">analyzer sensitivity</span>
              </div>
              <span class="value" data-value-for="SENSITIVITY">{{ sliders.SENSITIVITY.toFixed(2) }}</span>
            </div>
            <div class="slider-track">
              <input
                type="range"
                min="0.5"
                max="1.5"
                step="0.05"
                :value="sliders.SENSITIVITY"
                @input="onSlider('SENSITIVITY', ($event.target as HTMLInputElement).value)"
              />
            </div>
          </div>

          <div class="slider-row">
            <div class="head">
              <div class="label-block">
                <span class="label">Chunk overlap</span>
                <span class="hint">seconds analyzed per pass</span>
              </div>
              <span class="value" data-value-for="OVERLAP">{{ sliders.OVERLAP.toFixed(1) }}</span>
            </div>
            <div class="slider-track">
              <input
                type="range"
                min="0"
                max="2.5"
                step="0.1"
                :value="sliders.OVERLAP"
                @input="onSlider('OVERLAP', ($event.target as HTMLInputElement).value)"
              />
            </div>
          </div>

          <div class="menu-row">
            <div><span class="label">When disk fills</span></div>
            <div class="seg" data-key="FULL_DISK">
              <button type="button" data-v="keep" :aria-current="fullDisk === 'keep' ? 'true' : 'false'" @click="setFullDisk('keep')">keep</button>
              <button type="button" data-v="purge" :aria-current="fullDisk === 'purge' ? 'true' : 'false'" @click="setFullDisk('purge')">purge</button>
            </div>
          </div>

          <div class="menu-save-row">
            <span class="save-state" id="saveState" :class="saveCls">{{ saveState }}</span>
            <button id="saveBtn" type="button" :disabled="!dirty" @click="saveSettings">save</button>
          </div>
        </div>

        <div v-else-if="section === 'system'" class="admin-grid">
          <template v-if="diag">
            <div class="admin-card">
              <h3>uptime</h3>
              <div class="v">{{ diag.system.uptime?.pretty ?? '-' }}</div>
            </div>
            <div class="admin-card">
              <h3>memory</h3>
              <div class="v">{{ diag.system.mem ? diag.system.mem.used_pct + '%' : '-' }}</div>
            </div>
            <div class="admin-card">
              <h3>cpu temp</h3>
              <div class="v">{{ diag.system.temp_c != null ? diag.system.temp_c + '°C' : '-' }}</div>
            </div>
            <div class="admin-card">
              <h3>birds.db</h3>
              <div class="v">{{ diag.system.birds_db?.exists ? 'ok' : 'missing' }}</div>
            </div>
            <table class="admin-tbl" id="adminServices">
              <thead><tr><th>unit</th><th>state</th></tr></thead>
              <tbody>
                <tr v-for="(state, name) in diag.services" :key="name">
                  <td>{{ name }}</td>
                  <td><span class="pill">{{ state.active }}</span></td>
                </tr>
              </tbody>
            </table>
          </template>
          <p v-else>loading...</p>
        </div>

        <template v-else-if="section === 'logs'">
          <div class="admin-logs-toolbar">
            <label>unit</label>
            <select id="adminLogsUnit" v-model="logUnit">
              <option v-for="u in LOG_UNITS" :key="u" :value="u">{{ u }}</option>
            </select>
            <label>lines</label>
            <input id="adminLogsLines" v-model.number="logLines" type="number" min="20" max="500" step="20" />
          </div>
          <div class="admin-logs-pane" id="adminLogsOut" ref="logsPane" @scroll="onLogsScroll">{{ logText }}</div>
        </template>

        <template v-else-if="section === 'tools'">
          <div class="admin-actions-grid">
            <div v-for="a in TOOLS" :key="a[2]" class="admin-action">
              <h4>{{ a[0] }}</h4>
              <p>{{ a[1] }}</p>
              <button class="run" type="button" :data-unit="a[2]" :disabled="toolBusy[a[2]]" @click="runRestart(a[2])">
                {{ toolBusy[a[2]] ? '...' : 'run' }}
              </button>
              <div class="out" :data-out="a[2]">{{ toolOut[a[2]] }}</div>
            </div>
          </div>
          <h2 class="admin-section-head">heal / update</h2>
          <div class="admin-actions-grid">
            <div v-for="d in DEPLOY" :key="d.title" class="admin-action deploy">
              <h4>{{ d.title }}</h4>
              <p>{{ d.desc }}</p>
              <pre>{{ d.lines.join('\n') }}</pre>
              <button class="copy" type="button" @click="copyDeploy(d.lines)">copy</button>
            </div>
          </div>
        </template>

        <p v-else class="admin-unreachable">{{ TITLES[section ?? ''] ?? section }} panel coming soon.</p>
      </div>
    </div>
  </section>
</template>
