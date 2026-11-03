import React, { useCallback, useEffect, useState } from 'react';
import { Icon, IconName } from '../ui/Icon';
import { relativeTime } from '../../utils/relativeTime';
import './Page.css';
import './DiagnosticsView.css';

type ServiceState = 'available' | 'degraded' | 'unavailable' | 'disabled' | 'not_configured' | 'unknown';

interface Diagnostics {
  backend: { state: ServiceState; version: string; bind_host: string; loopback_only: boolean };
  model: {
    state: ServiceState;
    runtime: string;
    base_url: string;
    configured: string;
    installed: boolean | null;
    installed_models: string[];
    request_timeout_s: number;
  };
  voice: {
    stt_state: ServiceState;
    tts_state: ServiceState;
    stt_engine: string;
    tts_engine: string;
    stt_language: string;
    recognizers: string[];
    voices: string[];
    wake_word_active: boolean;
    max_clip_seconds: number;
  };
  location: { provider: string; tracking_enabled: boolean; fix_status: string | null };
  memory: { state: ServiceState; active_records: number | null; path: string };
  world: {
    status: string;
    providers: Record<string, { provider: string; status: string; last_successful_retrieval?: string | null; is_stale: boolean; cached_items_count: number; error_message?: string | null }>;
  };
  config: Record<string, boolean>;
  warnings: { level: 'info' | 'warning' | 'error'; message: string }[];
}

const STATE_LABEL: Record<ServiceState, string> = {
  available: 'Available',
  degraded: 'Degraded',
  unavailable: 'Unavailable',
  disabled: 'Disabled',
  not_configured: 'Not configured',
  unknown: 'Unknown',
};

const providerState = (status: string, stale: boolean): ServiceState =>
  status === 'ok' && !stale ? 'available' : status === 'ok' || status === 'stale' || status === 'empty' ? 'degraded' : status === 'not_configured' ? 'not_configured' : status ? 'unavailable' : 'unknown';

/** State is always shown as an icon plus a word, never colour alone. */
const State: React.FC<{ state: ServiceState }> = ({ state }) => {
  const icon: IconName = state === 'available' ? 'check' : state === 'degraded' ? 'alert' : state === 'unknown' ? 'info' : 'x';
  return (
    <span className={`dstate dstate--${state}`}>
      <Icon name={icon} size={13} strokeWidth={2} /> {STATE_LABEL[state]}
    </span>
  );
};

const Row: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div className="drow">
    <dt>{label}</dt>
    <dd>{children}</dd>
  </div>
);

export const DiagnosticsView: React.FC = () => {
  const [data, setData] = useState<Diagnostics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [checkedAt, setCheckedAt] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/diagnostics');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setData(await res.json());
      setError(null);
      setCheckedAt(Date.now());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const backendState: ServiceState = error ? 'unavailable' : data ? data.backend.state : 'unknown';

  return (
    <div className="page">
      <div className="page__inner">
        <header className="page__header">
          <div>
            <h2 className="page__title">Diagnostics</h2>
            <p className="page__lede">
              Observed state of each local service and data provider. Values are measured when you check; nothing is
              estimated, and anything that can’t be determined is shown as unknown.
            </p>
          </div>
          <div className="page__actions">
            {checkedAt && <span className="small muted">Checked {relativeTime(checkedAt)}</span>}
            <button type="button" className="btn btn--sm" onClick={load} disabled={loading}>
              {loading ? <span className="spinner" /> : <Icon name="refresh" size={13} />} Check again
            </button>
          </div>
        </header>

        {error && (
          <div className="notice notice--danger" role="alert">
            <Icon name="alert" size={15} />
            <div>
              The backend did not answer ({error}). Start it with{' '}
              <code>.venv\Scripts\python -m uvicorn backend.friday.api.app:app --host 127.0.0.1 --port 8000</code>.
            </div>
          </div>
        )}

        {data?.warnings.map((w, i) => (
          <div key={i} className={`notice ${w.level === 'error' ? 'notice--danger' : w.level === 'warning' ? 'notice--warn' : 'notice--info'}`}>
            <Icon name={w.level === 'info' ? 'info' : 'alert'} size={15} />
            <div>{w.message}</div>
          </div>
        ))}

        <div className="dgrid">
          <section className="card dcard">
            <div className="card__header">
              <div className="card__title">Backend</div>
              <State state={backendState} />
            </div>
            {data && (
              <dl className="dlist">
                <Row label="Version"><span className="mono">{data.backend.version}</span></Row>
                <Row label="Bound to"><span className="mono">{data.backend.bind_host}:8000</span></Row>
                <Row label="Loopback only">{data.backend.loopback_only ? 'Yes' : 'No: check the configuration'}</Row>
              </dl>
            )}
          </section>

          <section className="card dcard">
            <div className="card__header">
              <div className="card__title">Language model</div>
              <State state={data ? data.model.state : 'unknown'} />
            </div>
            {data && (
              <dl className="dlist">
                <Row label="Runtime">{data.model.runtime} <span className="mono muted">{data.model.base_url}</span></Row>
                <Row label="Configured"><span className="mono">{data.model.configured}</span></Row>
                <Row label="Installed">{data.model.installed === null ? 'Unknown (Ollama unreachable)' : data.model.installed ? 'Yes' : 'No'}</Row>
                <Row label="Other local models">{data.model.installed_models.filter((m) => m !== data.model.configured).join(', ') || 'None'}</Row>
                <Row label="Request timeout"><span className="mono">{data.model.request_timeout_s} s</span></Row>
              </dl>
            )}
          </section>

          <section className="card dcard">
            <div className="card__header">
              <div className="card__title">Voice</div>
              <State state={data ? data.voice.stt_state : 'unknown'} />
            </div>
            {data && (
              <dl className="dlist">
                <Row label="Recognition">{data.voice.stt_engine} · <span className="mono">{data.voice.stt_language}</span></Row>
                <Row label="Language packs">{data.voice.recognizers.join('; ') || 'None detected'}</Row>
                <Row label="Speech output"><State state={data.voice.tts_state} /> {data.voice.voices.length} voice(s)</Row>
                <Row label="Wake word">{data.voice.wake_word_active ? 'Active' : 'Disabled'}</Row>
                <Row label="Max clip"><span className="mono">{data.voice.max_clip_seconds} s</span></Row>
              </dl>
            )}
          </section>

          <section className="card dcard">
            <div className="card__header">
              <div className="card__title">Memory & location</div>
              <State state={data ? data.memory.state : 'unknown'} />
            </div>
            {data && (
              <dl className="dlist">
                <Row label="Active memories"><span className="mono">{data.memory.active_records ?? 'unknown'}</span></Row>
                <Row label="Store"><span className="mono dpath">{data.memory.path}</span></Row>
                <Row label="Place provider"><span className="mono">{data.location.provider}</span></Row>
                <Row label="Location tracking">{data.location.tracking_enabled ? `On (${data.location.fix_status ?? 'no fix'})` : 'Off'}</Row>
              </dl>
            )}
          </section>
        </div>

        <section className="card">
          <div className="card__header">
            <div className="card__title">World data providers</div>
            {data && <span className="small muted">Earth-view-only layers (aircraft, satellites, launches, fires) report their status on the Earth screen.</span>}
          </div>
          {data && (
            <table className="dtable">
              <thead>
                <tr>
                  <th scope="col">Provider</th>
                  <th scope="col">State</th>
                  <th scope="col">Last success</th>
                  <th scope="col">Cached items</th>
                  <th scope="col">Detail</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(data.world.providers ?? {}).map(([key, p]) => (
                  <tr key={key}>
                    <td>{p.provider}</td>
                    <td><State state={providerState(p.status, p.is_stale)} /></td>
                    <td className="mono">{p.last_successful_retrieval ? relativeTime(Date.parse(p.last_successful_retrieval)) : 'never this session'}</td>
                    <td className="mono">{p.cached_items_count}</td>
                    <td className="muted small">{p.error_message ?? ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        {data && (
          <section className="card">
            <div className="card__header">
              <div className="card__title">Configuration</div>
              <span className="small muted">Environment variable names only. Values are never shown.</span>
            </div>
            <dl className="dlist dlist--cols">
              {Object.entries(data.config).map(([name, set]) => (
                <Row key={name} label={name}>{set ? 'Set' : 'Not set'}</Row>
              ))}
            </dl>
          </section>
        )}
      </div>
    </div>
  );
};
