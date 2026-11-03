import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Icon } from '../ui/Icon';
import { useLocationAwareness } from '../../context/LocationProvider';
import { EARTH_FOCUS_EVENT, takeEarthFocus } from '../../services/earthLocation';
import './EarthView.css';

/**
 * The Earth screen: the complete app from apps/gods-eye-view, started by the desktop dev
 * server (see vite.config.ts) and shown here with its full interface.
 * It stays a separate origin, so its keys and Cesium runtime never mix with W.E.D.N.E.S.D.A.Y.'s.
 */
const EARTH_ORIGIN = 'http://localhost:4173';
const EARTH_URL = `${EARTH_ORIGIN}/?embed=1&ui=full`;
const RETRY_MS = 4000;

type Status = 'checking' | 'loading' | 'ready' | 'unreachable';

export const EarthView: React.FC<{ active: boolean; onQuietChange: (quiet: boolean) => void }> = ({ active, onQuietChange }) => {
  const [status, setStatus] = useState<Status>('checking');
  const [attempts, setAttempts] = useState(0);
  const mounted = useRef(true);
  const frame = useRef<HTMLIFrameElement>(null);
  const { view, status: locationStatus, locateOnce } = useLocationAwareness();
  const [frameReady, setFrameReady] = useState(false);
  const askedOnce = useRef(false);

  const probe = useCallback(async () => {
    try {
      // Opaque response: this only shows that the Earth server answers.
      await fetch(`${EARTH_ORIGIN}/`, { mode: 'no-cors', cache: 'no-store', signal: AbortSignal.timeout(3000) });
      if (mounted.current) setStatus((s) => (s === 'ready' ? s : 'loading'));
    } catch {
      if (mounted.current) {
        setStatus('unreachable');
        setAttempts((n) => n + 1);
      }
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    probe();
    return () => {
      mounted.current = false;
    };
  }, [probe]);

  // The server can take a few seconds to start with the app; keep trying until it answers.
  useEffect(() => {
    if (status !== 'unreachable') return;
    const t = window.setTimeout(probe, RETRY_MS);
    return () => window.clearTimeout(t);
  }, [status, attempts, probe]);

  const send = useCallback((message: Record<string, unknown>) => {
    frame.current?.contentWindow?.postMessage(message, EARTH_ORIGIN);
  }, []);

  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      if (event.origin !== EARTH_ORIGIN || event.source !== frame.current?.contentWindow) return;
      if (event.data?.type === 'gev:ready') setFrameReady(true);
      else if (event.data?.type === 'wednesday:locate-request') void locateOnce();
      else if (event.data?.type === 'wednesday:quiet') onQuietChange(event.data.quiet === true);
    };
    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, [locateOnce, onQuietChange]);

  // A hidden frame looks visible from inside, so tell Earth to rest while another screen is open.
  useEffect(() => {
    if (frameReady) send({ type: 'wednesday:visibility', visible: active });
    if (!active) onQuietChange(false);
  }, [frameReady, active, send, onQuietChange]);

  // In Once mode, opening Earth is the moment a reading is needed. Off reads nothing.
  useEffect(() => {
    if (!frameReady || askedOnce.current || !locationStatus) return;
    askedOnce.current = true;
    if (locationStatus.mode !== 'off' && locationStatus.mode !== 'continuous' && !view.fresh) void locateOnce();
  }, [frameReady, locationStatus, view.fresh, locateOnce]);

  // Coordinates go by message to Earth's origin only, never in a URL.
  const { position, fresh, approximate, label } = view;
  useEffect(() => {
    if (!frameReady) return;
    send({
      type: 'wednesday:location',
      latitude: position?.latitude ?? null,
      longitude: position?.longitude ?? null,
      fresh,
      approximate,
      label,
    });
  }, [frameReady, send, position?.latitude, position?.longitude, fresh, approximate, label]);

  // "Show on Earth" from another screen waits here until Earth can take it.
  useEffect(() => {
    if (!frameReady) return;
    const flush = () => {
      const focus = takeEarthFocus();
      if (focus) send({ type: 'wednesday:focus', latitude: focus.latitude, longitude: focus.longitude, fresh: true });
    };
    flush();
    window.addEventListener(EARTH_FOCUS_EVENT, flush);
    return () => window.removeEventListener(EARTH_FOCUS_EVENT, flush);
  }, [frameReady, send]);

  if (status === 'unreachable') {
    return (
      <div className="earth-host earth-host--message">
        {attempts < 8 ? (
          <div className="earth-host__status" role="status">
            <span className="spinner" /> Starting Earth…
          </div>
        ) : (
          <div className="notice notice--warn earth-host__notice" role="alert">
            <Icon name="alert" size={15} />
            <div>
              <strong>Earth isn’t running.</strong> It starts with the desktop dev server. Restart{' '}
              <code>npm --prefix apps/desktop run dev</code> and check its output. This screen connects by itself once it’s up.
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="earth-host">
      {status !== 'ready' && (
        <div className="earth-host__status earth-host__status--over" role="status">
          <span className="spinner" /> Loading Earth…
        </div>
      )}
      {status !== 'checking' && (
        <iframe
          ref={frame}
          className="earth-host__frame"
          src={EARTH_URL}
          title="Earth: interactive 3D globe with live world data"
          allow="fullscreen; clipboard-write; microphone; geolocation"
          onLoad={() => setStatus('ready')}
        />
      )}
    </div>
  );
};
