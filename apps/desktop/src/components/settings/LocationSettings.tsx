import React from 'react';
import { NearbyPlacesPanel } from '../intelligence/NearbyPlacesPanel';
import { useLocationAwareness } from '../../context/LocationProvider';
import { ago, permissionLabel } from '../../services/earthLocation';
import { LocationMode } from '../../types/intelligence';
import './LocationSettings.css';

const MODES: { id: LocationMode; label: string; hint: string }[] = [
  { id: 'off', label: 'Off', hint: 'No location is read, and the stored position is cleared.' },
  { id: 'once', label: 'Once', hint: 'One reading when you open Earth or ask for it. Nothing runs in the background.' },
  {
    id: 'continuous',
    label: 'Continuous',
    hint: 'A background worker reads your position while W.E.D.N.E.S.D.A.Y. is running, and resumes when it next starts. It stops when the app closes.',
  },
];

const INTERVALS = [
  { seconds: 30, label: 'Every 30 seconds' },
  { seconds: 60, label: 'Every minute' },
  { seconds: 300, label: 'Every 5 minutes' },
  { seconds: 900, label: 'Every 15 minutes' },
];

/** Location modes and privacy controls. Tracking is on only if chosen here. */
export const LocationSettings: React.FC = () => {
  const { status, view, busy, error, setMode, pause, resume, stop, clear, locateOnce } = useLocationAwareness();
  const mode = status?.mode ?? 'once';
  const fix = status?.latest_fix;
  const interval = status?.update_interval_s ?? 60;

  return (
    <div className="loc-settings">
      <div className="loc-modes" role="radiogroup" aria-label="Location mode">
        {MODES.map((m) => (
          <button
            key={m.id}
            type="button"
            role="radio"
            aria-checked={mode === m.id}
            className="loc-mode"
            disabled={busy || !status}
            onClick={() => mode !== m.id && setMode(m.id, m.id === 'continuous' ? interval : undefined)}
          >
            <span className="loc-mode__label">{m.label}</span>
            <span className="loc-mode__hint">{m.hint}</span>
          </button>
        ))}
      </div>

      {error && (
        <div className="notice notice--warn" role="alert">
          {error}
        </div>
      )}

      <dl className="loc-facts" aria-live="polite">
        <div>
          <dt>Status</dt>
          <dd>{view.label}</dd>
        </div>
        <div>
          <dt>Windows permission</dt>
          <dd>{permissionLabel(status)}</dd>
        </div>
        <div>
          <dt>Last known position</dt>
          <dd className="mono">
            {view.position
              ? `${view.position.latitude.toFixed(4)}, ${view.position.longitude.toFixed(4)}${fix?.accuracy_m ? ` (±${Math.round(fix.accuracy_m)} m)` : ''}`
              : 'None'}
          </dd>
        </div>
        <div>
          <dt>Last successful update</dt>
          <dd>{view.position ? ago(fix?.timestamp_utc) : 'None'}</dd>
        </div>
        <div>
          <dt>Update frequency</dt>
          <dd>
            {mode === 'continuous' ? (
              <select
                className="field"
                aria-label="Update frequency"
                value={interval}
                disabled={busy}
                onChange={(e) => setMode('continuous', Number(e.target.value))}
              >
                {INTERVALS.some((i) => i.seconds === interval) ? null : <option value={interval}>Every {interval} seconds</option>}
                {INTERVALS.map((i) => (
                  <option key={i.seconds} value={i.seconds}>
                    {i.label}
                  </option>
                ))}
              </select>
            ) : (
              'Not tracking'
            )}
          </dd>
        </div>
      </dl>
      {mode === 'continuous' && (
        <p className="loc-note">Polling slows while you stay in one place, but never so far that the position goes stale.</p>
      )}

      <div className="loc-actions">
        {mode === 'continuous' &&
          (status?.is_paused ? (
            <button type="button" className="btn" disabled={busy} onClick={resume}>
              Resume
            </button>
          ) : (
            <button type="button" className="btn" disabled={busy} onClick={pause}>
              Pause
            </button>
          ))}
        {mode === 'continuous' && (
          <button type="button" className="btn btn--danger" disabled={busy} onClick={stop}>
            Stop tracking
          </button>
        )}
        {mode !== 'off' && (
          <button type="button" className="btn" disabled={busy} onClick={locateOnce}>
            Read location now
          </button>
        )}
        <button type="button" className="btn btn--ghost" disabled={busy || !fix} onClick={clear}>
          Clear stored position
        </button>
      </div>
      <p className="loc-note">
        Only your latest position is kept, on this computer. There is no location history. Your position leaves this computer only
        when you use a feature that needs it, such as nearby places, or when Earth loads map images for that area.
      </p>

      <NearbyPlacesPanel deviceLocation={fix ?? null} />
    </div>
  );
};
