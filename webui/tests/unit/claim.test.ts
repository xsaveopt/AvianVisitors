import { beforeEach, describe, expect, it, vi } from 'vitest';
import { audioClaim, audioRelease } from '@/audio/claim';

let log: string[] = [];

function player(name: string): () => void {
  return () => log.push(name);
}

beforeEach(() => {
  const idle = vi.fn();
  audioClaim(idle);
  audioRelease(idle);
  log = [];
});

describe('audioClaim', () => {
  it('stops the previous holder', () => {
    const first = player('first');
    audioClaim(first);
    audioClaim(player('second'));
    expect(log).toEqual(['first']);
  });

  it('does not stop the same holder claiming twice', () => {
    const only = player('only');
    audioClaim(only);
    audioClaim(only);
    expect(log).toEqual([]);
  });

  it('only ever stops one holder back', () => {
    audioClaim(player('a'));
    audioClaim(player('b'));
    audioClaim(player('c'));
    expect(log).toEqual(['a', 'b']);
  });

  it('claims cleanly when nobody holds it', () => {
    audioClaim(player('first'));
    expect(log).toEqual([]);
  });

  it('a throwing holder does not block the new claim', () => {
    audioClaim(() => {
      throw new Error('already gone');
    });
    const second = player('second');
    expect(() => audioClaim(second)).not.toThrow();
    audioClaim(player('third'));
    expect(log).toEqual(['second']);
  });

  it('does not re-enter when the stopped holder releases itself', () => {
    const first: () => void = () => {
      log.push('first');
      audioRelease(first);
    };
    audioClaim(first);
    audioClaim(player('second'));
    audioClaim(player('third'));
    expect(log).toEqual(['first', 'second']);
  });
});

describe('audioRelease', () => {
  it('clears the claim so the next one stops nobody', () => {
    const first = player('first');
    audioClaim(first);
    audioRelease(first);
    audioClaim(player('second'));
    expect(log).toEqual([]);
  });

  it('ignores a release from a holder that no longer owns the claim', () => {
    const first = player('first');
    audioClaim(first);
    const second = player('second');
    audioClaim(second);
    log.length = 0;
    audioRelease(first);
    audioClaim(player('third'));
    expect(log).toEqual(['second']);
  });

  it('is safe to call twice', () => {
    const first = player('first');
    audioClaim(first);
    audioRelease(first);
    expect(() => audioRelease(first)).not.toThrow();
  });
});
