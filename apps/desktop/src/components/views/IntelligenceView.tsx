import React, { useCallback, useEffect, useState } from 'react';
import { Icon, IconName } from '../ui/Icon';
import { fetchDisasters, fetchEarthquakes, fetchNaturalEvents, fetchWorldNews } from '../../services/worldApi';
import { ago, requestEarthFocus } from '../../services/earthLocation';
import { FeedEnvelope } from '../../types/intelligence';
import './Page.css';
import './IntelligenceView.css';

interface Item {
  id: string;
  title: string;
  meta: string;
  time: string | null;
  url?: string | null;
  latitude?: number;
  longitude?: number;
}

type FeedId = 'quakes' | 'events' | 'disasters' | 'news';

interface Feed {
  envelope: FeedEnvelope | null;
  items: Item[];
}

const FEEDS: { id: FeedId; title: string; icon: IconName }[] = [
  { id: 'quakes', title: 'Earthquakes', icon: 'quake' },
  { id: 'events', title: 'Natural events', icon: 'flame' },
  { id: 'disasters', title: 'Disaster alerts', icon: 'alert' },
  { id: 'news', title: 'World news', icon: 'newspaper' },
];

const LOADERS: Record<FeedId, () => Promise<Feed>> = {
  quakes: async () => {
    const r = await fetchEarthquakes(2.5, 25);
    return {
      envelope: r,
      items: (r?.earthquakes ?? []).map((q) => ({
        id: q.id,
        title: `M${q.magnitude.toFixed(1)} · ${q.place}`,
        meta: `${q.depth_km.toFixed(0)} km deep`,
        time: q.time_utc,
        url: q.url,
        latitude: q.latitude,
        longitude: q.longitude,
      })),
    };
  },
  events: async () => {
    const r = await fetchNaturalEvents(30, 25);
    return {
      envelope: r,
      items: (r?.events ?? []).map((e) => ({
        id: e.id,
        title: e.title,
        meta: e.category_title,
        time: e.timestamp_utc,
        url: e.source_url,
        latitude: e.latitude,
        longitude: e.longitude,
      })),
    };
  },
  disasters: async () => {
    const r = await fetchDisasters(25);
    return {
      envelope: r,
      items: (r?.disasters ?? []).map((d) => ({
        id: d.id,
        title: d.title,
        meta: [d.alert_level, d.event_type, d.country].filter(Boolean).join(' · '),
        time: d.timestamp_utc,
        url: d.url,
        latitude: d.latitude,
        longitude: d.longitude,
      })),
    };
  },
  news: async () => {
    const r = await fetchWorldNews(25);
    return {
      envelope: r,
      items: (r?.articles ?? []).map((a) => ({
        id: a.id,
        title: a.title,
        meta: a.publisher,
        time: a.published_at_utc,
        url: a.url,
      })),
    };
  },
};

/** What the feed's own envelope supports saying: never "live" for a cached or stale result. */
export function freshnessLabel(envelope: FeedEnvelope | null): { text: string; tone: 'ok' | 'warn' | 'bad' } {
  if (!envelope) return { text: 'Unavailable', tone: 'bad' };
  if (envelope.is_stale || envelope.status === 'stale') return { text: `Stale · retrieved ${ago(envelope.retrieved_at)}`, tone: 'warn' };
  if (envelope.status === 'ok' || envelope.status === 'empty') return { text: `Retrieved ${ago(envelope.retrieved_at)}`, tone: 'ok' };
  return { text: 'Unavailable', tone: 'bad' };
}

const FeedColumn: React.FC<{
  meta: (typeof FEEDS)[number];
  feed: Feed | undefined;
  onShow: (lat: number, lon: number) => void;
}> = ({ meta, feed, onShow }) => {
  const state = feed ? freshnessLabel(feed.envelope) : null;
  return (
    <section className="intel-feed" aria-labelledby={`feed-${meta.id}`}>
      <header className="intel-feed__head">
        <Icon name={meta.icon} size={16} />
        <h2 id={`feed-${meta.id}`}>{meta.title}</h2>
        {state && <span className={`intel-fresh intel-fresh--${state.tone}`}>{state.text}</span>}
      </header>
      {!feed ? (
        <div className="intel-empty" role="status">
          <span className="spinner" /> Loading
        </div>
      ) : feed.items.length === 0 ? (
        <p className="intel-empty">
          {feed.envelope ? feed.envelope.details || 'Nothing reported right now.' : 'This source could not be reached.'}
        </p>
      ) : (
        <ol className="intel-list">
          {feed.items.map((item) => (
            <li key={item.id} className="intel-item">
              <div className="intel-item__title">{item.title}</div>
              <div className="intel-item__meta">
                {item.meta && <span>{item.meta}</span>}
                {item.time && <span>{ago(item.time)}</span>}
              </div>
              <div className="intel-item__actions">
                {item.latitude !== undefined && item.longitude !== undefined && (
                  <button type="button" className="btn btn--ghost btn--sm" onClick={() => onShow(item.latitude as number, item.longitude as number)}>
                    <Icon name="earth" size={13} /> Show on Earth
                  </button>
                )}
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
      {feed?.envelope?.attribution && <footer className="intel-feed__source">{feed.envelope.attribution}</footer>}
    </section>
  );
};

/** World events from the backend's providers, each with its own source and freshness. */
export const IntelligenceView: React.FC<{ onOpenEarth: () => void }> = ({ onOpenEarth }) => {
  const [feeds, setFeeds] = useState<Partial<Record<FeedId, Feed>>>({});
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    await Promise.all(
      FEEDS.map(async ({ id }) => {
        let feed: Feed;
        try {
          feed = await LOADERS[id]();
        } catch {
          feed = { envelope: null, items: [] };
        }
        setFeeds((f) => ({ ...f, [id]: feed }));
      })
    );
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="page">
      <div className="page__inner intel">
        <div className="page__header">
          <div>
            <h2 className="page__title">Intelligence</h2>
            <p className="page__lede">What’s happening in the world, from public sources. Each feed shows who published it and when it was retrieved.</p>
          </div>
          <div className="page__actions">
            <button type="button" className="btn" onClick={load} disabled={loading}>
              <Icon name="refresh" size={14} /> Refresh
            </button>
          </div>
        </div>
        <div className="intel-grid">
          {FEEDS.map((meta) => (
            <FeedColumn
              key={meta.id}
              meta={meta}
              feed={feeds[meta.id]}
              onShow={(latitude, longitude) => {
                requestEarthFocus({ latitude, longitude });
                onOpenEarth();
              }}
            />
          ))}
        </div>
      </div>
    </div>
  );
};
