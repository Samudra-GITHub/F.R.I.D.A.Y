import React, { useState } from 'react';
import { useApp } from '../../context/AppProvider';
import { useVoice } from '../../context/VoiceContext';
import { PageHero } from '../ui/PageHero';
import { Icon } from '../ui/Icon';
import { VoiceLab } from '../settings/VoiceLab';
import { LocationSettings } from '../settings/LocationSettings';
import { engineLabel } from '../../utils/audioUtils';
import './Page.css';
import './SettingsView.css';

const Row: React.FC<{ label: string; hint?: React.ReactNode; children: React.ReactNode }> = ({ label, hint, children }) => (
  <div className="setting">
    <div>
      <div className="setting__label">{label}</div>
      {hint && <div className="setting__hint">{hint}</div>}
    </div>
    <div className="setting__control">{children}</div>
  </div>
);

const SECTIONS = [
  { id: 'sys-h', label: 'System' },
  { id: 'voice-h', label: 'Voice' },
  { id: 'lab-h', label: 'Voice lab' },
  { id: 'priv-h', label: 'Privacy & control' },
  { id: 'loc-h', label: 'Location' },
];

const Status: React.FC<{ ok: boolean | null; yes: string; no: string }> = ({ ok, yes, no }) => (
  <span className="row small" style={{ gap: 8 }}>
    <span className={`dot ${ok === null ? '' : ok ? 'dot--ok' : 'dot--danger'}`} />
    {ok === null ? 'Unknown' : ok ? yes : no}
  </span>
);

export const SettingsView: React.FC = () => {
  const { backend, health, refreshHealth, emergencyStop } = useApp();
  const voice = useVoice();
  const [probing, setProbing] = useState(false);
  const [testingVoice, setTestingVoice] = useState(false);

  const probe = async () => {
    setProbing(true);
    await Promise.all([refreshHealth(), voice.refreshConfig()]);
    setProbing(false);
  };

  const online = backend === 'online';

  return (
    <div className="page">
      <div className="page__inner">
        <PageHero
          kicker="Runs on this computer"
          title="Settings"
          lede="System health, voice, privacy, and location. Nothing here sends anything to a cloud service."
          actions={
            <button type="button" className="btn btn--sm" onClick={probe} disabled={probing}>
              {probing ? <span className="spinner" /> : <Icon name="refresh" size={13} />} Check again
            </button>
          }
        />

        <div className="settings-layout">
        <nav className="settings-index" aria-label="Settings sections">
          {SECTIONS.map((s) => (
            <button
              key={s.id}
              type="button"
              className="settings-index__link"
              onClick={() => document.getElementById(s.id)?.closest('section')?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
            >
              {s.label}
            </button>
          ))}
          <button type="button" className="settings-index__link settings-index__out" onClick={() => (window.location.hash = 'diagnostics')}>
            Diagnostics <Icon name="chevronRight" size={13} />
          </button>
        </nav>
        <div className="settings-layout__main">

        <section className="card" aria-labelledby="sys-h">
          <div className="card__header"><div className="card__title" id="sys-h">System</div></div>
          <Row label="Backend service" hint="FastAPI, bound to 127.0.0.1 only. Requests with any other Host header are rejected.">
            <code className="setting__value">127.0.0.1:8000</code>
            <Status ok={backend === 'connecting' ? null : online} yes="Connected" no="Offline" />
          </Row>
          <Row label="Language model" hint="Runs in Ollama on this machine. If it’s unavailable, requests fail visibly; nothing falls back to a cloud model.">
            <code className="setting__value">{health?.model ?? '—'}</code>
            <Status ok={health ? health.ollama_reachable : null} yes="Reachable" no="Not reachable" />
          </Row>
          <Row label="Workspace folder" hint="The only folder the workspace tool can list. Paths outside it are rejected.">
            <code className="setting__value setting__path">{health?.workspace_root ?? '—'}</code>
          </Row>
          <Row label="Version">
            <span className="setting__value mono">{health?.version ?? '—'}</span>
          </Row>
        </section>

        <section className="card" aria-labelledby="voice-h">
          <div className="card__header">
            <div>
              <div className="card__title" id="voice-h">Voice</div>
              <div className="card__subtitle">Push-to-talk only. Recognition and speech both run offline on this computer.</div>
            </div>
            {voice.config && (
              <span className={`badge ${voice.config.stt_available ? 'badge--ok' : 'badge--danger'}`}>
                {voice.config.stt_available ? 'Engine ready' : 'Engine unavailable'}
              </span>
            )}
          </div>
          {voice.configError && (
            <div style={{ padding: '12px 20px 0' }}>
              <div className="notice notice--warn"><Icon name="alert" size={15} /><div>Voice settings could not be loaded: {voice.configError}</div></div>
            </div>
          )}
          <Row label="Microphone" hint="Device names appear after you grant microphone access once.">
            <select
              className="field"
              value={voice.selectedMicrophone ?? ''}
              onChange={(e) => voice.setSelectedMicrophone(e.target.value || null)}
              aria-label="Microphone"
            >
              <option value="">System default</option>
              {voice.microphones.map((m, i) => (
                <option key={m.deviceId || i} value={m.deviceId}>{m.label || `Microphone ${i + 1}`}</option>
              ))}
            </select>
          </Row>
          <Row label="Speak replies aloud" hint="Off by default. Press Esc at any time to stop playback.">
            <button type="button" role="switch" className="switch" aria-checked={voice.outputEnabled} onClick={() => voice.setOutputEnabled(!voice.outputEnabled)} aria-label="Speak replies aloud" />
          </Row>
          <Row label="Voice" hint="Installed Windows voices.">
            <select className="field" value={voice.selectedVoice ?? ''} onChange={(e) => voice.setSelectedVoice(e.target.value || null)} aria-label="Voice" disabled={!voice.voices.length}>
              <option value="">System default</option>
              {voice.voices.map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
            <button
              type="button"
              className="btn btn--sm"
              disabled={!online || testingVoice}
              onClick={async () => {
                setTestingVoice(true);
                await voice.speak('This is how I will sound when I answer you.');
                setTestingVoice(false);
              }}
            >
              <Icon name="play" size={12} /> Test
            </button>
          </Row>
          <Row
            label="Recognition engine"
            hint={<>Used for push-to-talk. Compare the engines on your own voice in the Voice lab below. Windows language packs: {voice.config?.installed_speech_packs?.length ? voice.config.installed_speech_packs.join('; ') : 'none detected'}</>}
          >
            <select
              className="field"
              value={voice.selectedEngine ?? ''}
              onChange={(e) => voice.setSelectedEngine(e.target.value || null)}
              aria-label="Recognition engine"
              disabled={!voice.config}
            >
              <option value="">Default ({voice.config ? engineLabel(voice.config.stt_engine) : 'unknown'})</option>
              {voice.sttEngines.map((e) => <option key={e} value={e}>{engineLabel(e)}</option>)}
              {voice.selectedEngine && voice.config && !voice.sttEngines.includes(voice.selectedEngine) && (
                <option value={voice.selectedEngine}>{engineLabel(voice.selectedEngine)} (unavailable)</option>
              )}
            </select>
          </Row>
          <Row label="Wake word" hint="Always-on listening is disabled by design. The microphone opens only when you press it.">
            <span className="badge">Disabled</span>
          </Row>
        </section>

        <section className="card" aria-labelledby="lab-h">
          <div className="card__header">
            <div>
              <div className="card__title" id="lab-h">Voice lab</div>
              <div className="card__subtitle">
                Measure recognition on your real microphone: record, listen back, then transcribe. Scores are computed from
                the actual transcript.
              </div>
            </div>
          </div>
          <VoiceLab />
        </section>

        <section className="card" aria-labelledby="priv-h">
          <div className="card__header"><div className="card__title" id="priv-h">Privacy & control</div></div>
          <Row label="Stop everything" hint={<>Stops speech, closes the microphone, and cancels the pending request. Works without the model. Shortcut: <kbd>Esc</kbd>.</>}>
            <button type="button" className="btn btn--danger btn--sm" onClick={emergencyStop}>
              <Icon name="stop" size={12} strokeWidth={2.2} /> Stop now
            </button>
          </Row>
          <Row label="Recordings" hint="Kept in this window’s memory until you send, discard, or clear them, or close the window. Never written to disk and never uploaded.">
            <span className="badge badge--ok">Local only</span>
          </Row>
          <Row label="Cloud fallback" hint="If the local model or recognizer fails, W.E.D.N.E.S.D.A.Y. reports the failure instead of using a cloud service.">
            <span className="badge badge--ok">Never</span>
          </Row>
          <Row label="Earth" hint="The Earth screen contacts its map and data providers directly from this computer. Its keys live in its own settings (POWER UP, on that screen), and its optional voice control uses OpenAI’s cloud only if you add a key.">
            <span className="badge badge--info">Network</span>
          </Row>
        </section>

        <section className="card" aria-labelledby="loc-h">
          <div className="card__header">
            <div>
              <div className="card__title" id="loc-h">Location</div>
              <div className="card__subtitle">Choose how W.E.D.N.E.S.D.A.Y. knows where you are. Continuous tracking runs only if you turn it on.</div>
            </div>
          </div>
          <LocationSettings />
        </section>
        </div>
        </div>
      </div>
    </div>
  );
};
