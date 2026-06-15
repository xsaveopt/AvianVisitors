import { ref } from 'vue';
import { fetchAudioObjectUrl } from '@/api/client';
import { audioClaim, audioRelease } from '@/audio/claim';

const activeKey = ref<string | null>(null);
const state = ref<'idle' | 'loading' | 'playing'>('idle');

let audio: HTMLAudioElement | null = null;
let objectUrl: string | null = null;

function teardown(): void {
  if (audio) {
    try {
      audio.pause();
    } catch {
      audio = null;
    }
    audio = null;
  }
  if (objectUrl) {
    URL.revokeObjectURL(objectUrl);
    objectUrl = null;
  }
}

export function usePlayer() {
  function stop(): void {
    audioRelease(stop);
    teardown();
    activeKey.value = null;
    state.value = 'idle';
  }

  async function toggle(key: string, url: string): Promise<void> {
    if (activeKey.value === key && audio) {
      stop();
      return;
    }
    stop();
    audioClaim(stop);
    activeKey.value = key;
    state.value = 'loading';
    try {
      objectUrl = await fetchAudioObjectUrl(url);
      audio = new Audio(objectUrl);
      audio.addEventListener('ended', stop);
      await audio.play();
      if (activeKey.value === key) {
        state.value = 'playing';
      }
    } catch {
      stop();
    }
  }

  return { activeKey, state, toggle, stop };
}
