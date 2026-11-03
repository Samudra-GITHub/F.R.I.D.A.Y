import React, { useEffect, useState } from 'react';
import { Icon } from '../ui/Icon';
import { EarthRecord, queueEarthActions } from '../../services/earthActions';
import { ago } from '../../services/earthLocation';
import './EarthPanels.css';

export interface InvestigationPoint {
  latitude: number;
  longitude: number;
  radius_km: number;
}

interface Investigation {
  radius_km: number;
  start: string;
  end: string;
  nearby: EarthRecord[];
  weather: { condition?: string; temperature_c?: number; wind_speed_kmh?: number } | null;
  consulted: { provider: string; count: number }[];
  missing: { provider: string; reason: string }[];
  retrieved_at: string;
}

const KIND: Record<string, string> = {
  earthquake: 'Earthquake',
  event: 'Natural event',
  disaster: 'Disaster alert',
};

/** What happened here? Only records whose own position falls inside the circle. */
export const InvestigatePanel: React.FC<{ point: InvestigationPoint; onClose: () => void }> = ({ point, onClose }) => {
  const [data, setData] = useState<Investigation | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setData(null);
    setError(null);
    const params = new URLSearchParams({
      lat: point.latitude.toFixed(4),
      lon: point.longitude.toFixed(4),
      radius_km: String(point.radius_km),
      days: '7',
    });
    fetch(`/api/world/investigate?${params}`, { signal: controller.signal })
      .then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const d: Investigation = await r.json();
        setData(d);
        queueEarthActions([{ type: 'show_records', group: 'investigate', records: d.nearby.slice(0, 500) }], 'What happened here?');
      })
      .catch((err) => {
        if (!controller.signal.aborted) setError(`The investigation couldn't run: ${err instanceof Error ? err.message : err}`);
      });
    return () => controller.abort();
  }, [point]);

  useEffect(
    () => () => {
      queueEarthActions([{ type: 'show_records', group: 'investigate', records: [] }], 'Investigation closed');
    },
    []
  );

  return (
    <section className="earth-panel earth-panel--investigate" aria-label="What happened here">
      <header className="earth-panel__head">
        <span className="earth-panel__kicker">What happened here?</span>
        <button type="button" className="icon-btn icon-btn--sm" onClick={onClose} aria-label="Close">
          <Icon name="close" size={14} />
        </button>
      </header>
      <p className="investigate__scope mono">
        {point.latitude.toFixed(2)}, {point.longitude.toFixed(2)} · within {point.radius_km} km · past 7 days
      </p>

      {error && (
        <div className="notice notice--warn" role="alert">
          <Icon name="alert" size={14} />
          <div>{error}</div>
        </div>
      )}
      {!data && !error && (
        <div className="earth-panel__loading">
          <span className="spinner" /> Checking the archives
        </div>
      )}

      {data && (
        <>
          {data.weather && (
            <p className="investigate__weather">
              Now at this point: {data.weather.condition}
              {typeof data.weather.temperature_c === 'number' && `, ${Math.round(data.weather.temperature_c)} °C`}
              {typeof data.weather.wind_speed_kmh === 'number' && `, wind ${Math.round(data.weather.wind_speed_kmh)} km/h`}{' '}
              <span className="muted">(Open-Meteo)</span>
            </p>
          )}
          {data.nearby.length === 0 ? (
            <p className="muted small">Nothing on record inside this circle in the past 7 days, from the sources below.</p>
          ) : (
            <ol className="investigate__list">
              {data.nearby.map((r) => (
                <li key={r.id}>
                  <button type="button" className="ask__record" onClick={() => queueEarthActions([{ type: 'select_record', id: r.id }], 'Select record')}>
                    <span className="ask__record-title">{r.title}</span>
                    <span className="ask__record-meta">
                      {KIND[r.category] ?? r.category} · {r.distance_km} km away · {r.time_utc ? ago(r.time_utc) : 'time not given'} · {r.source}
                    </span>
                  </button>
                </li>
              ))}
            </ol>
          )}
          <details className="time__sources">
            <summary>
              Sources · retrieved {ago(data.retrieved_at)}
              {data.missing.length > 0 && ` · ${data.missing.length} missing`}
            </summary>
            <ul>
              {data.consulted.map((c) => (
                <li key={c.provider}>
                  {c.provider}: {c.count}
                </li>
              ))}
              {data.missing.map((m) => (
                <li key={m.provider} className="time__missing">
                  {m.provider}: {m.reason}
                </li>
              ))}
              <li className="muted">Records are listed only when their own coordinates are inside the circle; country-wide or regional reports aren't placed here.</li>
            </ul>
          </details>
        </>
      )}
    </section>
  );
};
