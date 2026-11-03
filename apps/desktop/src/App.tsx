import React, { useCallback, useEffect, useState } from 'react';
import { NavTab } from './types/voice';
import { useApp, useAssistantPhase } from './context/AppProvider';
import { useVoice } from './context/VoiceContext';
import { useLocationAwareness } from './context/LocationProvider';
import { Icon, IconName } from './components/ui/Icon';
import { phaseLabel } from './components/ui/Presence';
import { ErrorBoundary } from './components/common/ErrorBoundary';
import { AssistantView } from './components/views/AssistantView';
import { ActivityView } from './components/views/ActivityView';
import { MemoryView } from './components/views/MemoryView';
import { ToolsView } from './components/views/ToolsView';
import { SettingsView } from './components/views/SettingsView';
import { DiagnosticsView } from './components/views/DiagnosticsView';
import { EarthView } from './components/views/EarthView';
import { IntelligenceView } from './components/views/IntelligenceView';
import { setEarthMode, useEarthMode, EarthMode } from './services/earthMode';
import './App.css';

const NAV: { id: NavTab; label: string; icon: IconName; title: string; group: 'main' | 'system' }[] = [
  { id: 'assistant', label: 'Mind', icon: 'assistant', title: 'Mind', group: 'main' },
  { id: 'earth', label: 'World', icon: 'earth', title: 'World', group: 'main' },
  { id: 'intelligence', label: 'Pulse', icon: 'sparkle', title: 'Pulse', group: 'main' },
  { id: 'activity', label: 'Activity', icon: 'activity', title: 'Activity', group: 'main' },
  { id: 'memory', label: 'Memory', icon: 'memory', title: 'Memory', group: 'main' },
  { id: 'tools', label: 'Security', icon: 'shield', title: 'Security', group: 'system' },
  { id: 'settings', label: 'Settings', icon: 'settings', title: 'Settings', group: 'system' },
];

const isTab = (id: string): id is NavTab => id === 'diagnostics' || NAV.some((n) => n.id === id);

const readTab = (): NavTab => {
  const hash = window.location.hash.replace('#', '');
  return isTab(hash) ? hash : 'assistant';
};

const readExpanded = () => {
  try {
    const v = localStorage.getItem('friday.nav');
    return v ? v === 'expanded' : window.innerWidth >= 1280;
  } catch {
    return window.innerWidth >= 1280;
  }
};

const BrandMark: React.FC = () => (
  <svg className="rail__mark" viewBox="0 0 64 64" aria-hidden="true">
    <path d="M8.5 40A25 25 0 0 1 49 13.5" className="rail__mark-arc" />
    <path d="M17 23l7.5 20L32 27l7.5 16L47 23" className="rail__mark-w" />
  </svg>
);

export const App: React.FC = () => {
  const [tab, setTab] = useState<NavTab>(readTab);
  const [expanded, setExpanded] = useState(readExpanded);
  const { backend, health, pendingSince, emergencyStop } = useApp();
  const voice = useVoice();
  const location = useLocationAwareness();
  const earthMode = useEarthMode();
  const [earthQuiet, setEarthQuiet] = useState(false);
  const phase = useAssistantPhase();
  const busy = pendingSince !== null || voice.isRecording || voice.isSpeaking;
  const [earthOpened, setEarthOpened] = useState(tab === 'earth');
  useEffect(() => {
    if (tab === 'earth') setEarthOpened(true);
  }, [tab]);

  const go = useCallback((next: NavTab) => {
    setTab(next);
    history.replaceState(null, '', `#${next}`);
  }, []);

  const toggleNav = () => {
    setExpanded((e) => {
      try {
        localStorage.setItem('friday.nav', e ? 'collapsed' : 'expanded');
      } catch {
        /* preference lasts this session */
      }
      return !e;
    });
  };

  useEffect(() => {
    const onHash = () => setTab(readTab());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  // Keyboard: Esc stops speech/recording/requests (independent of the model);
  // Alt+1…7 switches screens.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && busy) {
        e.preventDefault();
        emergencyStop();
      } else if (e.altKey && !e.ctrlKey && !e.metaKey && /^[1-7]$/.test(e.key)) {
        e.preventDefault();
        go(NAV[Number(e.key) - 1].id);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [busy, emergencyStop, go]);

  const currentTitle = tab === 'diagnostics' ? 'Diagnostics' : NAV.find((n) => n.id === tab)!.title;
  const locationKind = location.view.kind;
  const locationTone = location.view.monitoring && location.view.fresh ? 'on' : ['denied', 'stopped', 'no_fresh_fix', 'unavailable'].includes(locationKind) ? 'warn' : 'idle';
  const modelState = backend !== 'online' ? null : health?.ollama_reachable ? 'ok' : 'down';
  const backendDot = backend === 'online' ? 'dot--ok' : backend === 'offline' ? 'dot--danger' : 'dot--warn';

  const navItem = (item: (typeof NAV)[number], i: number) => (
    <li key={item.id}>
      <button
        type="button"
        className="rail__item"
        aria-current={tab === item.id ? 'page' : undefined}
        onClick={() => go(item.id)}
        title={expanded ? undefined : `${item.title} (Alt+${i + 1})`}
      >
        <Icon name={item.icon} size={19} />
        <span className="rail__label">{item.label}</span>
      </button>
    </li>
  );

  return (
    <div className="shell" data-tab={tab} data-quiet={tab === 'earth' && earthQuiet} data-nav={expanded && tab !== 'earth' ? 'expanded' : 'collapsed'}>
      <a className="skip-link" href="#main">Skip to content</a>
      <nav className="rail" aria-label="Primary">
        <div className="rail__brand">
          <BrandMark />
          <span className="rail__name">W.E.D.N.E.S.D.A.Y.</span>
        </div>
        <ul className="rail__list">{NAV.filter((n) => n.group === 'main').map((n) => navItem(n, NAV.indexOf(n)))}</ul>
        <div className="rail__sep" />
        <ul className="rail__list">{NAV.filter((n) => n.group === 'system').map((n) => navItem(n, NAV.indexOf(n)))}</ul>
        <div className="rail__foot">
          <button
            type="button"
            className="rail__item"
            aria-current={tab === 'diagnostics' ? 'page' : undefined}
            onClick={() => go('diagnostics')}
            title={expanded ? undefined : 'Diagnostics'}
          >
            <Icon name="cpu" size={19} />
            <span className="rail__label">Diagnostics</span>
          </button>
          <button type="button" className="icon-btn rail__toggle" onClick={toggleNav} aria-label={expanded ? 'Collapse navigation' : 'Expand navigation'} aria-expanded={expanded}>
            <Icon name={expanded ? 'chevronLeft' : 'chevronRight'} size={16} />
          </button>
        </div>
      </nav>

      <div className="shell__main">
        <header className="topbar">
          <h1 className="topbar__title">{currentTitle}</h1>
          {tab === 'earth' && (
            <div className="topbar__modes" role="group" aria-label="World mode">
              {(['live', 'time', 'orbit'] as EarthMode[]).map((m) => (
                <button key={m} type="button" className="topbar__mode" aria-pressed={earthMode === m} onClick={() => setEarthMode(m)}>
                  {m === 'live' ? 'Live' : m === 'time' ? 'Time' : 'Orbit'}
                </button>
              ))}
            </div>
          )}
          <div className="topbar__status" role="status">
            {voice.isRecording && (
              <span className="topbar__mic" title="The microphone is recording">
                <Icon name="mic" size={13} strokeWidth={2} /> Microphone on
              </span>
            )}
            <span className="topbar__phase" data-phase={phase}>
              <span className="topbar__phase-dot" />
              {phaseLabel(phase)}
            </span>
            <span className="topbar__location" data-tone={locationTone}>
              <button type="button" className="topbar__location-open" onClick={() => go('settings')} title="Location settings">
                <Icon name="locate" size={13} strokeWidth={2} />
                <span>{location.view.label}</span>
              </button>
              {location.status?.mode === 'continuous' && (
                <>
                  {location.status.is_paused ? (
                    <button type="button" className="btn btn--sm btn--ghost" onClick={location.resume} disabled={location.busy}>
                      Resume
                    </button>
                  ) : (
                    <button type="button" className="btn btn--sm btn--ghost" onClick={location.pause} disabled={location.busy}>
                      Pause
                    </button>
                  )}
                  <button type="button" className="btn btn--sm btn--ghost" onClick={location.stop} disabled={location.busy}>
                    Stop
                  </button>
                </>
              )}
            </span>
            <span className="topbar__sep" />
            <span className="topbar__item" title="Local FastAPI service on 127.0.0.1:8000">
              <span className={`dot ${backendDot}`} />
              {backend === 'online' ? 'Backend' : backend === 'offline' ? 'Backend offline' : 'Connecting…'}
            </span>
            {modelState && (
              <span className="topbar__item" title="Local Ollama model">
                <span className={`dot ${modelState === 'ok' ? 'dot--ok' : 'dot--danger'}`} />
                <span className="mono">{health?.model}</span>
                {modelState === 'down' && <span className="muted">unreachable</span>}
              </span>
            )}
            <button
              type="button"
              className="btn btn--sm btn--danger topbar__stop"
              onClick={emergencyStop}
              disabled={!busy}
              title="Stop speech, recording and the pending request (Esc)"
            >
              <Icon name="stop" size={12} strokeWidth={2.2} />
              Stop <kbd>Esc</kbd>
            </button>
          </div>
        </header>

        <main className="stage" id="main" tabIndex={-1}>
          <ErrorBoundary region={currentTitle} key={tab}>
            <div className="stage__view view-enter">
              {tab === 'assistant' && <AssistantView />}
              {tab === 'intelligence' && <IntelligenceView onOpenEarth={() => go('earth')} />}
              {tab === 'activity' && <ActivityView />}
              {tab === 'memory' && <MemoryView />}
              {tab === 'tools' && <ToolsView />}
              {tab === 'settings' && <SettingsView />}
              {tab === 'diagnostics' && <DiagnosticsView />}
            </div>
          </ErrorBoundary>
          {/* Stays mounted after first opening so its camera and layers survive switching screens. */}
          {earthOpened && (
            <div className="stage__earth" hidden={tab !== 'earth'}>
              <ErrorBoundary region="Earth">
                <EarthView active={tab === 'earth'} onQuietChange={setEarthQuiet} />
              </ErrorBoundary>
            </div>
          )}
        </main>
      </div>
    </div>
  );
};
