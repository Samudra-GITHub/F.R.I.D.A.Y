import React, { useEffect, useState } from 'react';
import { Icon } from '../ui/Icon';
import { EarthRecord, queueEarthActions } from '../../services/earthActions';
import { ago } from '../../services/earthLocation';
import { useLocationAwareness } from '../../context/LocationProvider';
import './EarthPanels.css';

interface FeedStatus {
  status: string;
  count?: number;
  retrieved_at?: string;
  is_stale?: boolean;
  attribution?: string;
  details?: string | null;
}

/**
 * Orbit: what's moving above the planet. Satellites and aircraft come from the Earth
 * screen's own live feeds; ships need an AISStream key. Nothing here is simulated.
 */
export const OrbitPanel: React.FC = () => {
  const { view } = useLocationAwareness();
  const [sats, setSats] = useState<FeedStatus | null>(null);
  const [near, setNear] = useState<{ state: 'idle' | 'loading' | 'done' | 'error'; text?: string }>({ state: 'idle' });

  useEffect(() => {
    queueEarthActions(
      [
        { type: 'set_layer', layer: 'satellites', enabled: true },
        { type: 'set_layer', layer: 'flights', enabled: true },
      ],
      'Orbit'
    );
    fetch('/api/world/satellites?limit=1')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setSats(d ?? { status: 'unavailable' }))
      .catch(() => setSats({ status: 'unavailable' }));
  }, []);

  const aircraftNearMe = async () => {
    if (!view.position) return;
    setNear({ state: 'loading' });
    try {
      const { latitude, longitude } = view.position;
      const res = await fetch(`/api/world/flights?lat=${latitude.toFixed(2)}&lng=${longitude.toFixed(2)}&radius_nm=150`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const records: EarthRecord[] = (data.flights ?? []).slice(0, 200).map((f: Record<string, unknown>) => ({
        id: `adsb:${f.hex}`,
        category: 'aircraft',
        latitude: f.latitude,
        longitude: f.longitude,
        title: String(f.callsign || f.registration || f.hex || 'Aircraft').trim(),
        source: 'adsb.lol',
      }));
      queueEarthActions(
        [
          { type: 'show_records', group: 'ask', records },
          { type: 'focus_user' },
        ],
        'Aircraft near you'
      );
      setNear({
        state: 'done',
        text: `${records.length} aircraft within 150 nm, from adsb.lol, retrieved ${data.retrieved_at ? ago(data.retrieved_at) : 'just now'}${data.is_stale ? ' (cached)' : ''}.`,
      });
    } catch {
      setNear({ state: 'error', text: 'The aircraft feed could not be reached.' });
    }
  };

  return (
    <section className="earth-panel earth-panel--orbit" aria-label="Orbit">
      <header className="earth-panel__head">
        <span className="earth-panel__kicker">Orbit</span>
        <span className="earth-panel__hint">Satellites, aircraft and ships, from live public feeds</span>
      </header>

      <div className="orbit__rows">
        <div className="orbit__row">
          <Icon name="sparkle" size={15} />
          <div>
            <div className="orbit__title">Satellites</div>
            <div className="orbit__meta">
              {sats === null
                ? 'Checking…'
                : sats.status === 'unavailable'
                  ? 'Feed unavailable'
                  : `CelesTrak orbits, positions computed with SGP4${sats.retrieved_at ? ` · elements ${ago(sats.retrieved_at)}` : ''}${sats.is_stale ? ' · stale' : ''}`}
            </div>
          </div>
          <button type="button" className="btn btn--sm" onClick={() => queueEarthActions([{ type: 'select_satellite', query: 'ISS (ZARYA)' }], 'Follow the ISS')}>
            Follow the ISS
          </button>
        </div>

        <div className="orbit__row">
          <Icon name="send" size={15} />
          <div>
            <div className="orbit__title">Aircraft</div>
            <div className="orbit__meta">
              Live ADS-B positions. Movement between reports is estimated from the last reported speed and track; select one for its 3D model and trail.
            </div>
            {near.text && <div className={`orbit__meta ${near.state === 'error' ? 'orbit__bad' : ''}`}>{near.text}</div>}
          </div>
          <button type="button" className="btn btn--sm" onClick={aircraftNearMe} disabled={!view.position || near.state === 'loading'} title={view.position ? undefined : view.label}>
            {near.state === 'loading' ? <span className="spinner" /> : null} Near me
          </button>
        </div>

        <div className="orbit__row">
          <Icon name="wave" size={15} />
          <div>
            <div className="orbit__title">Ships</div>
            <div className="orbit__meta">
              Needs an AISStream key, entered in POWER UP on this screen. Selected ships then show a 3D model facing their reported heading.
            </div>
          </div>
          <button type="button" className="btn btn--sm" onClick={() => queueEarthActions([{ type: 'set_layer', layer: 'vessels', enabled: true }], 'Ships')}>
            Turn on
          </button>
        </div>
      </div>
    </section>
  );
};
