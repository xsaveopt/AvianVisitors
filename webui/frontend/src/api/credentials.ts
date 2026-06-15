const STORAGE_KEY = 'av:auth';

let creds: string | null = readStored();

function readStored(): string | null {
  try {
    return sessionStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function getCredentials(): string | null {
  return creds;
}

export function setCredentials(value: string | null): void {
  creds = value;
  try {
    if (value) {
      sessionStorage.setItem(STORAGE_KEY, value);
    } else {
      sessionStorage.removeItem(STORAGE_KEY);
    }
  } catch {
    creds = value;
  }
}

export function encodeBasic(user: string, pass: string): string {
  return btoa(`${user}:${pass}`);
}

export function authHeaders(): Record<string, string> {
  return creds ? { Authorization: `Basic ${creds}` } : {};
}
