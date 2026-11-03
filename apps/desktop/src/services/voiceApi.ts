/**
 * Local backend client (conversation, voice, memory, policy). All paths go through
 * the Vite /api proxy to 127.0.0.1:8000; nothing here talks to a remote service.
 */

import {
  AuditEvent,
  CapabilitiesResponse,
  ConsentKey,
  ConversationResponse,
  HealthInfo,
  MemoryItem,
  PendingApproval,
  STTTranscriptionResponse,
  TTSSynthesisResponse,
  VoiceConfigResponse,
} from '../types/voice';

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: init?.body ? { 'Content-Type': 'application/json', ...init.headers } : init?.headers,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      // FastAPI errors are JSON; a non-JSON 5xx comes from the dev proxy when the backend is down.
      if (res.status >= 500) detail = 'no response from the local backend. Is it running?';
    }
    throw new ApiError(`${res.status}: ${detail}`, res.status);
  }
  return res.json() as Promise<T>;
}

const post = <T>(path: string, body: unknown, signal?: AbortSignal) =>
  request<T>(path, { method: 'POST', body: JSON.stringify(body), signal });

// ---- Health -----------------------------------------------------------------
export const fetchHealth = () => request<HealthInfo>('/health');

// ---- Conversation -------------------------------------------------------------
export function sendChatMessage(
  message: string,
  conversationId?: string | null,
  requestId?: string | null,
  signal?: AbortSignal
): Promise<ConversationResponse> {
  return post<ConversationResponse>(
    '/chat',
    { message, conversation_id: conversationId || undefined, request_id: requestId || undefined },
    signal
  );
}

export const cancelChat = (requestId: string) => post<{ status: string }>('/chat/cancel', { request_id: requestId });

export async function resetConversation(conversationId?: string | null): Promise<void> {
  await post('/chat/reset', { conversation_id: conversationId || undefined });
}

// ---- Voice ----------------------------------------------------------------------
export const fetchVoiceConfig = () => request<VoiceConfigResponse>('/voice/config');

export const updateVoicePrivacy = (action: 'enable' | 'disable' | 'stop_playback') =>
  post<{ status: string; voice_enabled: boolean; current_state: string; details: string }>('/voice/privacy', { action });

/** `engine` names a local recognizer; omit it to use the backend's configured default. */
export const transcribeAudio = (audioBase64: string, engine?: string | null, audioFormat = 'wav', sampleRateHz = 16000) =>
  post<STTTranscriptionResponse>('/voice/transcribe', {
    audio_base64: audioBase64,
    audio_format: audioFormat,
    sample_rate_hz: sampleRateHz,
    engine: engine || undefined,
  });

export const synthesizeSpeech = (text: string, voiceName?: string | null) =>
  post<TTSSynthesisResponse>('/voice/synthesize', { text, voice_name: voiceName || undefined });

// ---- Memory ------------------------------------------------------------------------
export const listMemories = (q?: string) =>
  request<{ memories: MemoryItem[] }>(`/memories${q ? `?q=${encodeURIComponent(q)}` : ''}`).then((r) => r.memories);

export const createMemory = (kind: MemoryItem['kind'], content: string) =>
  post<{ memory: MemoryItem }>('/memories', { kind, content }).then((r) => r.memory);

export const updateMemory = (id: string, patch: { content?: string; kind?: MemoryItem['kind'] }) =>
  request<{ memory: MemoryItem }>(`/memories/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: JSON.stringify(patch),
  }).then((r) => r.memory);

export const deleteMemory = (id: string) =>
  request<{ status: string }>(`/memories/${encodeURIComponent(id)}`, { method: 'DELETE' });

// ---- Capabilities, consent, audit ---------------------------------------------------
export const fetchCapabilities = () => request<CapabilitiesResponse>('/capabilities');

export const setConsent = (consent: ConsentKey, enabled: boolean) =>
  post<{ consents: CapabilitiesResponse['consents'] }>('/policy/consent', { consent, enabled }).then((r) => r.consents);

export const fetchAudit = (limit = 100) => request<{ events: AuditEvent[] }>(`/audit?limit=${limit}`).then((r) => r.events);

// ---- Approvals ------------------------------------------------------------------------
export const decideApproval = (approvalId: string, decision: 'approve' | 'deny') =>
  post<{ approval: PendingApproval }>(`/approvals/${encodeURIComponent(approvalId)}/decision`, { decision }).then((r) => r.approval);
