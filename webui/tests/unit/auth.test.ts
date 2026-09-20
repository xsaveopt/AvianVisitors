import { createPinia, setActivePinia } from 'pinia';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const probeAuth = vi.fn<() => Promise<'authed' | 'required' | 'offline'>>();
const apiLogin = vi.fn<(creds: string) => Promise<boolean>>();
const menu = vi.fn<() => Promise<{ items: unknown[] }>>();

vi.mock('@/api/client', () => ({
  api: { menu: () => menu() },
  login: (creds: string) => apiLogin(creds),
  probeAuth: () => probeAuth(),
}));

let stored: string | null = null;

vi.mock('@/api/credentials', () => ({
  getCredentials: () => stored,
  setCredentials: (value: string | null) => {
    stored = value;
  },
  encodeBasic: (user: string, pass: string) => `${user}:${pass}`,
}));

const { useAuthStore } = await import('@/stores/auth');

beforeEach(() => {
  setActivePinia(createPinia());
  stored = null;
  probeAuth.mockReset();
  apiLogin.mockReset();
  menu.mockReset();
  menu.mockResolvedValue({ items: [{ label: 'Logs' }] });
});

describe('probe', () => {
  it('starts unauthenticated with an empty menu', () => {
    const store = useAuthStore();
    expect(store.authed).toBe(false);
    expect(store.required).toBe(false);
    expect(store.menu).toEqual([]);
  });

  it('authed loads the menu and clears the requirement', async () => {
    probeAuth.mockResolvedValue('authed');
    const store = useAuthStore();
    store.required = true;
    await store.probe();
    expect(store.authed).toBe(true);
    expect(store.required).toBe(false);
    expect(store.menu).toEqual([{ label: 'Logs' }]);
  });

  it('required drops stale credentials', async () => {
    stored = 'stale';
    probeAuth.mockResolvedValue('required');
    const store = useAuthStore();
    await store.probe();
    expect(stored).toBeNull();
    expect(store.required).toBe(true);
    expect(store.authed).toBe(false);
    expect(menu).not.toHaveBeenCalled();
  });

  it('offline leaves every flag alone', async () => {
    probeAuth.mockResolvedValue('offline');
    const store = useAuthStore();
    await store.probe();
    expect(store.authed).toBe(false);
    expect(store.required).toBe(false);
    expect(menu).not.toHaveBeenCalled();
  });

  it('a failing menu leaves the session authenticated', async () => {
    probeAuth.mockResolvedValue('authed');
    menu.mockRejectedValue(new Error('500'));
    const store = useAuthStore();
    await store.probe();
    expect(store.authed).toBe(true);
    expect(store.menu).toEqual([]);
  });
});

describe('login', () => {
  it('stores the encoded credentials on success', async () => {
    apiLogin.mockResolvedValue(true);
    const store = useAuthStore();
    store.required = true;
    await expect(store.login('admin', 'hunter2')).resolves.toBe(true);
    expect(apiLogin).toHaveBeenCalledWith('admin:hunter2');
    expect(stored).toBe('admin:hunter2');
    expect(store.authed).toBe(true);
    expect(store.required).toBe(false);
    expect(store.menu).toEqual([{ label: 'Logs' }]);
  });

  it('stores nothing on a rejected password', async () => {
    apiLogin.mockResolvedValue(false);
    const store = useAuthStore();
    await expect(store.login('admin', 'wrong')).resolves.toBe(false);
    expect(stored).toBeNull();
    expect(store.authed).toBe(false);
    expect(menu).not.toHaveBeenCalled();
  });
});

describe('logout', () => {
  it('clears credentials, the flag and the menu', async () => {
    apiLogin.mockResolvedValue(true);
    const store = useAuthStore();
    await store.login('admin', 'hunter2');
    store.logout();
    expect(stored).toBeNull();
    expect(store.authed).toBe(false);
    expect(store.menu).toEqual([]);
  });

  it('leaves the required flag untouched', async () => {
    const store = useAuthStore();
    store.required = true;
    store.logout();
    expect(store.required).toBe(true);
  });
});
