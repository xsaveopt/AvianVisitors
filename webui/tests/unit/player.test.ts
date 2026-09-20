import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const fetchAudioObjectUrl = vi.fn<(url: string) => Promise<string>>();
const audioClaim = vi.fn<(stop: () => void) => void>();
const audioRelease = vi.fn<(stop: () => void) => void>();

vi.mock('@/api/client', () => ({
  fetchAudioObjectUrl: (url: string) => fetchAudioObjectUrl(url),
}));

vi.mock('@/audio/claim', () => ({
  audioClaim: (stop: () => void) => audioClaim(stop),
  audioRelease: (stop: () => void) => audioRelease(stop),
}));

class FakeAudio {
  static instances: FakeAudio[] = [];
  static playRejects = false;
  static pauseThrows = false;

  readonly listeners: Record<string, Array<() => void>> = {};
  paused = false;
  played = 0;

  constructor(readonly src: string) {
    FakeAudio.instances.push(this);
  }

  addEventListener(name: string, fn: () => void): void {
    (this.listeners[name] ??= []).push(fn);
  }

  play(): Promise<void> {
    this.played += 1;
    return FakeAudio.playRejects ? Promise.reject(new Error('blocked')) : Promise.resolve();
  }

  pause(): void {
    if (FakeAudio.pauseThrows) {
      throw new Error('detached');
    }
    this.paused = true;
  }

  fire(name: string): void {
    for (const fn of this.listeners[name] ?? []) {
      fn();
    }
  }
}

const revoked: string[] = [];

const { usePlayer } = await import('@/composables/usePlayer');

beforeEach(() => {
  FakeAudio.playRejects = false;
  FakeAudio.pauseThrows = false;
  fetchAudioObjectUrl.mockReset();
  fetchAudioObjectUrl.mockImplementation(async (url: string) => `blob:${url}`);
  vi.stubGlobal('Audio', FakeAudio);
  vi.stubGlobal('URL', {
    revokeObjectURL: (url: string) => revoked.push(url),
  });
  usePlayer().stop();
  FakeAudio.instances = [];
  revoked.length = 0;
  audioClaim.mockReset();
  audioRelease.mockReset();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('toggle', () => {
  it('starts idle', () => {
    const player = usePlayer();
    expect(player.activeKey.value).toBeNull();
    expect(player.state.value).toBe('idle');
  });

  it('fetches, plays and reports the active key', async () => {
    const player = usePlayer();
    await player.toggle('a', '/api/recording?sci=a');
    expect(fetchAudioObjectUrl).toHaveBeenCalledWith('/api/recording?sci=a');
    expect(FakeAudio.instances).toHaveLength(1);
    expect(FakeAudio.instances[0].src).toBe('blob:/api/recording?sci=a');
    expect(FakeAudio.instances[0].played).toBe(1);
    expect(player.activeKey.value).toBe('a');
    expect(player.state.value).toBe('playing');
  });

  it('claims the shared audio slot', async () => {
    const player = usePlayer();
    await player.toggle('a', '/a');
    expect(audioClaim).toHaveBeenCalledTimes(1);
    expect(audioClaim.mock.calls[0][0]).toBe(player.stop);
  });

  it('toggling the same key again stops playback', async () => {
    const player = usePlayer();
    await player.toggle('a', '/a');
    await player.toggle('a', '/a');
    expect(FakeAudio.instances[0].paused).toBe(true);
    expect(player.activeKey.value).toBeNull();
    expect(player.state.value).toBe('idle');
    expect(revoked).toEqual(['blob:/a']);
    expect(fetchAudioObjectUrl).toHaveBeenCalledTimes(1);
  });

  it('a different key replaces the current clip', async () => {
    const player = usePlayer();
    await player.toggle('a', '/a');
    await player.toggle('b', '/b');
    expect(FakeAudio.instances).toHaveLength(2);
    expect(FakeAudio.instances[0].paused).toBe(true);
    expect(revoked).toEqual(['blob:/a']);
    expect(player.activeKey.value).toBe('b');
    expect(player.state.value).toBe('playing');
  });

  it('the ended event returns to idle', async () => {
    const player = usePlayer();
    await player.toggle('a', '/a');
    FakeAudio.instances[0].fire('ended');
    expect(player.activeKey.value).toBeNull();
    expect(player.state.value).toBe('idle');
  });

  const failures: Array<[string, () => void]> = [
    [
      'a failed download',
      () => fetchAudioObjectUrl.mockRejectedValue(new Error('404')),
    ],
    [
      'a blocked play',
      () => {
        FakeAudio.playRejects = true;
      },
    ],
  ];

  for (const [name, arrange] of failures) {
    it(`${name} leaves the player idle`, async () => {
      arrange();
      const player = usePlayer();
      await player.toggle('a', '/a');
      expect(player.activeKey.value).toBeNull();
      expect(player.state.value).toBe('idle');
    });
  }

  it('a blocked play still releases the object url', async () => {
    FakeAudio.playRejects = true;
    const player = usePlayer();
    await player.toggle('a', '/a');
    expect(revoked).toEqual(['blob:/a']);
  });

  it('a pending clip is dropped when a newer one wins the key', async () => {
    const player = usePlayer();
    let release: (url: string) => void = () => {};
    fetchAudioObjectUrl.mockImplementation(
      () =>
        new Promise<string>((resolve) => {
          release = resolve;
        }),
    );
    const pending = player.toggle('a', '/a');
    expect(player.state.value).toBe('loading');
    player.stop();
    release('blob:/a');
    await pending;
    expect(player.activeKey.value).toBeNull();
    expect(player.state.value).toBe('idle');
  });
});

describe('stop', () => {
  it('releases the shared slot', async () => {
    const player = usePlayer();
    await player.toggle('a', '/a');
    audioRelease.mockClear();
    player.stop();
    expect(audioRelease).toHaveBeenCalledWith(player.stop);
  });

  it('is safe with nothing playing', () => {
    const player = usePlayer();
    expect(() => player.stop()).not.toThrow();
    expect(revoked).toEqual([]);
  });

  it('survives an element that refuses to pause', async () => {
    const player = usePlayer();
    await player.toggle('a', '/a');
    FakeAudio.pauseThrows = true;
    expect(() => player.stop()).not.toThrow();
    expect(revoked).toEqual(['blob:/a']);
    expect(player.state.value).toBe('idle');
  });

  it('does not revoke the same url twice', async () => {
    const player = usePlayer();
    await player.toggle('a', '/a');
    player.stop();
    player.stop();
    expect(revoked).toEqual(['blob:/a']);
  });
});
