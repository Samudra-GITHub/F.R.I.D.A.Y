import { useSyncExternalStore } from 'react';

/** What the World screen is doing: the live planet, the Time Machine, or Orbit tracking. */
export type EarthMode = 'live' | 'time' | 'orbit';

let mode: EarthMode = 'live';
const listeners = new Set<() => void>();

export function setEarthMode(next: EarthMode): void {
  if (next === mode) return;
  mode = next;
  listeners.forEach((l) => l());
}

export function useEarthMode(): EarthMode {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => mode
  );
}

/** Group a history's records by UTC day, in date order, keeping every day in the range. */
export function recordsByDay<T extends { time_utc?: string }>(records: T[], start: string, end: string): { day: string; records: T[] }[] {
  const days: { day: string; records: T[] }[] = [];
  const index = new Map<string, T[]>();
  const first = Date.parse(`${start}T00:00:00Z`);
  const last = Date.parse(`${end}T00:00:00Z`);
  if (!Number.isFinite(first) || !Number.isFinite(last) || last < first) return days;
  for (let t = first; t <= last; t += 86400000) {
    const day = new Date(t).toISOString().slice(0, 10);
    const list: T[] = [];
    index.set(day, list);
    days.push({ day, records: list });
  }
  for (const r of records) {
    const day = r.time_utc?.slice(0, 10);
    if (day && index.has(day)) index.get(day)!.push(r);
  }
  return days;
}
