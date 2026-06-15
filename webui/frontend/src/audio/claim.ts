type Stop = () => void;

let active: Stop | null = null;

export function audioClaim(stop: Stop): void {
  if (active && active !== stop) {
    const prev = active;
    active = null;
    try {
      prev();
    } catch {
      active = null;
    }
  }
  active = stop;
}

export function audioRelease(stop: Stop): void {
  if (active === stop) {
    active = null;
  }
}
