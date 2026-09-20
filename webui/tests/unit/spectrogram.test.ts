import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

let ctxCount = 0;
let ctxAvailable = true;

class FakeAudioContext {
  constructor() {
    ctxCount += 1;
  }

  async decodeAudioData(data: ArrayBuffer): Promise<unknown> {
    return { decodedFrom: data.byteLength };
  }
}

interface Call {
  url: string;
  init: RequestInit;
}

let calls: Call[] = [];

function respond(status: number, bytes = 8): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    arrayBuffer: async () => new ArrayBuffer(bytes),
  } as unknown as Response;
}

function stubFetch(handler: () => unknown): void {
  vi.stubGlobal('fetch', (url: string, init: RequestInit = {}) => {
    calls.push({ url, init });
    const out = handler();
    return out instanceof Error ? Promise.reject(out) : Promise.resolve(out);
  });
}

function stubEnvironment(theme: string | null = null): void {
  vi.stubGlobal(
    'window',
    ctxAvailable ? { AudioContext: FakeAudioContext, devicePixelRatio: 1 } : { devicePixelRatio: 1 },
  );
  vi.stubGlobal('document', {
    documentElement: { getAttribute: () => theme },
  });
  vi.stubGlobal('requestAnimationFrame', (fn: () => void) => {
    fn();
    return 1;
  });
}

async function load(): Promise<typeof import('@/audio/spectrogram')> {
  vi.resetModules();
  return import('@/audio/spectrogram');
}

beforeEach(() => {
  calls = [];
  ctxCount = 0;
  ctxAvailable = true;
  stubEnvironment();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('getSpecCtx', () => {
  it('creates one context and reuses it', async () => {
    const spec = await load();
    const first = spec.getSpecCtx();
    expect(first).toBeInstanceOf(FakeAudioContext);
    expect(spec.getSpecCtx()).toBe(first);
    expect(ctxCount).toBe(1);
  });

  it('falls back to the prefixed constructor', async () => {
    ctxAvailable = false;
    vi.stubGlobal('window', { webkitAudioContext: FakeAudioContext, devicePixelRatio: 1 });
    const spec = await load();
    expect(spec.getSpecCtx()).toBeInstanceOf(FakeAudioContext);
  });

  it('returns null without web audio', async () => {
    ctxAvailable = false;
    stubEnvironment();
    const spec = await load();
    expect(spec.getSpecCtx()).toBeNull();
  });
});

describe('decodeRecording', () => {
  it('fetches the recording and decodes it', async () => {
    stubFetch(() => respond(200, 16));
    const spec = await load();
    await expect(spec.decodeRecording('a b.wav')).resolves.toEqual({ decodedFrom: 16 });
    expect(calls[0].url).toBe('/api/recording?file=a%20b.wav');
  });

  it('caches the decoded buffer', async () => {
    stubFetch(() => respond(200));
    const spec = await load();
    const first = await spec.decodeRecording('a.wav');
    expect(await spec.decodeRecording('a.wav')).toBe(first);
    expect(calls).toHaveLength(1);
    expect(spec.cachedBuffer('a.wav')).toBe(first);
  });

  it('reports nothing cached for an unknown file', async () => {
    const spec = await load();
    expect(spec.cachedBuffer('never.wav')).toBeUndefined();
  });

  const failures: Array<[string, () => unknown, string]> = [
    ['an http error', () => respond(404), 'HTTP 404'],
    ['a server error', () => respond(500), 'HTTP 500'],
  ];

  for (const [name, handler, message] of failures) {
    it(`rejects on ${name}`, async () => {
      stubFetch(handler);
      const spec = await load();
      await expect(spec.decodeRecording('a.wav')).rejects.toThrow(message);
      expect(spec.cachedBuffer('a.wav')).toBeUndefined();
    });
  }

  it('rejects without web audio', async () => {
    ctxAvailable = false;
    stubEnvironment();
    stubFetch(() => respond(200));
    const spec = await load();
    await expect(spec.decodeRecording('a.wav')).rejects.toThrow('WebAudio not available');
    expect(calls).toHaveLength(0);
  });
});

class FakeCanvas {
  width = 0;
  height = 0;
  clientWidth = 0;
  clientHeight = 0;
  classes: string[] = [];
  painted: { data: Uint8ClampedArray; w: number; h: number } | null = null;

  readonly classList = { add: (name: string) => this.classes.push(name) };

  constructor(
    public parentElement: { clientWidth: number; clientHeight: number } | null,
    private readonly context = true,
  ) {}

  getContext(): unknown {
    if (!this.context) {
      return null;
    }
    return {
      createImageData: (w: number, h: number) => ({ data: new Uint8ClampedArray(w * h * 4), width: w, height: h }),
      putImageData: (img: { data: Uint8ClampedArray; width: number; height: number }) => {
        this.painted = { data: img.data, w: img.width, h: img.height };
      },
    };
  }
}

function tone(hz: number, sampleRate = 22050, length = 8192): unknown {
  const samples = new Float32Array(length);
  for (let i = 0; i < length; i++) {
    samples[i] = Math.sin((2 * Math.PI * hz * i) / sampleRate);
  }
  return { sampleRate, length, getChannelData: () => samples };
}

function silence(sampleRate = 22050, length = 8192): unknown {
  return { sampleRate, length, getChannelData: () => new Float32Array(length) };
}

function brightness(canvas: FakeCanvas): number {
  const data = canvas.painted!.data;
  let sum = 0;
  for (let p = 0; p < data.length; p += 4) {
    sum += data[p];
  }
  return sum / (data.length / 4);
}

function loudestRow(canvas: FakeCanvas): number {
  const { data, w, h } = canvas.painted!;
  let darkest = Number.POSITIVE_INFINITY;
  let row = 0;
  for (let y = 0; y < h; y++) {
    let sum = 0;
    for (let x = 0; x < w; x++) {
      sum += data[(y * w + x) * 4];
    }
    if (sum < darkest) {
      darkest = sum;
      row = y;
    }
  }
  return row;
}

describe('paintSpectrogram', () => {
  it('sizes the canvas from its parent and marks it ready', async () => {
    const spec = await load();
    const canvas = new FakeCanvas({ clientWidth: 240, clientHeight: 96 });
    spec.paintSpectrogram(canvas as unknown as HTMLCanvasElement, tone(3000) as AudioBuffer);
    expect(canvas.width).toBe(240);
    expect(canvas.height).toBe(96);
    expect(canvas.painted).not.toBeNull();
    expect(canvas.classes).toEqual(['ready']);
  });

  it('honours the device pixel ratio, capped at two', async () => {
    vi.stubGlobal('window', { AudioContext: FakeAudioContext, devicePixelRatio: 4 });
    const spec = await load();
    const canvas = new FakeCanvas({ clientWidth: 100, clientHeight: 50 });
    spec.paintSpectrogram(canvas as unknown as HTMLCanvasElement, silence() as AudioBuffer);
    expect(canvas.width).toBe(200);
    expect(canvas.height).toBe(100);
  });

  it('falls back to the canvas box without a parent', async () => {
    const spec = await load();
    const canvas = new FakeCanvas(null);
    canvas.clientWidth = 120;
    canvas.clientHeight = 64;
    spec.paintSpectrogram(canvas as unknown as HTMLCanvasElement, silence() as AudioBuffer);
    expect(canvas.width).toBe(120);
  });

  it('waits for a strip that has not been laid out yet', async () => {
    const spec = await load();
    const parent = { clientWidth: 0, clientHeight: 0 };
    let frames = 0;
    vi.stubGlobal('requestAnimationFrame', (fn: () => void) => {
      frames += 1;
      if (frames === 3) {
        parent.clientWidth = 200;
        parent.clientHeight = 88;
      }
      fn();
      return frames;
    });
    const canvas = new FakeCanvas(parent);
    spec.paintSpectrogram(canvas as unknown as HTMLCanvasElement, silence() as AudioBuffer);
    expect(frames).toBe(3);
    expect(canvas.width).toBe(200);
  });

  it('gives up quietly without a 2d context', async () => {
    const spec = await load();
    const canvas = new FakeCanvas({ clientWidth: 200, clientHeight: 88 }, false);
    expect(() =>
      spec.paintSpectrogram(canvas as unknown as HTMLCanvasElement, silence() as AudioBuffer),
    ).not.toThrow();
    expect(canvas.painted).toBeNull();
    expect(canvas.classes).toEqual([]);
  });

  it('paints a tone brighter than silence', async () => {
    const spec = await load();
    const parent = { clientWidth: 200, clientHeight: 88 };
    const quiet = new FakeCanvas(parent);
    const loud = new FakeCanvas(parent);
    spec.paintSpectrogram(quiet as unknown as HTMLCanvasElement, silence() as AudioBuffer);
    spec.paintSpectrogram(loud as unknown as HTMLCanvasElement, tone(3000) as AudioBuffer);
    expect(brightness(loud)).toBeLessThan(brightness(quiet));
  });

  it('puts a higher tone nearer the top', async () => {
    const spec = await load();
    const parent = { clientWidth: 200, clientHeight: 88 };
    const low = new FakeCanvas(parent);
    const high = new FakeCanvas(parent);
    spec.paintSpectrogram(low as unknown as HTMLCanvasElement, tone(800) as AudioBuffer);
    spec.paintSpectrogram(high as unknown as HTMLCanvasElement, tone(6000) as AudioBuffer);
    expect(loudestRow(high)).toBeLessThan(loudestRow(low));
  });

  it('inverts the palette for the dark theme', async () => {
    stubEnvironment('dark');
    const spec = await load();
    const parent = { clientWidth: 120, clientHeight: 48 };
    const canvas = new FakeCanvas(parent);
    spec.paintSpectrogram(canvas as unknown as HTMLCanvasElement, silence() as AudioBuffer);
    const data = canvas.painted!.data;
    expect([data[0], data[1], data[2], data[3]]).toEqual([23, 24, 28, 255]);
  });

  it('uses the light palette otherwise', async () => {
    const spec = await load();
    const canvas = new FakeCanvas({ clientWidth: 120, clientHeight: 48 });
    spec.paintSpectrogram(canvas as unknown as HTMLCanvasElement, silence() as AudioBuffer);
    const data = canvas.painted!.data;
    expect([data[0], data[1], data[2], data[3]]).toEqual([245, 240, 230, 255]);
  });

  it('leaves the background untouched for a clip shorter than one window', async () => {
    const spec = await load();
    const canvas = new FakeCanvas({ clientWidth: 120, clientHeight: 48 });
    spec.paintSpectrogram(canvas as unknown as HTMLCanvasElement, silence(22050, 256) as AudioBuffer);
    expect(brightness(canvas)).toBeCloseTo(245, 5);
    expect(canvas.classes).toEqual(['ready']);
  });
});
