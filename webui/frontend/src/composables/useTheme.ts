import { ref } from 'vue';
import { api } from '@/api/client';

type Theme = 'light' | 'dark';

const KEY = 'bird:theme';

function read(): Theme {
  try {
    return localStorage.getItem(KEY) === 'dark' ? 'dark' : 'light';
  } catch {
    return 'light';
  }
}

function cache(value: Theme): void {
  try {
    localStorage.setItem(KEY, value);
  } catch {
    return;
  }
}

const theme = ref<Theme>(read());

function applyDom(value: Theme): void {
  if (value === 'dark') {
    document.documentElement.setAttribute('data-theme', 'dark');
  } else {
    document.documentElement.removeAttribute('data-theme');
  }
}

applyDom(theme.value);

function applyLocal(value: Theme): void {
  theme.value = value;
  applyDom(value);
  cache(value);
}

export function useTheme() {
  async function set(value: Theme): Promise<void> {
    applyLocal(value);
    try {
      await api.setTheme(value);
    } catch {
      return;
    }
  }

  async function sync(): Promise<void> {
    try {
      const { theme: server } = await api.theme();
      applyLocal(server === 'dark' ? 'dark' : 'light');
    } catch {
      return;
    }
  }

  return { theme, set, sync };
}
