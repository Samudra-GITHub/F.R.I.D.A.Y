import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Icon } from '../ui/Icon';
import { EarthRecord, queueEarthActions } from '../../services/earthActions';
import { recordsByDay } from '../../services/earthMode';
import './EarthPanels.css';

interface History {
  start: string;
  end: string;
  records: EarthRecord[];
  consulted: { provider: string; count: number }[];
  missing: { provider: string; reason: string }[];
  retrieved_at: string;
}

const isoDay = (offsetDays: number) => new Date(Date.now() - offsetDays * 86400000).toISOString().slice(0, 10);
const STEP_MS = 900;

async function loadHistory(start: string, end: string, minMag: number): Promise<History> {
  const params = new URLSearchParams({ start, end, min_magnitude: String(minMag) });
  const res = await fetch(`/api/world/history?${params}`);
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(typeof detail?.detail === 'string' ? detail.detail : `The archive request failed (HTTP ${res.status}).`);
  }
  return res.json();
}

const count = (records: EarthRecord[], category: string) => records.filter((r) => r.category === category).length;

/**
 * The Time Machine: real archived records, stepped through day by day. A day with no
 * records shows none; nothing is filled in, and live data never stands in for history.
 */
export const TimeMachine: React.FC = () => {
  const [start, setStart] = useState(isoDay(30));
  const [end, setEnd] = useState(isoDay(1));
  const [minMag, setMinMag] = useState(4.5);
  const [history, setHistory] = useState<History | null>(null);
  const [compare, setCompare] = useState<History | null>(null);
  const [compareStart, setCompareStart] = useState(isoDay(395));
  const [compareEnd, setCompareEnd] = useState(isoDay(366));
  const [loading, setLoading] = useState<'a' | 'b' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cursor, setCursor] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [cumulative, setCumulative] = useState(false);
  const timer = useRef<number>();

  const days = useMemo(() => (history ? recordsByDay(history.records, history.start, history.end) : []), [history]);
  const visible = useMemo(() => {
    if (!days.length) return [];
    return cumulative ? days.slice(0, cursor + 1).flatMap((d) => d.records) : days[cursor]?.records ?? [];
  }, [days, cursor, cumulative]);

  // What the globe shows always follows the playhead.
  useEffect(() => {
    if (!history) return;
    queueEarthActions([{ type: 'show_records', group: 'time', records: visible.slice(0, 500) }], 'Time Machine');
  }, [history, visible]);

  useEffect(() => {
    if (!playing) return;
    timer.current = window.setInterval(() => {
      setCursor((c) => {
        if (c >= days.length - 1) {
          setPlaying(false);
          return c;
        }
        return c + 1;
      });
    }, STEP_MS);
    return () => window.clearInterval(timer.current);
  }, [playing, days.length]);

  // Leaving the Time Machine takes its records off the globe.
  useEffect(
    () => () => {
      queueEarthActions(
        [
          { type: 'show_records', group: 'time', records: [] },
          { type: 'show_records', group: 'compare', records: [] },
        ],
        'Time Machine closed'
      );
    },
    []
  );

  const load = useCallback(async () => {
    setLoading('a');
    setError(null);
    setPlaying(false);
    try {
      const h = await loadHistory(start, end, minMag);
      setHistory(h);
      setCursor(0);
      // A period is worldwide, so pull back from whatever was being looked at.
      queueEarthActions([{ type: 'clear_selection' }, { type: 'return_global' }], 'Time Machine');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(null);
    }
  }, [start, end, minMag]);

  const loadCompare = async () => {
    setLoading('b');
    setError(null);
    try {
      const h = await loadHistory(compareStart, compareEnd, minMag);
      setCompare(h);
      queueEarthActions([{ type: 'show_records', group: 'compare', records: h.records.slice(0, 500) }], 'Comparison');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(null);
    }
  };

  const day = days[cursor];

  return (
    <section className="earth-panel earth-panel--time" aria-label="Time Machine">
      <header className="earth-panel__head">
        <span className="earth-panel__kicker">Time Machine</span>
        <span className="earth-panel__hint">USGS earthquake catalogue and NASA EONET archives</span>
      </header>

      <div className="time__controls">
        <label>
          <span>From</span>
          <input className="field" type="date" value={start} max={end} min="1900-01-01" onChange={(e) => setStart(e.target.value)} />
        </label>
        <label>
          <span>To</span>
          <input className="field" type="date" value={end} min={start} max={isoDay(0)} onChange={(e) => setEnd(e.target.value)} />
        </label>
        <label>
          <span>Min. magnitude</span>
          <input className="field" type="number" min={0} max={10} step={0.5} value={minMag} onChange={(e) => setMinMag(Number(e.target.value))} />
        </label>
        <button type="button" className="btn btn--primary btn--sm" onClick={load} disabled={loading !== null}>
          {loading === 'a' ? <span className="spinner" /> : <Icon name="clock" size={13} />} Load
        </button>
      </div>

      {error && (
        <div className="notice notice--warn" role="alert">
          <Icon name="alert" size={14} />
          <div>{error}</div>
        </div>
      )}

      {history && days.length > 0 && (
        <>
          <div className="time__playback">
            <button type="button" className="icon-btn" onClick={() => setPlaying((p) => !p)} aria-label={playing ? 'Pause' : 'Play'}>
              <Icon name={playing ? 'stop' : 'play'} size={15} />
            </button>
            <button
              type="button"
              className="icon-btn"
              onClick={() => {
                setPlaying(false);
                setCursor(0);
              }}
              aria-label="Back to the first day"
            >
              <Icon name="reset" size={15} />
            </button>
            <input
              className="time__slider"
              type="range"
              min={0}
              max={days.length - 1}
              value={cursor}
              onChange={(e) => setCursor(Number(e.target.value))}
              aria-label="Day"
              aria-valuetext={day?.day}
            />
            <span className="time__day mono">{day?.day}</span>
          </div>
          <div className="time__stats" aria-live="polite">
            <span>
              <strong>{count(visible, 'earthquake')}</strong> earthquakes
            </span>
            <span>
              <strong>{count(visible, 'event')}</strong> natural events
            </span>
            <span className="muted">{cumulative ? `${start} to ${day?.day}` : 'on this day'}</span>
            <label className="time__toggle">
              <input type="checkbox" checked={cumulative} onChange={(e) => setCumulative(e.target.checked)} /> Build up over time
            </label>
          </div>
          <details className="time__sources">
            <summary>
              Sources · {history.records.length} records · retrieved {new Date(history.retrieved_at).toLocaleTimeString()}
            </summary>
            <ul>
              {history.consulted.map((c) => (
                <li key={c.provider}>
                  {c.provider}: {c.count} records
                </li>
              ))}
              {history.missing.map((m) => (
                <li key={m.provider} className="time__missing">
                  {m.provider}: {m.reason}
                </li>
              ))}
              <li className="muted">Only records the archives hold are shown. A day with nothing shown had nothing recorded at this threshold.</li>
            </ul>
          </details>

          <details className="time__compare">
            <summary>Compare with another period</summary>
            <div className="time__controls">
              <label>
                <span>From</span>
                <input className="field" type="date" value={compareStart} max={compareEnd} min="1900-01-01" onChange={(e) => setCompareStart(e.target.value)} />
              </label>
              <label>
                <span>To</span>
                <input className="field" type="date" value={compareEnd} min={compareStart} max={isoDay(0)} onChange={(e) => setCompareEnd(e.target.value)} />
              </label>
              <button type="button" className="btn btn--sm" onClick={loadCompare} disabled={loading !== null}>
                {loading === 'b' ? <span className="spinner" /> : null} Compare
              </button>
            </div>
            {compare && (
              <table className="time__table">
                <thead>
                  <tr>
                    <th />
                    <th>
                      {history.start} to {history.end}
                    </th>
                    <th className="time__b">
                      {compare.start} to {compare.end}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Earthquakes (M{minMag}+)</td>
                    <td>{count(history.records, 'earthquake')}</td>
                    <td className="time__b">{count(compare.records, 'earthquake')}</td>
                  </tr>
                  <tr>
                    <td>Natural events</td>
                    <td>{count(history.records, 'event')}</td>
                    <td className="time__b">{count(compare.records, 'event')}</td>
                  </tr>
                </tbody>
              </table>
            )}
            {compare && <p className="small muted">The comparison period is drawn in blue. Ranges of different lengths aren't directly comparable.</p>}
          </details>
        </>
      )}
    </section>
  );
};
