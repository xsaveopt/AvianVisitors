import type { CollageSpecies } from '@/collage/algorithm';

export async function fetchCollage(): Promise<CollageSpecies[]> {
  const res = await fetch('api/collage', { credentials: 'same-origin' });
  if (!res.ok) {
    return [];
  }
  const data = (await res.json()) as { species?: CollageSpecies[] };
  return data.species ?? [];
}

export function collageIllustrationUrl(sci: string): string {
  return `api/collage/illustration?sci=${encodeURIComponent(sci)}`;
}
