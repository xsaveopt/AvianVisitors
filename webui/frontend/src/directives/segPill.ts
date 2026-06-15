import type { Directive } from 'vue';

interface SegEl extends HTMLElement {
  __segMo?: MutationObserver;
  __segRo?: ResizeObserver;
  __segRaf?: number;
}

function sync(el: HTMLElement): void {
  const pill = el.querySelector<HTMLElement>('.seg-pill');
  const active = el.querySelector<HTMLElement>('button[aria-current="true"]');
  if (!pill || !active) {
    return;
  }
  pill.style.width = active.offsetWidth + 'px';
  pill.style.transform = 'translateX(' + active.offsetLeft + 'px)';
}

function schedule(el: SegEl): void {
  if (el.__segRaf) {
    cancelAnimationFrame(el.__segRaf);
  }
  el.__segRaf = requestAnimationFrame(() => sync(el));
}

export const vSegPill: Directive<SegEl> = {
  mounted(el) {
    el.__segMo = new MutationObserver(() => schedule(el));
    el.__segMo.observe(el, { attributes: true, attributeFilter: ['aria-current'], subtree: true });
    el.__segRo = new ResizeObserver(() => schedule(el));
    el.__segRo.observe(el);
    schedule(el);
  },
  updated(el) {
    schedule(el);
  },
  unmounted(el) {
    el.__segMo?.disconnect();
    el.__segRo?.disconnect();
    if (el.__segRaf) {
      cancelAnimationFrame(el.__segRaf);
    }
  },
};
