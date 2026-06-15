import { defineStore } from 'pinia';
import { ref } from 'vue';
import { api, login as apiLogin, probeAuth } from '@/api/client';
import { encodeBasic, getCredentials, setCredentials } from '@/api/credentials';
import type { MenuItem } from '@/api/types';

export const useAuthStore = defineStore('auth', () => {
  const authed = ref(false);
  const required = ref(false);
  const menu = ref<MenuItem[]>([]);

  async function probe(): Promise<void> {
    const state = await probeAuth();
    if (state === 'authed') {
      authed.value = true;
      required.value = false;
      await loadMenu();
      return;
    }
    if (state === 'required') {
      required.value = true;
      if (getCredentials()) {
        setCredentials(null);
      }
      authed.value = false;
    }
  }

  async function login(user: string, pass: string): Promise<boolean> {
    const creds = encodeBasic(user, pass);
    const ok = await apiLogin(creds);
    if (!ok) {
      return false;
    }
    setCredentials(creds);
    authed.value = true;
    required.value = false;
    await loadMenu();
    return true;
  }

  async function loadMenu(): Promise<void> {
    try {
      menu.value = (await api.menu()).items;
    } catch {
      menu.value = [];
    }
  }

  function logout(): void {
    setCredentials(null);
    authed.value = false;
    menu.value = [];
  }

  return { authed, required, menu, probe, login, logout };
});
