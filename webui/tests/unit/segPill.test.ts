import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { DirectiveBinding, VNode } from 'vue';
import { vSegPill } from '@/directives/segPill';

interface FakeStyle {
  width?: string;
  transform?: string;
}

interface FakePill {
  style: FakeStyle;
}

interface FakeButton {
  offsetWidth: number;
  offsetLeft: number;
}

interface FakeHost {
  pill: FakePill | null;
  active: FakeButton | null;
  querySelector: (selector: string) => unknown;
  __segMo?: FakeObserver;
  __segRo?: FakeObserver;
  __segRaf?: number;
}

interface FakeObserver {
  callback: () => void;
  observed: Array<{ target: unknown; options: unknown }>;
  disconnected: boolean;
  observe: (target: unknown, options?: unknown) => void;
  disconnect: () => void;
}

let frames: Map<number, () => void>;
let nextFrame: number;
let cancelled: number[];
let mutationObservers: FakeObserver[];
let resizeObservers: FakeObserver[];

function observerClass(registry: FakeObserver[]) {
  return class {
    callback: () => void;
    observed: Array<{ target: unknown; options: unknown }> = [];
    disconnected = false;
    constructor(callback: () => void) {
      this.callback = callback;
      registry.push(this);
    }
    observe(target: unknown, options?: unknown): void {
      this.observed.push({ target, options });
    }
    disconnect(): void {
      this.disconnected = true;
    }
  };
}

function host(active: FakeButton | null, withPill = true): FakeHost {
  const el: FakeHost = {
    pill: withPill ? { style: {} } : null,
    active,
    querySelector(selector: string) {
      if (selector === '.seg-pill') {
        return el.pill;
      }
      if (selector === 'button[aria-current="true"]') {
        return el.active;
      }
      return null;
    },
  };
  return el;
}

function flush(): void {
  const pending = [...frames.values()];
  frames.clear();
  for (const run of pending) {
    run();
  }
}

type Hook = (el: unknown, binding: DirectiveBinding, vnode: VNode, prev: VNode | null) => void;

function call(name: 'mounted' | 'updated' | 'unmounted', el: FakeHost): void {
  const hook = vSegPill[name] as unknown as Hook;
  hook(el, {} as DirectiveBinding, {} as VNode, null);
}

beforeEach(() => {
  frames = new Map();
  nextFrame = 1;
  cancelled = [];
  mutationObservers = [];
  resizeObservers = [];
  vi.stubGlobal('requestAnimationFrame', (run: () => void) => {
    const id = nextFrame++;
    frames.set(id, run);
    return id;
  });
  vi.stubGlobal('cancelAnimationFrame', (id: number) => {
    cancelled.push(id);
    frames.delete(id);
  });
  vi.stubGlobal('MutationObserver', observerClass(mutationObservers));
  vi.stubGlobal('ResizeObserver', observerClass(resizeObservers));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('vSegPill', () => {
  it('sizes and moves the pill under the active button on the next frame', () => {
    const el = host({ offsetWidth: 48, offsetLeft: 96 });
    call('mounted', el);

    expect(el.pill?.style).toEqual({});
    flush();
    expect(el.pill?.style).toEqual({ width: '48px', transform: 'translateX(96px)' });
  });

  it('watches aria-current across the subtree and the element size', () => {
    const el = host({ offsetWidth: 10, offsetLeft: 0 });
    call('mounted', el);

    expect(mutationObservers).toHaveLength(1);
    expect(mutationObservers[0].observed).toEqual([
      { target: el, options: { attributes: true, attributeFilter: ['aria-current'], subtree: true } },
    ]);
    expect(resizeObservers).toHaveLength(1);
    expect(resizeObservers[0].observed).toEqual([{ target: el, options: undefined }]);
  });

  it('follows the active button when an observer fires', () => {
    const el = host({ offsetWidth: 30, offsetLeft: 0 });
    call('mounted', el);
    flush();

    el.active = { offsetWidth: 52, offsetLeft: 34 };
    mutationObservers[0].callback();
    flush();
    expect(el.pill?.style).toEqual({ width: '52px', transform: 'translateX(34px)' });

    el.active = { offsetWidth: 60, offsetLeft: 40 };
    resizeObservers[0].callback();
    flush();
    expect(el.pill?.style).toEqual({ width: '60px', transform: 'translateX(40px)' });
  });

  it('collapses bursts of changes into one frame', () => {
    const el = host({ offsetWidth: 20, offsetLeft: 5 });
    call('mounted', el);
    const first = el.__segRaf;

    call('updated', el);
    mutationObservers[0].callback();

    expect(cancelled).toContain(first);
    expect(frames.size).toBe(1);
  });

  it('leaves the pill alone when nothing is active', () => {
    const el = host(null);
    call('mounted', el);
    flush();
    expect(el.pill?.style).toEqual({});
  });

  it('does nothing when the pill element is missing', () => {
    const el = host({ offsetWidth: 20, offsetLeft: 5 }, false);
    call('mounted', el);
    expect(() => flush()).not.toThrow();
  });

  it('disconnects both observers and cancels a pending frame on unmount', () => {
    const el = host({ offsetWidth: 20, offsetLeft: 5 });
    call('mounted', el);
    const pending = el.__segRaf;

    call('unmounted', el);

    expect(mutationObservers[0].disconnected).toBe(true);
    expect(resizeObservers[0].disconnected).toBe(true);
    expect(cancelled).toContain(pending);
    flush();
    expect(el.pill?.style).toEqual({});
  });

  it('unmounts cleanly when it was never mounted', () => {
    const el = host(null);
    expect(() => call('unmounted', el)).not.toThrow();
    expect(cancelled).toEqual([]);
  });
});
