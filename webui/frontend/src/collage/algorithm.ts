import dimsData from './data/dims.json';
import masksData from './data/masks.json';
import type { RecentSpecies } from '@/api/types';

const DIMS = dimsData as unknown as Record<string, [number, number]>;
const MASKS = masksData as unknown as Record<string, { w: number; h: number; bits: string }>;

const GRID_STRIDE = 4;
const COLLAGE_PAD = 3;
const FLY_PROB = 0.15;

export interface Mask {
  w: number;
  h: number;
  cells: Array<[number, number]>;
}

export interface Tile {
  mask: Mask;
  data: RecentSpecies;
  pose: number;
  ar: number;
  score: number;
  area: number;
  fullW: number;
  fullH: number;
  x: number;
  y: number;
}

const maskCache: Record<string, Mask> = {};
const collagePose: Record<string, number> = {};

export function slugify(sci: string): string {
  return sci.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
}

function loadMask(slug: string): Mask | null {
  if (maskCache[slug]) {
    return maskCache[slug];
  }
  const rec = MASKS[slug];
  if (!rec) {
    return null;
  }
  const bytes = atob(rec.bits);
  const { w, h } = rec;
  const cells: Array<[number, number]> = [];
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const i = y * w + x;
      const b = bytes.charCodeAt(i >> 3);
      if ((b >> (7 - (i & 7))) & 1) {
        cells.push([x, y]);
      }
    }
  }
  maskCache[slug] = { w, h, cells };
  return maskCache[slug];
}

function tuning(n: number) {
  return {
    packingBudgetFrac: n <= 4 ? 0.46 : n <= 12 ? 0.4 : n <= 24 ? 0.34 : 0.28,
    countExp: 0.65,
    minTileAreaFrac: n <= 8 ? 0.01 : n <= 20 ? 0.0075 : 0.0055,
    ellipseAspectBias: 2.1,
  };
}

function maskPack(tiles: Tile[], W: number, H: number, xBias: number, yBias: number, pad: number): Tile[] {
  const GW = Math.ceil(W / GRID_STRIDE) + 2;
  const GH = Math.ceil(H / GRID_STRIDE) + 2;
  const grid = new Uint8Array(GW * GH);

  function cellRange(tile: Tile, tx: number, ty: number, c: [number, number]): [number, number, number, number] {
    const sx = tile.fullW / tile.mask.w;
    const sy = tile.fullH / tile.mask.h;
    let x0 = ((tx + c[0] * sx) / GRID_STRIDE) | 0;
    let y0 = ((ty + c[1] * sy) / GRID_STRIDE) | 0;
    let x1 = ((tx + (c[0] + 1) * sx) / GRID_STRIDE) | 0;
    let y1 = ((ty + (c[1] + 1) * sy) / GRID_STRIDE) | 0;
    if (x0 < 0) x0 = 0;
    if (y0 < 0) y0 = 0;
    if (x1 >= GW) x1 = GW - 1;
    if (y1 >= GH) y1 = GH - 1;
    return [x0, y0, x1, y1];
  }
  function collides(tile: Tile, tx: number, ty: number): boolean {
    const cells = tile.mask.cells;
    for (let i = 0; i < cells.length; i++) {
      const r = cellRange(tile, tx, ty, cells[i]);
      for (let gy = r[1]; gy <= r[3]; gy++) {
        const off = gy * GW;
        for (let gx = r[0]; gx <= r[2]; gx++) {
          if (grid[off + gx]) return true;
        }
      }
    }
    return false;
  }
  function stamp(tile: Tile, tx: number, ty: number): void {
    const cells = tile.mask.cells;
    for (let i = 0; i < cells.length; i++) {
      const r = cellRange(tile, tx, ty, cells[i]);
      let gy0 = r[1] - pad;
      let gy1 = r[3] + pad;
      let gx0 = r[0] - pad;
      let gx1 = r[2] + pad;
      if (gy0 < 0) gy0 = 0;
      if (gx0 < 0) gx0 = 0;
      if (gy1 >= GH) gy1 = GH - 1;
      if (gx1 >= GW) gx1 = GW - 1;
      for (let gy = gy0; gy <= gy1; gy++) {
        const off = gy * GW;
        for (let gx = gx0; gx <= gx1; gx++) grid[off + gx] = 1;
      }
    }
  }
  function offGrid(tile: Tile, tx: number, ty: number): boolean {
    return tx < 0 || ty < 0 || tx + tile.fullW > W || ty + tile.fullH > H;
  }

  const cx = W / 2;
  const cy = H / 2;
  tiles.sort((a, b) => b.fullW * b.fullH - a.fullW * a.fullH);
  const placed: Tile[] = [];
  let seed = 0x9e3779b9;
  const rand = (): number => {
    seed = (seed * 16807) % 2147483647;
    return seed / 2147483647;
  };

  for (let i = 0; i < tiles.length; i++) {
    const t = tiles[i];
    if (i === 0) {
      t.x = cx - t.fullW / 2;
      t.y = cy - t.fullH / 2;
      stamp(t, t.x, t.y);
      placed.push(t);
      continue;
    }
    let comX = 0;
    let comY = 0;
    let comW = 0;
    placed.forEach((p) => {
      const a = p.fullW * p.fullH;
      comX += (p.x + p.fullW / 2) * a;
      comY += (p.y + p.fullH / 2) * a;
      comW += a;
    });
    comX /= comW;
    comY /= comW;

    let best: { x: number; y: number } | null = null;
    let bestCost = Infinity;
    const step = Math.max(GRID_STRIDE, Math.min(t.fullW, t.fullH) * 0.05);
    const maxR = Math.max(W, H);
    let foundRing = -1;
    const phase = rand() * Math.PI * 2;
    for (let r = 0; r <= maxR; r += step) {
      if (foundRing >= 0 && r > foundRing + step * 2) break;
      const samples = Math.max(36, Math.floor(r / 1.6));
      for (let k = 0; k < samples; k++) {
        const theta = phase + (k / samples) * Math.PI * 2;
        const px = cx + r * xBias * Math.cos(theta) - t.fullW / 2;
        const py = cy + r * yBias * Math.sin(theta) - t.fullH / 2;
        if (offGrid(t, px, py)) continue;
        if (collides(t, px, py)) continue;
        const dxx = px + t.fullW / 2 - comX;
        const dyy = py + t.fullH / 2 - comY;
        const cost = Math.hypot(dxx / xBias, dyy / yBias) + rand() * step * 0.5;
        if (cost < bestCost) {
          bestCost = cost;
          best = { x: px, y: py };
        }
      }
      if (best && foundRing < 0) foundRing = r;
    }
    if (best) {
      t.x = best.x;
      t.y = best.y;
      stamp(t, best.x, best.y);
      placed.push(t);
    } else {
      t.x = -99999;
      t.y = -99999;
      placed.push(t);
    }
  }
  return placed;
}

export function layoutCollage(items: RecentSpecies[], W: number, H: number): Tile[] {
  const T = tuning(items.length);
  const vpArea = W * H;
  const budget = vpArea * T.packingBudgetFrac;
  const minArea = vpArea * T.minTileAreaFrac;

  const tiles: Tile[] = [];
  for (const s of items) {
    const base = slugify(s.sci);
    let pose = collagePose[s.sci];
    if (pose === undefined) {
      pose = DIMS[base + '-2'] && Math.random() < FLY_PROB ? 2 : 1;
      collagePose[s.sci] = pose;
    }
    let slug = pose === 2 ? base + '-2' : base;
    let mask = loadMask(slug);
    if (!mask && pose === 2) {
      pose = 1;
      slug = base;
      mask = loadMask(slug);
      collagePose[s.sci] = 1;
    }
    if (!mask) {
      continue;
    }
    const d = DIMS[slug];
    let n = Number(s.n);
    if (!n || isNaN(n)) n = 1;
    tiles.push({
      mask,
      data: s,
      pose,
      ar: d ? d[0] / d[1] : 1.4,
      score: Math.pow(Math.max(1, n), T.countExp),
      area: 0,
      fullW: 0,
      fullH: 0,
      x: 0,
      y: 0,
    });
  }

  const present: Record<string, number> = {};
  items.forEach((s) => (present[s.sci] = 1));
  Object.keys(collagePose).forEach((k) => {
    if (!present[k]) delete collagePose[k];
  });

  const sumScore = tiles.reduce((a, t) => a + t.score, 0) || 1;
  tiles.forEach((t) => {
    t.area = Math.max(minArea, (budget * t.score) / sumScore);
  });
  const sumA = tiles.reduce((a, t) => a + t.area, 0);
  if (sumA > budget) {
    const fixedSum = tiles.filter((t) => t.area <= minArea + 1e-9).reduce((a, t) => a + t.area, 0);
    const flexSum = sumA - fixedSum;
    const flexBudget = Math.max(0, budget - fixedSum);
    const shrink = flexSum > 0 ? Math.min(1, flexBudget / flexSum) : 1;
    tiles.forEach((t) => {
      if (t.area > minArea + 1e-9) t.area *= shrink;
    });
  }
  tiles.forEach((t) => {
    t.fullW = Math.sqrt(t.area * t.ar);
    t.fullH = t.fullW / t.ar;
  });

  const narrow = W <= 700;
  const xBias = narrow ? 1 : T.ellipseAspectBias;
  const yBias = narrow ? 1.7 : 1;
  const pad = narrow ? Math.max(1, COLLAGE_PAD - 1) : COLLAGE_PAD;
  let placed = maskPack(tiles, W, H, xBias, yBias, pad);

  const clusterBounds = (arr: Tile[]) => {
    let L = Infinity;
    let R = -Infinity;
    let T2 = Infinity;
    let B = -Infinity;
    arr.forEach((t) => {
      if (t.x < -1000) return;
      if (t.x < L) L = t.x;
      if (t.x + t.fullW > R) R = t.x + t.fullW;
      if (t.y < T2) T2 = t.y;
      if (t.y + t.fullH > B) B = t.y + t.fullH;
    });
    return { L, R, T: T2, B };
  };
  let b = clusterBounds(placed);
  for (let iter = 0; iter < 10; iter++) {
    const missing = placed.some((t) => t.x < -1000);
    const overflow = b.L < 0 || b.T < 0 || b.R > W || b.B > H;
    if (!missing && !overflow) break;
    let scale = 0.93;
    if (overflow) {
      const clW = b.R - b.L;
      const clH = b.B - b.T;
      const sx = (W * 0.96) / Math.max(clW, W * 0.96);
      const sy = (H * 0.94) / Math.max(clH, H * 0.94);
      scale = Math.min(scale, sx, sy);
    }
    tiles.forEach((t) => {
      t.fullW *= scale;
      t.fullH *= scale;
    });
    placed = maskPack(tiles, W, H, xBias, yBias, pad);
    b = clusterBounds(placed);
  }

  const dx = W / 2 - (b.L + b.R) / 2;
  const dy = H / 2 - (b.T + b.B) / 2;
  if (Math.abs(dx) > 1 || Math.abs(dy) > 1) {
    placed.forEach((t) => {
      if (t.x > -1000) {
        t.x += dx;
        t.y += dy;
      }
    });
  }

  return placed;
}
