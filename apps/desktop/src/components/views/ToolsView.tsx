import React, { useCallback, useEffect, useState } from 'react';
import { fetchCapabilities, setConsent } from '../../services/voiceApi';
import { CapabilitiesResponse, ConsentKey } from '../../types/voice';
import { useApp } from '../../context/AppProvider';
import { PageHero } from '../ui/PageHero';
import { Icon, IconName } from '../ui/Icon';
import './Page.css';
import './ToolsView.css';

const CONSENTS: { key: ConsentKey; title: string; body: string; icon: IconName }[] = [
  {
    key: 'world_read',
    title: 'World data',
    body: 'Earthquakes (USGS), weather (Open-Meteo), natural events (NASA EONET), disaster alerts (GDACS). Read-only public feeds.',
    icon: 'earth',
  },
  {
    key: 'media_control',
    title: 'Media keys',
    body: 'Lets the assistant press play/pause, next, and previous. Windows doesn’t report playback state back, so these actions are always marked unverified.',
    icon: 'play',
  },
  {
    key: 'location_read',
    title: 'Read device location',
    body: 'Lets the assistant read your latest position from Windows. How often it’s read is set in Settings → Location.',
    icon: 'locate',
  },
  {
    key: 'places_search',
    title: 'Places & addresses',
    body: 'Reverse geocoding and nearby search through the configured provider (OpenStreetMap by default). Sends coordinates to that provider.',
    icon: 'pin',
  },
];

const PERMISSION_LABEL: Record<string, string> = {
  'system:time': 'Always allowed',
  'workspace:read': 'Always allowed',
  'world:read': 'World data',
  'media:control': 'Media keys',
  'location:read': 'Device location',
  'places:search': 'Places',
  'location:control': 'Never automated',
};

export const ToolsView: React.FC = () => {
  const { backend, logEvent, refreshHealth } = useApp();
  const [caps, setCaps] = useState<CapabilitiesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<ConsentKey | null>(null);

  const load = useCallback(async () => {
    try {
      setCaps(await fetchCapabilities());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const toggle = async (key: ConsentKey, enabled: boolean) => {
    setBusy(key);
    try {
      await setConsent(key, enabled);
      logEvent({ kind: 'system', title: `${enabled ? 'Granted' : 'Revoked'}: ${key.replace(/_/g, ' ')}`, outcome: 'info' });
      await load();
      refreshHealth();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="page">
      <div className="page__inner">
        <PageHero
          kicker="Deny by default"
          title="Security"
          lede={
            <>
              The model can only <em>propose</em> actions. The capability broker checks every proposal against the tool’s
              schema and the permissions below, and denies anything else. Permissions last for this backend session and
              reset to the configured defaults when it restarts.
            </>
          }
          stats={[
            { label: 'Tools registered', value: caps?.tools.length ?? '–' },
            { label: 'Permitted now', value: caps ? caps.tools.filter((t) => t.permitted).length : '–', tone: 'accent' },
            { label: 'Permissions granted', value: caps ? `${CONSENTS.filter((c) => caps.consents?.[c.key]).length} of ${CONSENTS.length}` : '–' },
            { label: 'Shell access', value: 'None' },
          ]}
        />

        {(error || backend === 'offline') && (
          <div className="notice notice--danger" role="alert">
            <Icon name="alert" size={15} />
            <div>{backend === 'offline' ? 'The backend is offline, so permissions can’t be read or changed.' : error}</div>
          </div>
        )}

        <section className="card">
          <div className="card__header">
            <div>
              <div className="card__title">Session permissions</div>
              <div className="card__subtitle">You decide these; the model can’t change them.</div>
            </div>
          </div>
          <div className="consent-grid">
          {CONSENTS.map((c) => {
            const on = caps?.consents?.[c.key] ?? false;
            return (
              <div className={`consent-tile ${on ? 'is-on' : ''}`} key={c.key}>
                <div className="consent__label">
                  <span className={`consent__icon ${on ? 'is-on' : ''}`}><Icon name={c.icon} size={16} /></span>
                  <div>
                    <div className="setting__label">{c.title}</div>
                    <div className="setting__hint">{c.body}</div>
                  </div>
                </div>
                <div className="setting__control">
                  {busy === c.key && <span className="spinner" />}
                  <button
                    type="button"
                    role="switch"
                    className="switch"
                    aria-checked={on}
                    aria-label={c.title}
                    disabled={!caps || busy !== null}
                    onClick={() => toggle(c.key, !on)}
                  />
                </div>
              </div>
            );
          })}
          </div>
        </section>

        <section className="card">
          <div className="card__header">
            <div>
              <div className="card__title">Registered tools</div>
              <div className="card__subtitle">Fixed at startup. There is no shell tool and no way for the model to add tools.</div>
            </div>
            <span className="badge">{caps?.tools.length ?? '–'} tools</span>
          </div>
          {!caps ? (
            <div style={{ padding: 16, display: 'grid', gap: 10 }}>
              {[0, 1, 2].map((i) => <div key={i} className="skeleton" style={{ height: 40 }} />)}
            </div>
          ) : (
            <ul className="tool-grid">
              {caps.tools.map((t) => {
                const params = Object.keys((t.parameters as { properties?: object }).properties ?? {});
                return (
                  <li key={t.name} className="tool">
                    <div className="tool__main">
                      <div className="row" style={{ gap: 8 }}>
                        <span className="mono tool__name">{t.name}</span>
                        <span className={`badge ${t.permitted ? 'badge--ok' : ''}`}>{t.permitted ? 'Permitted' : 'Blocked'}</span>
                      </div>
                      <p className="tool__desc">{t.description}</p>
                      {params.length > 0 && (
                        <p className="tool__params mono">({params.join(', ')})</p>
                      )}
                    </div>
                    <span className="tool__perm small muted">{PERMISSION_LABEL[t.permission] ?? t.permission}</span>
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
};
