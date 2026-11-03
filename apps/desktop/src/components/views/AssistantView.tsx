import React, { useEffect, useRef, useState } from 'react';
import { useApp, useAssistantPhase } from '../../context/AppProvider';
import { useVoice } from '../../context/VoiceContext';
import { ChatMessageItem, PendingApproval, ToolExecutionSummary } from '../../types/voice';
import { Markdown } from '../ui/Markdown';
import { Icon } from '../ui/Icon';
import { Presence } from '../ui/Presence';
import './AssistantView.css';

const SUGGESTIONS = [
  'What time is it?',
  'Show the strongest earthquakes today',
  'What’s the weather in Tokyo?',
  'List my workspace files',
];

const formatTime = (ms: number) => new Date(ms).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

const greeting = () => {
  const h = new Date().getHours();
  return h < 5 ? 'Working late' : h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening';
};

/** Ticks only while mounted, so elapsed time never re-renders the whole view. */
const Elapsed: React.FC<{ since: number }> = ({ since }) => {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 100);
    return () => window.clearInterval(t);
  }, []);
  return <span className="mono tabular">{((now - since) / 1000).toFixed(1)} s</span>;
};

/** Recording timer driven by the real capture start time. */
const RecordingTimer: React.FC<{ since: number }> = ({ since }) => {
  const [now, setNow] = useState(performance.now());
  useEffect(() => {
    const t = window.setInterval(() => setNow(performance.now()), 200);
    return () => window.clearInterval(t);
  }, []);
  const s = Math.max(0, Math.floor((now - since) / 1000));
  return <span className="mono tabular">{Math.floor(s / 60)}:{String(s % 60).padStart(2, '0')}</span>;
};

const TOOL_LABELS: Record<string, string> = { control_media: 'Press a media key' };

const ApprovalCard: React.FC<{ approval: PendingApproval; onDecide: (decision: 'approve' | 'deny') => void }> = ({ approval: a, onDecide }) => {
  const expired = a.status === 'pending' && Date.parse(a.expires_at) < Date.now();
  const status = expired ? 'expired' : a.status;
  const tone = status === 'succeeded' ? 'badge--ok' : status === 'pending' ? 'badge--warn' : status === 'executing' ? 'badge--info' : 'badge--danger';
  let resultText = '';
  if (a.result && status !== 'pending') {
    if (a.result.ok) {
      resultText = a.result.verified
        ? 'Done and verified.'
        : 'Sent, but not verified: ' + (a.result.verification_details ?? 'the outcome could not be checked.');
    } else if (status === 'outcome_unknown') {
      resultText = 'Outcome unknown: ' + a.result.error + '. It will not be retried automatically.';
    } else {
      resultText = 'Not completed: ' + a.result.error;
    }
  }
  return (
    <div className={'approval approval--' + status} role="group" aria-label="Action awaiting approval">
      <div className="approval__head">
        <Icon name="lock" size={14} />
        <span className="approval__title">{TOOL_LABELS[a.tool_name] ?? a.tool_name}</span>
        <span className={'badge ' + tone}>{status === 'pending' ? 'Needs approval' : status.replace(/_/g, ' ')}</span>
      </div>
      <dl className="approval__args">
        {Object.entries(a.arguments).map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd className="mono">{JSON.stringify(v)}</dd>
          </div>
        ))}
      </dl>
      {status === 'pending' && (
        <div className="approval__actions">
          <span className="small muted">
            Runs once, with exactly these arguments. Expires {new Date(a.expires_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}.
          </span>
          <span className="spacer" />
          <button type="button" className="btn btn--sm" onClick={() => onDecide('deny')}>
            Deny
          </button>
          <button type="button" className="btn btn--primary btn--sm" onClick={() => onDecide('approve')}>
            Approve once
          </button>
        </div>
      )}
      {status === 'executing' && (
        <p className="small muted row">
          <span className="spinner" /> Running…
        </p>
      )}
      {resultText && <p className="small approval__result">{resultText}</p>}
    </div>
  );
};

const toolState = (t: ToolExecutionSummary): { label: string; tone: string } => {
  if (!t.allowed) return { label: 'Denied', tone: 'danger' };
  if (!t.ok) return { label: 'Failed', tone: 'danger' };
  if (t.verified) return { label: 'Verified', tone: 'ok' };
  return { label: 'Unverified', tone: 'warn' };
};

const ToolTrace: React.FC<{ calls: ToolExecutionSummary[] }> = ({ calls }) => {
  const denied = calls.filter((c) => !c.allowed || !c.ok).length;
  return (
    <details className="trace">
      <summary>
        <Icon name="bolt" size={13} />
        {calls.length} tool {calls.length === 1 ? 'call' : 'calls'}
        {denied > 0 && <span className="trace__warn">· {denied} not completed</span>}
        <Icon name="chevronDown" size={13} className="trace__chev" />
      </summary>
      <ol className="trace__list">
        {calls.map((c, i) => {
          const s = toolState(c);
          return (
            <li key={i} className="trace__item">
              <span className="mono trace__name">{c.tool_name}</span>
              <span className={`badge badge--${s.tone}`}>{s.label}</span>
              {(c.error || c.details) && <p className="trace__detail">{c.error || c.details}</p>}
            </li>
          );
        })}
      </ol>
    </details>
  );
};

const StatusNotice: React.FC<{ msg: ChatMessageItem }> = ({ msg }) => {
  if (msg.status === 'ollama_unavailable')
    return (
      <div className="notice notice--warn">
        <Icon name="alert" size={15} />
        <div>
          <strong>The local model isn’t running.</strong> Start Ollama (<code>ollama serve</code>) and make sure the
          configured model is pulled, then send again.
        </div>
      </div>
    );
  if (msg.status === 'network_error')
    return (
      <div className="notice notice--danger">
        <Icon name="alert" size={15} />
        <div>
          <strong>Backend unreachable.</strong> {msg.error}
        </div>
      </div>
    );
  if (msg.status === 'turn_limit_reached')
    return (
      <div className="notice notice--warn">
        <Icon name="info" size={15} />
        <div>Stopped at the safety budget for steps or tool calls in one request.</div>
      </div>
    );
  if (msg.status === 'error' && msg.error)
    return (
      <div className="notice notice--danger">
        <Icon name="alert" size={15} />
        <div>{msg.error}</div>
      </div>
    );
  return null;
};

const Message: React.FC<{ msg: ChatMessageItem; onRetry?: () => void; onDecide?: (approvalId: string, d: 'approve' | 'deny') => void }> = ({
  msg,
  onRetry,
  onDecide,
}) => {
  if (msg.role === 'user') {
    return (
      <div className="msg msg--user">
        <div className="msg__bubble">{msg.content}</div>
        <div className="msg__meta">
          {msg.viaVoice && (
            <span className="msg__voice">
              <Icon name="mic" size={11} /> voice
            </span>
          )}
          {formatTime(msg.createdAt)}
        </div>
      </div>
    );
  }
  const failed = msg.status && msg.status !== 'ok';
  return (
    <div className={`msg msg--assistant ${failed ? 'msg--failed' : ''}`}>
      <div className="msg__avatar" aria-hidden="true" />
      <div className="msg__body">
        <StatusNotice msg={msg} />
        {msg.status !== 'network_error' && msg.status !== 'ollama_unavailable' && (
          <div className="msg__text">
            <Markdown text={msg.content} />
          </div>
        )}
        {msg.approvals?.map((a) => (
          <ApprovalCard key={a.approval_id} approval={a} onDecide={(d) => onDecide?.(a.approval_id, d)} />
        ))}
        {msg.toolCalls && msg.toolCalls.length > 0 && <ToolTrace calls={msg.toolCalls} />}
        {msg.sources && msg.sources.length > 0 && (
          <ul className="sources" aria-label="Sources">
            {msg.sources.map((s, i) => (
              <li key={i}>
                {s.url ? (
                  <a href={s.url} target="_blank" rel="noopener noreferrer" className="source" title={s.details || s.title}>
                    <Icon name="link" size={12} />
                    <span className="source__title">{s.title}</span>
                    {s.is_stale && <span className="badge badge--warn">Stale</span>}
                  </a>
                ) : (
                  <span className="source" title={s.details || s.title}>
                    <Icon name="cpu" size={12} />
                    <span className="source__title">{s.title}</span>
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
        <div className="msg__meta">
          {formatTime(msg.createdAt)}
          {msg.latencyMs !== undefined && <span className="mono">{(msg.latencyMs / 1000).toFixed(1)} s</span>}
          {failed && onRetry && (
            <button type="button" className="btn btn--ghost btn--sm" onClick={onRetry}>
              <Icon name="refresh" size={12} /> Retry
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

const TranscriptReview: React.FC<{ onSend: (text: string) => void }> = ({ onSend }) => {
  const { pending, setPendingText, discardPending, playPendingAudio } = useVoice();
  if (!pending) return null;
  const r = pending.result;
  const ok = r.status === 'ok';
  return (
    <section className="review" aria-label="Review transcript">
      <header className="review__head">
        <span className="eyebrow">{ok ? 'Review before sending' : 'Nothing recognized'}</span>
        <span className="review__meta mono">
          {r.duration_seconds != null && `${r.duration_seconds.toFixed(1)} s`}
          {r.confidence != null && ` · recognizer confidence ${Math.round(r.confidence * 100)}%`}
          {r.latency_ms != null && ` · ${r.latency_ms} ms`}
        </span>
      </header>
      <textarea
        className="field review__text"
        rows={2}
        value={pending.text}
        placeholder={ok ? '' : r.details || 'Type what you said, or record again.'}
        onChange={(e) => setPendingText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing && pending.text.trim()) {
            e.preventDefault();
            onSend(pending.text);
          }
        }}
        aria-label="Transcript"
        autoFocus
      />
      <div className="review__actions">
        {pending.audioUrl && (
          <button type="button" className="btn btn--ghost btn--sm" onClick={playPendingAudio}>
            <Icon name="play" size={12} /> Listen to recording
          </button>
        )}
        <span className="spacer" />
        <button type="button" className="btn btn--sm" onClick={discardPending}>
          Discard
        </button>
        <button type="button" className="btn btn--primary btn--sm" disabled={!pending.text.trim()} onClick={() => onSend(pending.text)}>
          Send <Icon name="send" size={12} />
        </button>
      </div>
      <p className="review__note">The recording stays in this window and is cleared when you send or discard it.</p>
    </section>
  );
};

const MicButton: React.FC = () => {
  const { isRecording, phase, startRecording, stopRecording, readLevel } = useVoice();
  const ref = useRef<HTMLButtonElement>(null);

  // Live input meter: writes a CSS variable each frame while recording, no React state.
  useEffect(() => {
    if (!isRecording) {
      ref.current?.style.setProperty('--level', '0');
      return;
    }
    let raf = 0;
    const loop = () => {
      const lvl = Math.min(1, readLevel() * 6);
      ref.current?.style.setProperty('--level', lvl.toFixed(3));
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [isRecording, readLevel]);

  const busy = phase === 'transcribing';
  return (
    <button
      ref={ref}
      type="button"
      className={`mic ${isRecording ? 'mic--live' : ''}`}
      onClick={isRecording ? stopRecording : startRecording}
      disabled={busy}
      aria-pressed={isRecording}
      aria-label={isRecording ? 'Stop recording and transcribe' : 'Start push-to-talk recording'}
      title={isRecording ? 'Stop and transcribe' : 'Push to talk'}
    >
      {busy ? <span className="spinner" /> : <Icon name={isRecording ? 'stop' : 'mic'} size={18} strokeWidth={isRecording ? 2.2 : 1.6} />}
    </button>
  );
};

export const AssistantView: React.FC = () => {
  const { messages, send, pendingSince, cancel, resetChat, backend, decide } = useApp();
  const voice = useVoice();
  const phase = useAssistantPhase();
  const [draft, setDraft] = useState('');
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const pending = pendingSince !== null;

  // Follow new messages only while the reader is at the bottom; otherwise offer a jump button.
  const atBottom = useRef(true);
  const [unseen, setUnseen] = useState(0);
  const scrollToEnd = () => {
    const el = listRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
    setUnseen(0);
  };
  useEffect(() => {
    if (atBottom.current) scrollToEnd();
    else setUnseen((n) => n + 1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages.length, pending]);
  useEffect(() => {
    if (voice.pending && atBottom.current) scrollToEnd();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [voice.pending]);

  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  }, [draft]);

  const submit = (text: string, viaVoice = false) => {
    if (!text.trim() || pending) return;
    send(text, { viaVoice });
    if (viaVoice) voice.discardPending();
    else setDraft('');
  };

  const lastUser = [...messages].reverse().find((m) => m.role === 'user');
  const empty = messages.length === 0;

  return (
    <div className="assistant">
      <div
        className="assistant__scroll"
        ref={listRef}
        onScroll={(e) => {
          const el = e.currentTarget;
          atBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
          if (atBottom.current && unseen) setUnseen(0);
        }}
      >
        {empty ? (
          <div className="assistant__hero">
            <Presence phase={phase} size={132} />
            <h2 className="assistant__greeting">{greeting()}.</h2>
            <p className="assistant__lede">
              Ask in text, or press the microphone to talk. Everything runs on this machine; tools only act within the
              permissions you’ve granted.
            </p>
            {backend === 'offline' && (
              <div className="notice notice--danger">
                <Icon name="alert" size={15} />
                <div>
                  The local backend isn’t reachable. Start it with{' '}
                  <code>uvicorn backend.friday.api.app:app --host 127.0.0.1 --port 8000</code>.
                </div>
              </div>
            )}
            <div className="assistant__suggestions">
              {SUGGESTIONS.map((s) => (
                <button key={s} type="button" className="chip" onClick={() => submit(s)} disabled={backend !== 'online'}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="thread" role="log" aria-live="polite" aria-label="Conversation">
            {messages.map((m, i) => (
              <Message
                key={m.id}
                msg={m}
                onRetry={i === messages.length - 1 && lastUser ? () => send(lastUser.content) : undefined}
                onDecide={(approvalId, d) => decide(m.id, approvalId, d)}
              />
            ))}
            {pending && (
              <div className="msg msg--assistant msg--working">
                <Presence phase="thinking" size={28} />
                <div className="working">
                  <span>Working on it</span>
                  <Elapsed since={pendingSince!} />
                  <button type="button" className="btn btn--ghost btn--sm" onClick={cancel}>
                    Stop
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="assistant__dock">
        {unseen > 0 && (
          <button type="button" className="chip assistant__jump" onClick={() => scrollToEnd()}>
            <Icon name="chevronDown" size={13} /> New messages
          </button>
        )}
        <TranscriptReview onSend={(t) => submit(t, true)} />
        {voice.voiceError && !voice.pending && (
          <div className="notice notice--warn dock__error" role="alert">
            <Icon name="alert" size={15} />
            <div>{voice.voiceError}</div>
            <button type="button" className="icon-btn icon-btn--sm" onClick={voice.clearVoiceError} aria-label="Dismiss">
              <Icon name="close" size={14} />
            </button>
          </div>
        )}
        <form
          className={`composer ${voice.isRecording ? 'composer--recording' : ''}`}
          onSubmit={(e) => {
            e.preventDefault();
            submit(draft);
          }}
        >
          <MicButton />
          {voice.isRecording ? (
            <div className="composer__recording" aria-live="polite">
              <span className="dot dot--accent dot--live" />
              <span>
                Recording {voice.recordingStartedAt !== null && <RecordingTimer since={voice.recordingStartedAt} />}. Press the button again when you’re done.
              </span>
              <button type="button" className="btn btn--ghost btn--sm" onClick={voice.cancelRecording}>
                Cancel
              </button>
            </div>
          ) : (
            <textarea
              ref={inputRef}
              className="composer__input"
              rows={1}
              placeholder={backend === 'online' ? 'Message W.E.D.N.E.S.D.A.Y.' : 'Backend offline'}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  submit(draft);
                }
              }}
              aria-label="Message"
            />
          )}
          <div className="composer__actions">
            <button
              type="button"
              className="icon-btn"
              aria-pressed={voice.outputEnabled}
              onClick={() => {
                if (voice.outputEnabled) voice.stopSpeaking();
                voice.setOutputEnabled(!voice.outputEnabled);
              }}
              title={voice.outputEnabled ? 'Spoken replies on' : 'Spoken replies off'}
              aria-label="Speak replies aloud"
            >
              <Icon name={voice.outputEnabled ? 'volume' : 'volumeOff'} size={18} />
            </button>
            {messages.length > 0 && (
              <button type="button" className="icon-btn" onClick={resetChat} title="New conversation" aria-label="New conversation">
                <Icon name="reset" size={17} />
              </button>
            )}
            {pending ? (
              <button type="button" className="send send--stop" onClick={cancel} aria-label="Stop request">
                <Icon name="stop" size={14} strokeWidth={2.4} />
              </button>
            ) : (
              <button type="submit" className="send" disabled={!draft.trim() || voice.isRecording} aria-label="Send">
                <Icon name="send" size={16} strokeWidth={2} />
              </button>
            )}
          </div>
        </form>
        <p className="composer__hint">
          <kbd>Enter</kbd> send · <kbd>Shift</kbd>+<kbd>Enter</kbd> new line · <kbd>Esc</kbd> stop
        </p>
      </div>
    </div>
  );
};
