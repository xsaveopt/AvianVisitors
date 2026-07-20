import type { CollageSpecies } from '@/collage/algorithm';
import { BASE_PATH } from '@/env';

const API = `${BASE_PATH}/api`;

export async function fetchCollage(): Promise<CollageSpecies[]> {
  const res = await fetch(`${API}/collage`, { credentials: 'same-origin' });
  if (!res.ok) {
    return [];
  }
  const data = (await res.json()) as { species?: CollageSpecies[] };
  return data.species ?? [];
}

export function collageIllustrationUrl(sci: string): string {
  return `${API}/collage/illustration?sci=${encodeURIComponent(sci)}`;
}
