import type { DeviceLocationFix, LocationServiceStatus } from '../types/intelligence';

const APPROXIMATE_ABOVE_M = 5000;

export type LocationKind =
  | 'off'
  | 'not_read'
  | 'current'
  | 'last_known'
  | 'tracking'
  | 'no_fresh_fix'
  | 'paused'
  | 'stopped'
  | 'denied'
  | 'unavailable';

export interface LocationView {
  kind: LocationKind;
  /** Short status for the top bar and Earth. Never claims more than the data shows. */
  label: string;
  /** Coordinates to show, or null when there is nothing honest to show. */
  position: { latitude: number; longitude: number } | null;
  fresh: boolean;
  approximate: boolean;
  /** A location worker is meant to be running, so stop controls stay on screen. */
  monitoring: boolean;
}

/** A fix with real coordinates, or null. A failed or empty fix never yields a position. */
export function usableFix(fix: DeviceLocationFix | null | undefined): DeviceLocationFix | null {
  if (!fix) return null;
  const { latitude, longitude } = fix;
  if (typeof latitude !== 'number' || !Number.isFinite(latitude) || Math.abs(latitude) > 90) return null;
  if (typeof longitude !== 'number' || !Number.isFinite(longitude) || Math.abs(longitude) > 180) return null;
  return fix;
}

export function ago(iso: string | null | undefined, now = Date.now()): string {
  const then = iso ? Date.parse(iso) : NaN;
  if (Number.isNaN(then)) return 'at an unknown time';
  const s = Math.max(0, Math.round((now - then) / 1000));
  if (s < 60) return 'just now';
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 48) return `${h} h ago`;
  return `${Math.round(h / 24)} d ago`;
}

/** The single source of truth for what the app may say about location. */
export function describeLocation(status: LocationServiceStatus | null, now = Date.now()): LocationView {
  const none = { position: null, fresh: false, approximate: false, monitoring: false };
  if (!status) return { ...none, kind: 'unavailable', label: 'Location status unknown' };
  const mode = status.mode ?? (status.tracking_enabled ? 'continuous' : 'once');
  if (mode === 'off') return { ...none, kind: 'off', label: 'Location off' };

  const continuous = mode === 'continuous';
  const monitoring = continuous && status.worker_running && !status.is_paused;
  const fix = status.latest_fix;
  if (fix?.status === 'denied') {
    return { ...none, monitoring, kind: 'denied', label: 'Location permission denied' };
  }
  const usable = usableFix(fix);
  const fresh = !!usable && usable.status === 'fresh' && !usable.is_stale;
  const place = usable
    ? {
        position: { latitude: usable.latitude as number, longitude: usable.longitude as number },
        fresh,
        approximate: (usable.accuracy_m ?? 0) > APPROXIMATE_ABOVE_M,
      }
    : { position: null, fresh: false, approximate: false };
  const when = ago(usable?.timestamp_utc, now);

  if (continuous) {
    if (status.is_paused) {
      return { ...place, fresh: false, monitoring: false, kind: 'paused', label: 'Tracking paused' };
    }
    if (!status.worker_running) {
      return { ...place, fresh: false, monitoring: false, kind: 'stopped', label: 'Tracking stopped' };
    }
    if (fresh) return { ...place, monitoring, kind: 'tracking', label: `Tracking · updated ${when}` };
    if (usable) return { ...place, monitoring, kind: 'no_fresh_fix', label: `No fresh position · last ${when}` };
    return { ...none, monitoring, kind: 'no_fresh_fix', label: 'Tracking · waiting for a position' };
  }

  if (!usable) {
    return fix && fix.status !== 'disabled'
      ? { ...none, kind: 'unavailable', label: 'Location unavailable' }
      : { ...none, kind: 'not_read', label: 'Location not read yet' };
  }
  return fresh
    ? { ...place, monitoring: false, kind: 'current', label: `Location read ${when}` }
    : { ...place, monitoring: false, kind: 'last_known', label: `Last known position · ${when}` };
}

/** Plain-language permission state, for Settings. */
export function permissionLabel(status: LocationServiceStatus | null): string {
  const fix = status?.latest_fix;
  if (!fix) return 'Not checked yet';
  if (fix.status === 'denied') return 'Denied in Windows settings';
  if (usableFix(fix)) return 'Allowed';
  if (fix.status === 'unavailable' || fix.status === 'error') return 'Windows gave no position';
  return 'Not checked yet';
}

const FOCUS_EVENT = 'wednesday:earth-focus';
export interface EarthFocus {
  latitude: number;
  longitude: number;
}
let pendingFocus: EarthFocus | null = null;

/** Ask the Earth screen to fly to a place. Earth may not be open or ready yet, so it's held. */
export function requestEarthFocus(focus: EarthFocus): void {
  pendingFocus = focus;
  window.dispatchEvent(new Event(FOCUS_EVENT));
}

export function takeEarthFocus(): EarthFocus | null {
  const focus = pendingFocus;
  pendingFocus = null;
  return focus;
}

export const EARTH_FOCUS_EVENT = FOCUS_EVENT;
