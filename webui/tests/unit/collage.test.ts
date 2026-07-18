import { describe, expect, it } from 'vitest';
import { layoutCollage, slugify } from '@/collage/algorithm';
import type { RecentSpecies } from '@/api/types';

function species(sci: string, n: number): RecentSpecies {
  return { sci, n } as unknown as RecentSpecies;
}

describe('slugify', () => {
  it('lowercases and hyphenates', () => {
    expect(slugify('Calypte anna')).toBe('calypte-anna');
  });

  it('collapses runs of non-alphanumerics', () => {
    expect(slugify("Anna's   Hummingbird!!")).toBe('anna-s-hummingbird');
  });

  it('trims leading and trailing separators', () => {
    expect(slugify('  Spinus psaltria  ')).toBe('spinus-psaltria');
    expect(slugify('---x---')).toBe('x');
  });
});

describe('layoutCollage', () => {
  it('returns nothing for an empty list', () => {
    expect(layoutCollage([], 800, 600)).toEqual([]);
  });

  it('skips species without a mask', () => {
    expect(layoutCollage([species('Totally fakebird', 5)], 800, 600)).toEqual([]);
  });

  it('places known species with finite coordinates', () => {
    const tiles = layoutCollage([species('Cyanistes caeruleus', 10), species('Parus major', 3)], 1000, 800);
    expect(tiles.length).toBe(2);
    for (const tile of tiles) {
      expect(Number.isFinite(tile.x)).toBe(true);
      expect(Number.isFinite(tile.y)).toBe(true);
      expect(tile.fullW).toBeGreaterThan(0);
    }
  });
});
