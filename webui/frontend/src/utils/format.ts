export const EBIRD_CODES: Record<string, string> = {
  'Calypte anna': 'annhum',
  'Passer domesticus': 'houspa',
  'Haemorhous mexicanus': 'houfin',
  'Turdus migratorius': 'amerob',
  'Zenaida macroura': 'moudov',
  'Spinus psaltria': 'lesgol',
  'Zonotrichia leucophrys': 'whcspa',
  'Aphelocoma californica': 'cascj1',
  'Mimus polyglottos': 'normoc',
  'Sayornis nigricans': 'blkpho',
  'Larus occidentalis': 'wegull',
  'Corvus brachyrhynchos': 'amecro',
};

export function fmtN(n: number | null | undefined): string {
  if (n == null) {
    return '-';
  }
  if (n >= 10000) {
    return (n / 1000).toFixed(1) + 'k';
  }
  return n.toLocaleString();
}

export function pad(n: number): string {
  return n < 10 ? '0' + n : '' + n;
}

export function windowLabel(h: number): string {
  if (h <= 1) {
    return 'this hour';
  }
  if (h <= 12) {
    return 'past 12h';
  }
  if (h <= 24) {
    return 'today';
  }
  if (h <= 168) {
    return 'this week';
  }
  return 'all time';
}

export function wikiUrl(sci: string): string {
  return 'https://en.wikipedia.org/wiki/' + encodeURIComponent(sci.replace(/ /g, '_'));
}

export function ebirdUrl(sci: string): string {
  const code = EBIRD_CODES[sci];
  return code ? 'https://ebird.org/species/' + code : 'https://ebird.org/explore';
}

export function fmtRecTime(d: string, t: string): string {
  if (!d) {
    return '-';
  }
  const date = new Date((d || '') + 'T' + (t || '00:00:00'));
  if (isNaN(date.getTime())) {
    return d + ' ' + (t || '');
  }
  const ago = Math.floor((Date.now() - date.getTime()) / 1000);
  if (ago < 60) {
    return ago + 's ago';
  }
  if (ago < 3600) {
    return Math.floor(ago / 60) + 'm ago';
  }
  if (ago < 86400) {
    return Math.floor(ago / 3600) + 'h ago';
  }
  return Math.floor(ago / 86400) + 'd ago';
}

export function fmtDateLine(d: string, t: string): string {
  if (!d) {
    return '';
  }
  const date = new Date(d + 'T' + (t || '00:00:00'));
  if (isNaN(date.getTime())) {
    return d + ' ' + (t || '');
  }
  return (
    date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) +
    ' · ' +
    (t ? t.slice(0, 5) : '')
  );
}

export function rarityLabel(total: number, firstSeenIso: string | null | undefined): string {
  if (!total) {
    return '-';
  }
  let days = 1;
  if (firstSeenIso) {
    const t = Date.parse(firstSeenIso.replace(' ', 'T'));
    if (!isNaN(t)) {
      days = Math.max(1, Math.ceil((Date.now() - t) / 86400000));
    }
  }
  const perDay = total / days;
  if (perDay >= 5) {
    return 'common';
  }
  if (perDay >= 1) {
    return 'regular';
  }
  if (perDay >= 0.2) {
    return 'occasional';
  }
  return 'rare';
}
