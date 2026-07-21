import type { CollageSpecies } from '@/collage/algorithm';

export interface RecentCapture {
  sci: string;
  com: string;
  ago: number;
}

export async function fetchCollage(): Promise<CollageSpecies[]> {
  const res = await fetch('api/collage', { credentials: 'same-origin' });
  if (!res.ok) {
    return [];
  }
  const data = (await res.json()) as { species?: CollageSpecies[] };
  return data.species ?? [];
}

export async function fetchCollageRecent(): Promise<RecentCapture[]> {
  const res = await fetch('api/collage/recent', { credentials: 'same-origin' });
  if (!res.ok) {
    return [];
  }
  const data = (await res.json()) as { recent?: RecentCapture[] };
  return data.recent ?? [];
}

export function collageIllustrationUrl(sci: string): string {
  return `api/collage/illustration?sci=${encodeURIComponent(sci)}`;
}
