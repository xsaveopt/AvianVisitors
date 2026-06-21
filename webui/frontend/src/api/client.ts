import { authHeaders } from './credentials';
import type {
  ConfigResponse,
  FirstSeenSpecies,
  LifelistSpecies,
  LogsResponse,
  MenuItem,
  RecentSpecies,
  RestartResult,
  SaveConfigResult,
  SpeciesDetail,
  Stats,
  SystemDiag,
  Timeseries,
  WikiSummary,
} from './types';

const BASE = '/api';

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function getJson<T>(path: string, withAuth = false): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    credentials: 'same-origin',
    headers: withAuth ? authHeaders() : {},
  });
  if (!res.ok) {
    throw new ApiError(res.status, `${path} -> ${res.status}`);
  }
  return (await res.json()) as T;
}

export const recordingUrl = (sci: string): string =>
  `${BASE}/recording?sci=${encodeURIComponent(sci)}`;

export const recordingFileUrl = (file: string): string =>
  `${BASE}/recording?file=${encodeURIComponent(file)}`;

export const cutoutUrl = (sci: string, com: string, version: string): string =>
  `${BASE}/illustration?sci=${encodeURIComponent(sci)}` +
  (com ? `&com=${encodeURIComponent(com)}` : '') +
  `&v=${version}`;

export const illustrationPoseUrl = (sci: string, version: string, pose: number): string =>
  `${BASE}/illustration?sci=${encodeURIComponent(sci)}&v=${version}` +
  (pose > 1 ? `&pose=${pose}` : '');

async function postJson<T>(path: string, payload: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return (await res.json()) as T;
}

export const api = {
  stats: () => getJson<Stats>('/stats'),
  lifelist: () => getJson<{ species: LifelistSpecies[] }>('/lifelist'),
  recent: (hours: number) =>
    getJson<{ hours: number; species: RecentSpecies[] }>(`/recent?hours=${hours}`),
  firstseen: (limit: number) => getJson<{ species: FirstSeenSpecies[] }>(`/firstseen?limit=${limit}`),
  timeseries: (days: number) => getJson<Timeseries>(`/timeseries?days=${days}`),
  species: (sci: string) => getJson<SpeciesDetail>(`/species?sci=${encodeURIComponent(sci)}`),
  wiki: (sci: string) => getJson<WikiSummary>(`/wiki?sci=${encodeURIComponent(sci)}`),
  menu: () => getJson<{ items: MenuItem[] }>('/menu', true),
  config: () => getJson<ConfigResponse>('/config', true),
  saveConfig: (payload: Record<string, unknown>) => postJson<SaveConfigResult>('/config', payload),
  theme: () => getJson<{ theme: string }>('/theme'),
  setTheme: (value: string) => postJson<SaveConfigResult>('/config', { THEME: value }),
  status: (action: string) => getJson<SystemDiag>(`/status?action=${action}`, true),
  logs: (unit: string, lines: number) =>
    getJson<LogsResponse>(`/status?action=logs&unit=${encodeURIComponent(unit)}&lines=${lines}`, true),
  restart: (unit: string) =>
    postJson<RestartResult>(`/status?action=restart&unit=${encodeURIComponent(unit)}`, {}),
};

export async function fetchAudioObjectUrl(url: string): Promise<string> {
  const res = await fetch(url, { headers: authHeaders() });
  if (!res.ok) {
    throw new ApiError(res.status, `${url} -> ${res.status}`);
  }
  return URL.createObjectURL(await res.blob());
}

export async function probeAuth(): Promise<'authed' | 'required' | 'offline'> {
  try {
    const res = await fetch(`${BASE}/menu`, {
      credentials: 'same-origin',
      headers: authHeaders(),
      cache: 'no-store',
    });
    return res.status === 200 ? 'authed' : 'required';
  } catch {
    return 'offline';
  }
}

export async function login(creds: string): Promise<boolean> {
  const res = await fetch(`${BASE}/menu`, {
    method: 'POST',
    headers: { Authorization: `Basic ${creds}` },
    credentials: 'same-origin',
  });
  return res.status === 200;
}
