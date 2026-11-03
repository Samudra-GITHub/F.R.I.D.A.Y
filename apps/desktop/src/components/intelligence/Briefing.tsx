import React, { useCallback, useEffect, useState } from 'react';
import { Icon } from '../ui/Icon';
import { EarthRecord, queueEarthActions } from '../../services/earthActions';
import { ago } from '../../services/earthLocation';
import './Briefing.css';

interface BriefingItem extends EarthRecord {
  level?: string;
  kind?: string;
}

interface Feed {
  provider: string;
  status: string;
  retrieved_at?: string;
  is_stale?: boolean;
  count?: number;
  details?: string;
}

interface Summary {
  summary: string | null;
  reason?: string | null;
  based_on: number;
  model?: string;
  generated_at?: string;
}

const KIND: Record<string, string> = { earthquake: 'Earthquake', disaster: 'Disaster alert', event: 'Natural event' };

/**
 * The world briefing: source records first, each with its provider, time and link.
 * The local model may summarize them on request, and its summary is labelled as its
 * reading of these records, not as news.
 */
export const Briefing: React.FC<{ onOpenEarth: () => void }> = ({ onOpenEarth }) => {
  const [items, setItems] = useState<BriefingItem[] | null>(null);
  const [feeds, setFeeds] = useState<Feed[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [writing, setWriting] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const res = await fetch('/api/world/briefing');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setItems(data.items ?? []);
      setFeeds(data.feeds ?? []);
    } catch (err) {
      setError(`The briefing couldn't load: ${err instanceof Error ? err.message : err}`);
      setItems([]);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const writeSummary = async () => {
    setWriting(true);
    try {
      const res = await fetch('/api/world/briefing/summary', { method: 'POST' });
      setSummary(res.ok ? await res.json() : { summary: null, reason: `HTTP ${res.status}`, based_on: 0 });
    } catch {
      setSummary({ summary: null, reason: 'The local core could not be reached.', based_on: 0 });
    } finally {
      setWriting(false);
    }
  };

  const showOnEarth = (item: BriefingItem) => {
    queueEarthActions(
      [
        { type: 'show_records', group: 'pulse', records: [item] },
        { type: 'select_record', id: item.id },
      ],
      `Pulse: ${item.title.slice(0, 40)}`
    );
    onOpenEarth();
  };

  return (
    <section className="briefing" aria-labelledby="briefing-h">
      <header className="briefing__head">
        <h2 id="briefing-h">Briefing</h2>
        <div className="briefing__actions">
          <button type="button" className="btn btn--sm" onClick={writeSummary} disabled={writing || !items?.length}>
            {writing ? <span className="spinner" /> : <Icon name="sparkle" size={13} />} {writing ? 'Writing with the local model…' : 'Summarize'}
          </button>
        </div>
      </header>

      {summary && (
        <div className="briefing__summary">
          {summary.summary ? (
            <>
              <p>{summary.summary}</p>
              <p className="briefing__label">
                Written by {summary.model ?? 'the local model'} from the {summary.based_on} records below
                {summary.generated_at ? `, ${ago(summary.generated_at)}` : ''}. It is a reading of those records and can be
                wrong; the records are the facts.
              </p>
            </>
          ) : (
            <p className="briefing__label">No summary: {summary.reason}</p>
          )}
        </div>
      )}

      {error && (
        <div className="notice notice--warn" role="alert">
          <Icon name="alert" size={14} />
          <div>{error}</div>
        </div>
      )}

      {items === null ? (
        <div className="briefing__loading">
          <span className="spinner" /> Gathering records
        </div>
      ) : items.length === 0 && !error ? (
        <p className="muted small">No significant records right now.</p>
      ) : (
        <ol className="briefing__items">
          {items.map((item) => (
            <li key={item.id} className="briefing__item">
              <span className={`briefing__kind briefing__kind--${item.category}`}>{KIND[item.category] ?? item.category}</span>
              <div className="briefing__main">
                <div className="briefing__title">{item.title}</div>
                <div className="briefing__meta">
                  {item.time_utc ? ago(item.time_utc) : 'time not given'} · {item.source}
                  {item.level && ` · ${item.level} alert`}
                  {item.kind && ` · ${item.kind}`}
                </div>
              </div>
              <div className="briefing__links">
                <button type="button" className="btn btn--ghost btn--sm" onClick={() => showOnEarth(item)}>
                  <Icon name="earth" size={13} /> Show on Earth
                </button>
                {item.url && (
                  <a className="btn btn--ghost btn--sm" href={item.url} target="_blank" rel="noreferrer noopener">
                    <Icon name="external" size={13} /> Source
                  </a>
                )}
              </div>
            </li>
          ))}
        </ol>
      )}

      {feeds.length > 0 && (
        <p className="briefing__feeds">
          {feeds.map((f) => (
            <span key={f.provider} className={f.status === 'ok' || f.status === 'empty' ? '' : 'briefing__feed--bad'}>
              {f.provider}: {f.status === 'ok' || f.status === 'empty' ? `retrieved ${f.retrieved_at ? ago(f.retrieved_at) : ''}` : f.status}
              {f.is_stale ? ' (stale)' : ''}
            </span>
          ))}
        </p>
      )}
    </section>
  );
};
