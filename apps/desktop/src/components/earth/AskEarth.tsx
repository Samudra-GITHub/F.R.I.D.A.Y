import React, { useMemo, useRef, useState } from 'react';
import { useApp } from '../../context/AppProvider';
import { Icon } from '../ui/Icon';
import { Markdown } from '../ui/Markdown';
import { UnmatchedNotice } from '../ui/UnmatchedNotice';
import { Presence } from '../ui/Presence';
import { useAssistantPhase } from '../../context/AppProvider';
import { MicButton, TranscriptReview } from '../views/AssistantView';
import { describeAction, describeToolCall, EarthRecord, queueEarthActions, useEarthBatch } from '../../services/earthActions';
import { ago } from '../../services/earthLocation';
import './AskEarth.css';

const SUGGESTIONS = [
  'Show earthquakes above magnitude 4 today',
  'Where is the International Space Station?',
  'Find aircraft near India',
  'Take me to my location',
  'What natural events are happening this week?',
];

/**
 * Ask the Earth: the assistant, docked to the planet. It shares the conversation with
 * the Assistant screen; replies that carry Earth actions are shown with Earth's own
 * report of what it did, never with the model's claim alone.
 */
export const AskEarth: React.FC = () => {
  const { messages, send, pendingSince, cancel, backend, runningTool } = useApp();
  const phase = useAssistantPhase();
  const [text, setText] = useState('');
  const [open, setOpen] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const lastUserIndex = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) if (messages[i].role === 'user') return i;
    return -1;
  }, [messages]);
  const question = lastUserIndex >= 0 ? messages[lastUserIndex] : null;
  const answer = lastUserIndex >= 0 ? messages.slice(lastUserIndex + 1).find((m) => m.role === 'assistant') : undefined;
  const batch = useEarthBatch(answer?.earthBatchId);
  const records = useMemo<EarthRecord[]>(() => {
    const show = batch?.actions.find((a) => a.type === 'show_records');
    return show && show.type === 'show_records' ? show.records.slice(0, 40) : [];
  }, [batch]);

  const submit = (value: string) => {
    const trimmed = value.trim();
    if (!trimmed || pendingSince !== null) return;
    setText('');
    setOpen(true);
    void send(trimmed);
  };

  const pending = pendingSince !== null;
  const showPanel = open && (question || pending);

  return (
    <div className={`ask ${showPanel ? 'ask--open' : ''}`}>
      {showPanel && (
        <section className="ask__panel" aria-label="Ask the Earth" aria-live="polite">
          <header className="ask__head">
            <Presence phase={phase} size={30} />
            <span className="ask__question">{question?.content}</span>
            <button type="button" className="icon-btn icon-btn--sm" onClick={() => setOpen(false)} aria-label="Hide answer">
              <Icon name="chevronDown" size={14} />
            </button>
          </header>

          {pending && (
            <div className="ask__progress">
              <span className="spinner" />
              {runningTool ? `Using ${describeToolCall(runningTool)}` : 'Thinking with the local model'}
              <button type="button" className="btn btn--ghost btn--sm" onClick={cancel}>
                Stop
              </button>
            </div>
          )}

          {answer && !pending && (
            <div className="ask__body">
              {answer.toolCalls && answer.toolCalls.length > 0 && (
                <div className="ask__read">
                  <span className="ask__label">Read as</span>
                  {answer.toolCalls.map((c, i) => (
                    <span key={i} className={`ask__chip ${c.ok ? '' : 'ask__chip--bad'}`} title={c.details || c.error || ''}>
                      {describeToolCall(c.tool_name, c.arguments)}
                      {!c.allowed && ' · not allowed'}
                    </span>
                  ))}
                </div>
              )}

              <UnmatchedNotice mentions={answer.unmatchedMentions} />
              <div className="ask__answer">
                <Markdown text={answer.content} />
              </div>

              {batch && (
                <ul className="ask__actions" aria-label="What Earth did">
                  {batch.state !== 'done' && (
                    <li className="ask__action">
                      <span className="spinner" /> Waiting for Earth to confirm
                    </li>
                  )}
                  {batch.state === 'done' &&
                    batch.actions.map((a, i) => {
                      const r = batch.results?.[i];
                      return (
                        <li key={i} className={`ask__action ${r?.ok ? 'is-ok' : 'is-bad'}`}>
                          <Icon name={r?.ok ? 'check' : 'x'} size={12} strokeWidth={2.2} />
                          {describeAction(a)}
                          {r?.error && <span className="ask__why">{r.error}</span>}
                        </li>
                      );
                    })}
                </ul>
              )}

              {records.length > 0 && (
                <ol className="ask__records" aria-label="Records on the globe">
                  {records.map((r) => (
                    <li key={r.id}>
                      <button
                        type="button"
                        className="ask__record"
                        onClick={() => queueEarthActions([{ type: 'select_record', id: r.id }], 'Select record')}
                      >
                        <span className="ask__record-title">{r.title}</span>
                        <span className="ask__record-meta">
                          {r.time_utc ? ago(r.time_utc) : 'time not given'} · {r.source}
                        </span>
                      </button>
                    </li>
                  ))}
                </ol>
              )}

              {answer.sources && answer.sources.length > 0 && (
                <details className="ask__sources">
                  <summary>
                    {answer.sources.length} source{answer.sources.length === 1 ? '' : 's'}
                  </summary>
                  <ul>
                    {answer.sources.map((s, i) => (
                      <li key={i}>
                        {s.url ? (
                          <a href={s.url} target="_blank" rel="noopener noreferrer">
                            {s.title}
                          </a>
                        ) : (
                          s.title
                        )}
                        {s.retrieved_at_utc && <span className="ask__record-meta"> · retrieved {ago(s.retrieved_at_utc)}</span>}
                        {s.is_stale && <span className="badge badge--warn">Stale</span>}
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          )}
        </section>
      )}

      <TranscriptReview onSend={submit} />

      {!question && !text && open === false && (
        <div className="ask__suggestions" role="list">
          {SUGGESTIONS.slice(0, 3).map((s) => (
            <button key={s} type="button" role="listitem" className="chip ask__suggestion" onClick={() => submit(s)} disabled={backend !== 'online'}>
              {s}
            </button>
          ))}
        </div>
      )}

      <form
        className="ask__composer"
        onSubmit={(e) => {
          e.preventDefault();
          submit(text);
        }}
      >
        <MicButton />
        <input
          ref={input}
          className="ask__input"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onFocus={() => question && setOpen(true)}
          placeholder={backend === 'online' ? 'Ask the Earth…' : 'The local core is offline'}
          disabled={backend !== 'online'}
          aria-label="Ask the Earth"
          list="ask-earth-suggestions"
          maxLength={500}
        />
        <datalist id="ask-earth-suggestions">
          {SUGGESTIONS.map((s) => (
            <option key={s} value={s} />
          ))}
        </datalist>
        {pending ? (
          <button type="button" className="ask__send" onClick={cancel} aria-label="Stop">
            <Icon name="stop" size={14} strokeWidth={2.2} />
          </button>
        ) : (
          <button type="submit" className="ask__send" disabled={!text.trim() || backend !== 'online'} aria-label="Ask">
            <Icon name="send" size={15} />
          </button>
        )}
      </form>
      {answer && !pending && answer.createdAt && <span className="sr-only">Answered {ago(new Date(answer.createdAt).toISOString())}</span>}
    </div>
  );
};
