import { describe, expect, it } from 'vitest';
import { layoutCollage, slugify } from '@/collage/algorithm';
import type { Tile } from '@/collage/algorithm';
import type { RecentSpecies } from '@/api/types';
import masksData from '@/collage/data/masks.json';

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

const KNOWN = Object.keys(masksData as Record<string, unknown>)
  .sort()
  .map((slug) => slug.replace(/-/g, ' '));

function pick(count: number, n: (i: number) => number = (i) => count - i): RecentSpecies[] {
  const step = Math.floor(KNOWN.length / count);
  return Array.from({ length: count }, (_, i) => species(KNOWN[i * step], n(i)));
}

function area(tile: Tile): number {
  return tile.fullW * tile.fullH;
}

function overlaps(tiles: Tile[], W: number, H: number): number {
  const owner = new Int32Array(W * H).fill(-1);
  let clashes = 0;
  tiles.forEach((tile, index) => {
    const sx = tile.fullW / tile.mask.w;
    const sy = tile.fullH / tile.mask.h;
    for (const [cx, cy] of tile.mask.cells) {
      const x0 = Math.max(0, Math.ceil(tile.x + cx * sx - 0.5));
      const x1 = Math.min(W - 1, Math.floor(tile.x + (cx + 1) * sx - 0.5));
      const y0 = Math.max(0, Math.ceil(tile.y + cy * sy - 0.5));
      const y1 = Math.min(H - 1, Math.floor(tile.y + (cy + 1) * sy - 0.5));
      for (let py = y0; py <= y1; py++) {
        for (let px = x0; px <= x1; px++) {
          const at = py * W + px;
          if (owner[at] !== -1 && owner[at] !== index) clashes++;
          owner[at] = index;
        }
      }
    }
  });
  return clashes;
}

describe('layoutCollage packing', () => {
  const viewports: Array<[number, number, number]> = [
    [1280, 800, 4],
    [1280, 800, 12],
    [1920, 1080, 30],
    [390, 844, 10],
    [700, 700, 20],
  ];

  it.each(viewports)('keeps every tile inside a %ix%i viewport with %i species', (W, H, count) => {
    const tiles = layoutCollage(pick(count), W, H);
    expect(tiles.length).toBe(count);
    for (const tile of tiles) {
      expect(tile.x).toBeGreaterThanOrEqual(-1);
      expect(tile.y).toBeGreaterThanOrEqual(-1);
      expect(tile.x + tile.fullW).toBeLessThanOrEqual(W + 1);
      expect(tile.y + tile.fullH).toBeLessThanOrEqual(H + 1);
    }
  });

  it.each(viewports)('never overlaps bird silhouettes in a %ix%i viewport with %i species', (W, H, count) => {
    const tiles = layoutCollage(pick(count), W, H);
    expect(overlaps(tiles, W, H)).toBe(0);
  });

  it.each(viewports)('centres the cluster in a %ix%i viewport with %i species', (W, H, count) => {
    const tiles = layoutCollage(pick(count), W, H);
    const left = Math.min(...tiles.map((t) => t.x));
    const right = Math.max(...tiles.map((t) => t.x + t.fullW));
    const top = Math.min(...tiles.map((t) => t.y));
    const bottom = Math.max(...tiles.map((t) => t.y + t.fullH));
    expect(Math.abs((left + right) / 2 - W / 2)).toBeLessThanOrEqual(1);
    expect(Math.abs((top + bottom) / 2 - H / 2)).toBeLessThanOrEqual(1);
  });

  it('keeps total tile area within the packing budget', () => {
    const W = 1280;
    const H = 800;
    const tiles = layoutCollage(pick(4), W, H);
    const total = tiles.reduce((sum, t) => sum + area(t), 0);
    expect(total).toBeLessThanOrEqual(W * H * 0.46 + 1e-6);
  });

  it('is deterministic for the same input', () => {
    const a = layoutCollage(pick(12), 1280, 800).map((t) => [t.data.sci, t.x, t.y, t.fullW]);
    const b = layoutCollage(pick(12), 1280, 800).map((t) => [t.data.sci, t.x, t.y, t.fullW]);
    expect(a).toEqual(b);
  });
});

describe('layoutCollage scaling', () => {
  it('sizes tiles by count to the 0.65 power', () => {
    const items = pick(3, (i) => [100, 10, 1][i]);
    const tiles = layoutCollage(items, 1280, 800);
    const bySci = new Map(tiles.map((t) => [t.data.sci, area(t)]));
    const big = bySci.get(items[0].sci)!;
    const mid = bySci.get(items[1].sci)!;
    const small = bySci.get(items[2].sci)!;
    expect(big).toBeGreaterThan(mid);
    expect(mid).toBeGreaterThan(small);
    expect(big / mid).toBeCloseTo(Math.pow(10, 0.65), 6);
    expect(mid / small).toBeCloseTo(Math.pow(10, 0.65), 6);
  });

  it('gives equal counts equal area', () => {
    const tiles = layoutCollage(pick(6, () => 7), 1280, 800);
    const areas = tiles.map(area);
    for (const a of areas) {
      expect(a).toBeCloseTo(areas[0], 6);
    }
  });

  it('keeps the aspect ratio from dims', () => {
    const tiles = layoutCollage(pick(5), 1280, 800);
    for (const tile of tiles) {
      expect(tile.fullW / tile.fullH).toBeCloseTo(tile.ar, 9);
    }
  });

  it('treats missing or zero counts as one', () => {
    const items = pick(3, (i) => [1, 0, Number.NaN][i]);
    const areas = layoutCollage(items, 1280, 800).map(area);
    expect(areas[1]).toBeCloseTo(areas[0], 6);
    expect(areas[2]).toBeCloseTo(areas[0], 6);
  });

  it('keeps the dominant species largest and places every tile', () => {
    const items = pick(20, (i) => (i === 0 ? 5000 : 1));
    const tiles = layoutCollage(items, 1280, 800);
    const top = tiles.find((t) => t.data.sci === items[0].sci)!;
    for (const tile of tiles) {
      if (tile !== top) expect(area(tile)).toBeLessThanOrEqual(area(top));
    }
    expect(tiles.every((t) => t.x > -1000)).toBe(true);
  });
});
