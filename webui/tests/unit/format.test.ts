import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  ebirdUrl,
  fmtDateLine,
  fmtN,
  fmtRecTime,
  pad,
  rarityLabel,
  wikiUrl,
  windowLabel,
} from '@/utils/format';

describe('fmtN', () => {
  it('renders dash for null/undefined', () => {
    expect(fmtN(null)).toBe('-');
    expect(fmtN(undefined)).toBe('-');
  });

  it('passes small numbers through', () => {
    expect(fmtN(0)).toBe('0');
    expect(fmtN(999)).toBe('999');
  });

  it('abbreviates at the 10k threshold', () => {
    expect(fmtN(9999)).not.toContain('k');
    expect(fmtN(10000)).toBe('10.0k');
    expect(fmtN(12345)).toBe('12.3k');
  });
});

describe('pad', () => {
  it('zero-pads single digits only', () => {
    expect(pad(0)).toBe('00');
    expect(pad(9)).toBe('09');
    expect(pad(10)).toBe('10');
    expect(pad(123)).toBe('123');
  });
});

describe('windowLabel', () => {
  it('maps hour buckets to labels', () => {
    expect(windowLabel(0)).toBe('this hour');
    expect(windowLabel(1)).toBe('this hour');
    expect(windowLabel(2)).toBe('past 12h');
    expect(windowLabel(12)).toBe('past 12h');
    expect(windowLabel(13)).toBe('today');
    expect(windowLabel(24)).toBe('today');
    expect(windowLabel(25)).toBe('this week');
    expect(windowLabel(168)).toBe('this week');
    expect(windowLabel(169)).toBe('all time');
  });
});

describe('wikiUrl', () => {
  it('uses underscores and keeps them unencoded', () => {
    expect(wikiUrl('Calypte anna')).toBe('https://en.wikipedia.org/wiki/Calypte_anna');
  });
});

describe('ebirdUrl', () => {
  it('links to the species code when known', () => {
    expect(ebirdUrl('Calypte anna')).toBe('https://ebird.org/species/annhum');
  });

  it('falls back to explore when unknown', () => {
    expect(ebirdUrl('Nonexistent species')).toBe('https://ebird.org/explore');
  });
});

describe('fmtRecTime', () => {
  afterEach(() => vi.useRealTimers());

  it('returns dash without a date', () => {
    expect(fmtRecTime('', '')).toBe('-');
  });

  it('falls back to raw text for invalid dates', () => {
    expect(fmtRecTime('2024-13-99', '25:99:99')).toBe('2024-13-99 25:99:99');
  });

  it('renders relative time', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2024-02-24T16:20:07Z'));
    expect(fmtRecTime('2024-02-24', '16:19:37')).toBe('30s ago');
    expect(fmtRecTime('2024-02-24', '16:10:07')).toBe('10m ago');
    expect(fmtRecTime('2024-02-24', '14:20:07')).toBe('2h ago');
    expect(fmtRecTime('2024-02-22', '16:20:07')).toBe('2d ago');
  });
});

describe('fmtDateLine', () => {
  it('returns empty without a date', () => {
    expect(fmtDateLine('', '')).toBe('');
  });

  it('falls back to raw text for invalid dates', () => {
    expect(fmtDateLine('bogus', '')).toBe('bogus ');
  });

  it('formats date and time', () => {
    const line = fmtDateLine('2024-02-24', '16:19:37');
    expect(line).toContain('24');
    expect(line.endsWith('· 16:19')).toBe(true);
  });
});

describe('rarityLabel', () => {
  afterEach(() => vi.useRealTimers());

  it('returns dash with no detections', () => {
    expect(rarityLabel(0, '2024-01-01')).toBe('-');
  });

  it('buckets by detections per day', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2024-02-24T00:00:00Z'));
    const tenDaysAgo = '2024-02-14';
    expect(rarityLabel(100, tenDaysAgo)).toBe('common');
    expect(rarityLabel(20, tenDaysAgo)).toBe('regular');
    expect(rarityLabel(3, tenDaysAgo)).toBe('occasional');
    expect(rarityLabel(1, tenDaysAgo)).toBe('rare');
  });

  it('treats a missing first-seen as a single day', () => {
    expect(rarityLabel(3, null)).toBe('regular');
    expect(rarityLabel(10, undefined)).toBe('common');
  });
});
