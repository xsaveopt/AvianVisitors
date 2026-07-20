export interface Stats {
  totals: { detections: number; species: number };
  today: { detections: number; species: number };
  last_hour: { detections: number };
  week: { detections: number; species: number };
  started: string | null;
  as_of: string;
}

export interface LifelistSpecies {
  sci: string;
  com: string;
  first_seen: string;
  last_seen: string;
  n: number;
  best_conf: number;
}

export interface RecentSpecies {
  sci: string;
  com: string;
  n: number;
  best_conf: number;
  last_seen: string;
}

export interface Detection {
  d: string;
  t: string;
  file: string;
  conf: number;
}

export interface SpeciesDetail {
  sci: string;
  summary: {
    com: string;
    total: number;
    first_seen: string;
    last_seen: string;
    best_conf: number;
  } | null;
  detections: Detection[];
}

export interface FirstSeenSpecies {
  sci: string;
  com: string;
  first_seen: string;
  total: number;
}

export interface Timeseries {
  days: number;
  daily: Array<{ date: string; detections: number; species: number }>;
  by_hour: Array<{ hour: number; detections: number }>;
  as_of: string;
}

export interface MenuItem {
  label: string;
  href: string;
  native: boolean;
}

export interface WikiSummary {
  extract: string | null;
  thumbnail: { source: string } | null;
  title: string | null;
}

export interface ConfigMeta {
  type: 'float' | 'int' | 'enum' | 'string';
  min?: number;
  max?: number;
  values?: string[];
  maxlen?: number;
  restart?: boolean;
}

export interface ConfigResponse {
  values: Record<string, number | string>;
  meta: Record<string, ConfigMeta>;
  preserve: boolean;
}

export interface SaveConfigResult {
  ok?: boolean;
  error?: string;
  fields?: Record<string, string>;
  restarted?: Record<string, boolean>;
}

export interface ServiceState {
  active: string;
  enabled: string;
  since: string | null;
}

export interface LogsResponse {
  unit: string;
  lines: number;
  text: string;
  error?: string;
}

export interface RestartResult {
  unit: string;
  ok: boolean;
  rc: number;
  out: string;
}

export interface SystemDiag {
  system: {
    uptime?: { pretty?: string };
    mem?: { used_pct: number; used_bytes: number; total_bytes: number };
    disk_birds?: { used_pct: number };
    temp_c?: number | null;
    birds_db?: { exists: boolean };
    conf?: { values?: Record<string, string> };
    hostname?: string;
  };
  services: Record<string, ServiceState>;
  recent_logs: Record<string, string>;
  as_of: string;
}
