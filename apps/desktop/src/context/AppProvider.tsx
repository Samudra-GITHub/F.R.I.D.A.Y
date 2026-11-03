import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { ChatMessageItem, HealthInfo, PendingApproval, SessionEvent } from '../types/voice';
import { cancelChat, decideApproval, fetchHealth, fetchTurnProgress, resetConversation, sendChatMessage } from '../services/voiceApi';
import { useVoice } from './VoiceContext';

const PROGRESS_POLL_MS = 600;

type BackendState = 'connecting' | 'online' | 'offline';

interface AppContextValue {
  backend: BackendState;
  health: HealthInfo | null;
  refreshHealth: () => Promise<void>;

  events: SessionEvent[];
  logEvent: (event: Omit<SessionEvent, 'id' | 'at'>) => void;
  clearEvents: () => void;

  messages: ChatMessageItem[];
  /** Epoch ms when the in-flight request started, or null when idle. */
  pendingSince: number | null;
  /** The tool the backend is running for the current request, or null. */
  runningTool: string | null;
  send: (text: string, opts?: { viaVoice?: boolean }) => Promise<void>;
  cancel: () => void;
  resetChat: () => Promise<void>;
  /** Approve or deny a pending action shown in the conversation. */
  decide: (messageId: string, approvalId: string, decision: 'approve' | 'deny') => Promise<void>;

  /** Stops speech, recording, and any in-flight request. Never depends on the model. */
  emergencyStop: () => void;
}

const AppContext = createContext<AppContextValue | undefined>(undefined);

export const useApp = (): AppContextValue => {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used within AppProvider');
  return ctx;
};

const newId = (prefix: string) =>
  `${prefix}_${typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : Math.random().toString(36).slice(2)}`;

const HEALTH_INTERVAL_MS = 15000;

export const AppProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const voice = useVoice();
  const [backend, setBackend] = useState<BackendState>('connecting');
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [events, setEvents] = useState<SessionEvent[]>([]);
  const [messages, setMessages] = useState<ChatMessageItem[]>([]);
  const [pendingSince, setPendingSince] = useState<number | null>(null);
  const [runningTool, setRunningTool] = useState<string | null>(null);

  const conversationId = useRef(newId('conv'));
  // Bumped on reset: replies from an older generation are dropped, never shown in the new chat.
  const generation = useRef(0);
  const inflight = useRef<{ requestId: string; controller: AbortController } | null>(null);

  const logEvent = useCallback((event: Omit<SessionEvent, 'id' | 'at'>) => {
    setEvents((prev) => [{ ...event, id: newId('ev'), at: Date.now() }, ...prev].slice(0, 300));
  }, []);

  const refreshHealth = useCallback(async () => {
    try {
      const h = await fetchHealth();
      setHealth(h);
      setBackend('online');
    } catch {
      setBackend('offline');
    }
  }, []);

  useEffect(() => {
    refreshHealth();
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') refreshHealth();
    }, HEALTH_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [refreshHealth]);

  const { outputEnabled, speak } = voice;

  const send = useCallback(
    async (text: string, opts?: { viaVoice?: boolean }) => {
      const trimmed = text.trim();
      if (!trimmed || inflight.current) return;
      const gen = generation.current;
      const started = Date.now();
      setMessages((prev) => [
        ...prev,
        { id: newId('msg'), role: 'user', content: trimmed, createdAt: started, viaVoice: opts?.viaVoice },
      ]);
      const requestId = newId('req');
      const controller = new AbortController();
      inflight.current = { requestId, controller };
      setPendingSince(started);
      // The reply arrives all at once, so ask the backend what it's doing meanwhile.
      const progressTimer = window.setInterval(async () => {
        const progress = await fetchTurnProgress(requestId, controller.signal);
        if (inflight.current?.requestId !== requestId) return;
        setRunningTool(progress?.phase === 'executing' ? progress.tool : null);
      }, PROGRESS_POLL_MS);

      try {
        const data = await sendChatMessage(trimmed, conversationId.current, requestId, controller.signal);
        if (gen !== generation.current) return;
        const latencyMs = Date.now() - started;
        setMessages((prev) => [
          ...prev,
          {
            id: newId('msg'),
            role: 'assistant',
            content: data.response,
            createdAt: Date.now(),
            sources: data.sources ?? [],
            toolCalls: data.tool_calls ?? [],
            status: data.status,
            error: data.error,
            latencyMs,
            approvals: data.approvals ?? [],
          },
        ]);
        logEvent({
          kind: 'conversation',
          title: data.status === 'ok' ? 'Reply received' : `Reply: ${data.status.replace(/_/g, ' ')}`,
          details: `${(data.tool_calls ?? []).length} tool call(s) · ${(latencyMs / 1000).toFixed(1)} s`,
          outcome: data.status === 'ok' ? 'ok' : data.status === 'cancelled' ? 'cancelled' : 'failed',
        });
        if (outputEnabled && data.status === 'ok' && data.response) speak(data.response);
      } catch (err) {
        if (gen !== generation.current) return;
        const aborted = controller.signal.aborted;
        const msg = err instanceof Error ? err.message : String(err);
        setMessages((prev) => [
          ...prev,
          {
            id: newId('msg'),
            role: 'assistant',
            content: aborted
              ? 'Stopped. The request was cancelled before a reply arrived.'
              : 'The local backend did not respond, so no reply was produced.',
            createdAt: Date.now(),
            status: aborted ? 'cancelled' : 'network_error',
            error: aborted ? null : msg,
          },
        ]);
        logEvent({
          kind: 'conversation',
          title: aborted ? 'Request cancelled' : 'Request failed',
          details: aborted ? undefined : msg,
          outcome: aborted ? 'cancelled' : 'failed',
        });
      } finally {
        window.clearInterval(progressTimer);
        setRunningTool(null);
        if (inflight.current?.requestId === requestId) {
          inflight.current = null;
          setPendingSince(null);
        }
      }
    },
    [logEvent, outputEnabled, speak]
  );

  const cancel = useCallback(() => {
    const current = inflight.current;
    if (!current) return;
    // Tell the backend first so it stops before the next tool dispatch, then drop the response.
    cancelChat(current.requestId).catch(() => {});
    current.controller.abort();
  }, []);

  const resetChat = useCallback(async () => {
    generation.current++;
    cancel();
    inflight.current = null;
    setPendingSince(null);
    voice.stopSpeaking();
    setMessages([]);
    const old = conversationId.current;
    conversationId.current = newId('conv');
    try {
      await resetConversation(old);
    } catch {
      /* the new conversation id already isolates history */
    }
    logEvent({ kind: 'conversation', title: 'Conversation cleared', outcome: 'info' });
  }, [cancel, logEvent, voice]);

  const decide = useCallback(
    async (messageId: string, approvalId: string, decision: 'approve' | 'deny') => {
      const patch = (fn: (a: PendingApproval) => PendingApproval) =>
        setMessages((prev) =>
          prev.map((m) =>
            m.id === messageId ? { ...m, approvals: m.approvals?.map((a) => (a.approval_id === approvalId ? fn(a) : a)) } : m
          )
        );
      if (decision === 'approve') patch((a) => ({ ...a, status: 'executing' }));
      try {
        const updated = await decideApproval(approvalId, decision);
        patch(() => updated);
        logEvent({
          kind: 'system',
          title: `${decision === 'approve' ? 'Approved' : 'Denied'}: ${updated.tool_name}`,
          details: `Result: ${updated.status.replace(/_/g, ' ')}`,
          outcome: updated.status === 'succeeded' ? 'ok' : updated.status === 'denied' ? 'denied' : updated.status === 'failed' ? 'failed' : 'info',
        });
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        // 409 means it was already decided or expired; show that state rather than retrying.
        patch((a) => ({ ...a, status: msg.startsWith('409') && msg.includes('expired') ? 'expired' : a.status === 'executing' ? 'pending' : a.status, result: { ok: false, error: msg } }));
      }
    },
    [logEvent]
  );

  const emergencyStop = useCallback(() => {
    const hadWork = Boolean(inflight.current) || voice.isRecording || voice.isSpeaking;
    cancel();
    voice.stopAll();
    if (hadWork) logEvent({ kind: 'system', title: 'Stop pressed', details: 'Speech, recording and pending request halted', outcome: 'cancelled' });
  }, [cancel, logEvent, voice]);

  const value = useMemo<AppContextValue>(
    () => ({
      backend,
      health,
      refreshHealth,
      events,
      logEvent,
      clearEvents: () => setEvents([]),
      messages,
      pendingSince,
      runningTool,
      send,
      cancel,
      resetChat,
      decide,
      emergencyStop,
    }),
    [backend, health, refreshHealth, events, logEvent, messages, pendingSince, runningTool, send, cancel, resetChat, decide, emergencyStop]
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
};

/** The single assistant phase shown by the presence mark and status line. */
export const useAssistantPhase = (): import('../types/voice').AssistantPhase => {
  const { backend, pendingSince, messages, runningTool } = useApp();
  const voice = useVoice();
  if (voice.phase === 'listening') return 'listening';
  if (voice.phase === 'transcribing') return 'transcribing';
  if (runningTool || messages.some((m) => m.approvals?.some((a) => a.status === 'executing'))) return 'executing';
  if (pendingSince !== null) return 'thinking';
  if (voice.isSpeaking) return 'speaking';
  if (voice.pending) return 'reviewing';
  if (backend === 'offline') return 'error';
  return 'idle';
};
