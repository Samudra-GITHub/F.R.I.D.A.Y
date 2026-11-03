import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { describeLocation, LocationView } from '../services/earthLocation';
import { LocationMode, LocationServiceStatus } from '../types/intelligence';
import { useApp } from './AppProvider';

const POLL_TRACKING_MS = 15000;
const POLL_IDLE_MS = 60000;
const FIRST_READING_MS = 3000;

interface LocationContextValue {
  status: LocationServiceStatus | null;
  view: LocationView;
  busy: boolean;
  error: string | null;
  setMode: (mode: LocationMode, intervalSeconds?: number) => Promise<void>;
  pause: () => Promise<void>;
  resume: () => Promise<void>;
  stop: () => Promise<void>;
  clear: () => Promise<void>;
  /** Ask Windows for one reading. Does nothing while location is off. */
  locateOnce: () => Promise<void>;
}

const noop = async () => {};
/** Before the provider mounts, the app knows nothing and so claims nothing. */
const UNKNOWN: LocationContextValue = {
  status: null,
  view: describeLocation(null),
  busy: false,
  error: null,
  setMode: noop,
  pause: noop,
  resume: noop,
  stop: noop,
  clear: noop,
  locateOnce: noop,
};

const LocationContext = createContext<LocationContextValue>(UNKNOWN);

/** Reads only the service's status here; the device itself is read by an explicit action or the opted-in worker. */
export const LocationProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { logEvent } = useApp();
  const [status, setStatus] = useState<LocationServiceStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const modeRef = useRef<LocationMode | undefined>();
  modeRef.current = status?.mode;

  const load = useCallback(async () => {
    try {
      const res = await fetch('/api/location/status');
      if (res.ok) setStatus(await res.json());
    } catch {
      /* backend offline: the status simply stops updating */
    }
    setNow(Date.now());
  }, []);

  const tracking = status?.mode === 'continuous' && !status.is_paused;
  useEffect(() => {
    load();
    const t = window.setInterval(() => {
      if (document.visibilityState === 'visible') load();
    }, tracking ? POLL_TRACKING_MS : POLL_IDLE_MS);
    return () => window.clearInterval(t);
  }, [load, tracking]);

  const act = useCallback(
    async (title: string, path: string, body?: unknown) => {
      setBusy(true);
      setError(null);
      try {
        const res = await fetch(`/api/location/${path}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: body === undefined ? undefined : JSON.stringify(body),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const next = await res.json();
        // poll-once answers with the fix alone, so read the whole status back.
        if (path === 'poll-once') await load();
        else setStatus(next);
        setNow(Date.now());
        // A worker just started takes a moment to report its first reading.
        if (next.mode === 'continuous') window.setTimeout(load, FIRST_READING_MS);
        logEvent({ kind: 'location', title, outcome: 'ok' });
      } catch (err) {
        setError(`${title} failed. Check that the backend is running.`);
        logEvent({ kind: 'location', title: `${title} failed`, details: String(err), outcome: 'failed' });
      } finally {
        setBusy(false);
      }
    },
    [load, logEvent]
  );

  const value = useMemo<LocationContextValue>(
    () => ({
      status,
      view: describeLocation(status, now),
      busy,
      error,
      setMode: (mode, intervalSeconds) =>
        act(`Location mode: ${mode}`, 'mode', intervalSeconds ? { mode, interval_s: intervalSeconds } : { mode }),
      pause: () => act('Location tracking paused', 'pause'),
      resume: () => act('Location tracking resumed', 'resume'),
      stop: () => act('Location turned off', 'mode', { mode: 'off' }),
      clear: () => act('Stored position cleared', 'clear'),
      locateOnce: async () => {
        if (modeRef.current === 'off') return;
        await act('Location read once', 'poll-once');
      },
    }),
    [status, now, busy, error, act]
  );

  return <LocationContext.Provider value={value}>{children}</LocationContext.Provider>;
};

export function useLocationAwareness(): LocationContextValue {
  return useContext(LocationContext);
}
