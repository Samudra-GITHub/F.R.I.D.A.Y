import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useApp } from '../../context/AppProvider';
import { fetchAudit } from '../../services/voiceApi';
import { AuditEvent, SessionEvent } from '../../types/voice';
import { PageHero } from '../ui/PageHero';
import { Icon, IconName } from '../ui/Icon';
import './Page.css';
import './ActivityView.css';

type Row = {
  key: string;
  at: number;
  source: 'broker' | 'session';
  title: string;
  details?: string;
  tone: 'ok' | 'danger' | 'warn' | 'info' | 'neutral';
  label: string;
  icon: IconName;
  digest?: string | null;
};

type Filter = 'all' | 'broker' | 'denied' | 'session';

const fromAudit = (e: AuditEvent): Row => {
  const denied = e.outcome === 'denied';
  return {
    key: `a${e.seq}`,
    at: Date.parse(e.at_utc),
    source: 'broker',
    title:
      e.kind === 'decision'
        ? `${denied ? 'Denied' : 'Allowed'} · ${e.tool}`
        : e.kind === 'consent'
        ? `Consent ${e.outcome} · ${e.tool.replace(/_/g, ' ')}`
        : `Memory ${e.outcome}`,
    details: e.reason || undefined,
    tone: denied ? 'danger' : e.kind === 'consent' ? 'warn' : e.kind === 'memory' ? 'info' : 'ok',
    label: e.kind === 'decision' ? e.outcome : e.kind,
    icon: e.kind === 'decision' ? 'shield' : e.kind === 'consent' ? 'lock' : 'memory',
    digest: e.args_digest,
  };
};

const fromSession = (e: SessionEvent): Row => ({
  key: e.id,
  at: e.at,
  source: 'session',
  title: e.title,
  details: e.details,
  tone: e.outcome === 'ok' ? 'ok' : e.outcome === 'failed' || e.outcome === 'denied' ? 'danger' : e.outcome === 'cancelled' ? 'warn' : 'neutral',
  label: e.outcome,
  icon: e.kind === 'conversation' ? 'assistant' : e.kind === 'voice' ? 'mic' : e.kind === 'world' ? 'earth' : e.kind === 'location' ? 'locate' : 'cpu',
});

/** "Today", "Yesterday", or the date, for grouping the timeline. */
export function dayLabel(at: number, now = Date.now()): string {
  const day = (t: number) => new Date(t).toDateString();
  if (day(at) === day(now)) return 'Today';
  if (day(at) === day(now - 86400000)) return 'Yesterday';
  return new Date(at).toLocaleDateString([], { weekday: 'long', month: 'short', day: 'numeric' });
}

export const ActivityView: React.FC = () => {
  const { events, clearEvents, backend } = useApp();
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [auditError, setAuditError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<Filter>('all');

  const load = useCallback(async () => {
    try {
      setAudit(await fetchAudit(200));
      setAuditError(null);
    } catch (err) {
      setAuditError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const t = window.setInterval(() => document.visibilityState === 'visible' && load(), 10000);
    return () => window.clearInterval(t);
  }, [load]);

  const rows = useMemo(() => {
    const all = [...audit.map(fromAudit), ...events.map(fromSession)].sort((a, b) => b.at - a.at);
    return all.filter((r) =>
      filter === 'all' ? true : filter === 'denied' ? r.tone === 'danger' : r.source === filter
    );
  }, [audit, events, filter]);

  const deniedCount = audit.filter((a) => a.outcome === 'denied').length;

  const days = useMemo(() => {
    const groups: { label: string; rows: Row[] }[] = [];
    for (const r of rows) {
      const label = dayLabel(r.at);
      if (groups[groups.length - 1]?.label !== label) groups.push({ label, rows: [] });
      groups[groups.length - 1].rows.push(r);
    }
    return groups;
  }, [rows]);

  return (
    <div className="page">
      <div className="page__inner">
        <PageHero
          kicker="Accountability"
          title="Activity"
          lede="Every decision the capability broker made, and what happened in this session. Tool arguments are never stored; the broker keeps its last 200 decisions in memory until the backend restarts."
          stats={[
            { label: 'Broker decisions', value: audit.filter((a) => a.kind === 'decision').length },
            { label: 'Denied', value: deniedCount, tone: deniedCount ? 'danger' : undefined },
            { label: 'Session events', value: events.length },
          ]}
          actions={
            <>
              <button type="button" className="btn btn--sm" onClick={load} disabled={backend !== 'online'}>
                <Icon name="refresh" size={13} /> Refresh
              </button>
              <button type="button" className="btn btn--sm btn--ghost" onClick={clearEvents} disabled={!events.length}>
                Clear session events
              </button>
            </>
          }
        />

        <div className="toolbar" role="group" aria-label="Filter activity">
          {(['all', 'broker', 'denied', 'session'] as Filter[]).map((f) => (
            <button key={f} type="button" className="chip" aria-pressed={filter === f} onClick={() => setFilter(f)}>
              {f === 'all' ? 'All' : f === 'broker' ? 'Broker' : f === 'denied' ? 'Denied' : 'This session'}
            </button>
          ))}
        </div>

        {auditError && (
          <div className="notice notice--warn">
            <Icon name="alert" size={15} />
            <div>Couldn’t load the broker log: {auditError}</div>
          </div>
        )}

        <section className="card">
          {loading ? (
            <div className="activity__loading">
              {[0, 1, 2].map((i) => <div key={i} className="skeleton" style={{ height: 44 }} />)}
            </div>
          ) : rows.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state__icon"><Icon name="activity" size={20} /></div>
              <div className="empty-state__title">Nothing recorded yet</div>
              <p className="empty-state__body">Ask the assistant something that needs a tool, like the local time or recent earthquakes, and its decisions will show up here.</p>
            </div>
          ) : (
            days.map((d) => (
            <div key={d.label} className="timeline__day">
            <h3 className="timeline__day-label">{d.label}</h3>
            <ol className="list timeline">
              {d.rows.map((r) => (
                <li key={r.key} className={`timeline__row tone-${r.tone}`}>
                  <span className="timeline__icon"><Icon name={r.icon} size={15} /></span>
                  <div className="timeline__main">
                    <div className="timeline__title">{r.title}</div>
                    {r.details && <div className="timeline__details">{r.details}</div>}
                  </div>
                  <div className="timeline__side">
                    <span className={`badge badge--${r.tone === 'neutral' ? 'info' : r.tone}`}>{r.label}</span>
                    <time className="mono tabular" dateTime={new Date(r.at).toISOString()}>
                      {new Date(r.at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                    </time>
                    {r.digest && <span className="mono timeline__digest" title="SHA-256 prefix of the canonical arguments">#{r.digest.slice(0, 8)}</span>}
                  </div>
                </li>
              ))}
            </ol>
            </div>
            ))
          )}
        </section>
      </div>
    </div>
  );
};
