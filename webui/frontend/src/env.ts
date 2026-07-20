const win =
  typeof window !== 'undefined'
    ? (window as unknown as { __AV_BASE__?: string })
    : undefined;

export const BASE_PATH = (win?.__AV_BASE__ ?? '').replace(/\/+$/, '');
