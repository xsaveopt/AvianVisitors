import { onMounted, onUnmounted, ref } from 'vue';

export interface HashRoute {
  sci: string | null;
  about: boolean;
  admin: string | null;
}

function parse(): HashRoute {
  const hash = location.hash;
  const sci = hash.match(/^#sci=(.+)$/);
  const admin = hash.match(/^#admin=([a-z]+)/);
  return {
    sci: sci ? decodeURIComponent(sci[1]) : null,
    about: hash === '#about',
    admin: admin ? admin[1] : null,
  };
}

export function useHashRoute() {
  const route = ref<HashRoute>(parse());
  const update = () => {
    route.value = parse();
  };

  onMounted(() => window.addEventListener('hashchange', update));
  onUnmounted(() => window.removeEventListener('hashchange', update));

  function go(hash: string): void {
    if (location.hash === hash) {
      update();
    } else {
      location.hash = hash;
    }
  }

  function clear(): void {
    if (location.hash) {
      location.hash = '';
    } else {
      update();
    }
  }

  return { route, go, clear };
}
