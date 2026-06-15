import { ref } from 'vue';

type Theme = 'light' | 'dark';

const KEY = 'bird:theme';

function read(): Theme {
  try {
    return localStorage.getItem(KEY) === 'dark' ? 'dark' : 'light';
  } catch {
    return 'light';
  }
}

const theme = ref<Theme>(read());

function apply(value: Theme): void {
  theme.value = value;
  if (value === 'dark') {
    document.documentElement.setAttribute('data-theme', 'dark');
  } else {
    document.documentElement.removeAttribute('data-theme');
  }
  try {
    localStorage.setItem(KEY, value);
  } catch {
    theme.value = value;
  }
}

export function useTheme() {
  function set(value: Theme): void {
    apply(value);
  }
  return { theme, set };
}
