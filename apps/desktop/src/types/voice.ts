/**
 * Voice, conversation, and shell types for W.E.D.N.E.S.D.A.Y. — mirrors schemas/contracts.py.
 */

/** What the assistant is doing right now; drives the presence indicator and status line. */
export type AssistantPhase =
  | 'idle'
  | 'listening'      // microphone open (push-to-talk)
  | 'transcribing'   // local recognizer running
  | 'reviewing'      // transcript waiting for the user to send or discard
  | 'thinking'       // the local model is working
  | 'retrieving'     // a read tool is fetching data
  | 'awaiting'       // an action waits for the user's approval
  | 'executing'      // an action the user approved is running
  | 'speaking'       // local TTS playback
  | 'error';

export type NavTab = 'assistant' | 'earth' | 'intelligence' | 'activity' | 'memory' | 'tools' | 'settings' | 'diagnostics';

export interface SourceReference {
  title: string;
  url?: string | null;
  publisher?: string | null;
  retrieved_at_utc?: string | null;
  is_stale?: boolean;
  details?: string | null;
}

export interface ToolExecutionSummary {
  tool_name: string;
  ok: boolean;
  verified: boolean;
  allowed: boolean;
  error?: string | null;
  details?: string | null;
  /** The arguments the tool ran with, so the user can see how the request was read. */
  arguments?: Record<string, unknown>;
}

export type ConversationStatus = 'ok' | 'ollama_unavailable' | 'turn_limit_reached' | 'cancelled' | 'error';

export interface ConversationResponse {
  response: string;
  model: string;
  conversation_id?: string | null;
  request_id?: string | null;
  sources: SourceReference[];
  tool_calls: ToolExecutionSummary[];
  status: ConversationStatus;
  error?: string | null;
  approvals?: PendingApproval[];
  /** Validated Earth view requests; the Earth screen confirms each one. */
  earth_actions?: unknown[];
  /** Records the answer names that no tool returned. */
  unmatched_mentions?: string[];
}

export type ApprovalStatus = 'pending' | 'executing' | 'succeeded' | 'failed' | 'outcome_unknown' | 'denied' | 'expired';

/** A side-effecting action the model proposed that only runs if the user approves these exact arguments. */
export interface PendingApproval {
  approval_id: string;
  conversation_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  args_digest: string;
  reason: string;
  status: ApprovalStatus;
  created_at: string;
  expires_at: string;
  result?: { ok: boolean; verified?: boolean; verification_details?: string | null; error?: string; output?: unknown } | null;
}

export interface ChatMessageItem {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  createdAt: number;
  sources?: SourceReference[];
  toolCalls?: ToolExecutionSummary[];
  status?: ConversationStatus | 'network_error';
  error?: string | null;
  /** Time from send to reply, measured in the browser. */
  latencyMs?: number;
  /** Set on user messages that came from a voice transcript. */
  viaVoice?: boolean;
  approvals?: PendingApproval[];
  /** The Earth batch this reply sent, whose results come from the Earth screen. */
  earthBatchId?: string | null;
  /** Records the answer names that no tool returned, found by the backend. */
  unmatchedMentions?: string[];
}

export interface STTTranscriptionResponse {
  status: 'ok' | 'empty_transcript' | 'model_not_installed' | 'transcription_error' | 'format_unsupported';
  transcript: string;
  duration_seconds?: number | null;
  detected_sample_rate?: number | null;
  detected_channels?: number | null;
  audio_size_bytes?: number | null;
  confidence?: number | null;
  peak_amplitude?: number | null;
  rms_amplitude?: number | null;
  silent_samples_ratio?: number | null;
  audio_samples_count?: number | null;
  clipped_ratio?: number | null;
  speech_duration_seconds?: number | null;
  segment_count?: number | null;
  latency_ms?: number | null;
  engine?: string | null;
  details?: string | null;
}

export interface TTSSynthesisResponse {
  status: 'ok' | 'model_not_installed' | 'disabled' | 'error';
  audio_base64?: string | null;
  audio_format?: string;
  duration_seconds?: number | null;
  details?: string | null;
}

export interface VoiceConfigResponse {
  voice_enabled: boolean;
  stt_available: boolean;
  tts_available: boolean;
  stt_engine: string;
  tts_engine: string;
  available_voices: string[];
  available_stt_engines?: string[];
  installed_speech_packs?: string[];
  wake_word_active: boolean;
}

/** A transcript awaiting the user's decision; the audio never leaves the browser except to the local backend. */
export interface PendingTranscript {
  text: string;
  audioUrl: string | null;
  result: STTTranscriptionResponse;
  clientRoundTripMs: number;
}

export interface VoiceContextValue {
  phase: 'idle' | 'listening' | 'transcribing' | 'speaking';
  /** Microphone, recognizer, or playback error to show the user. */
  voiceError: string | null;
  clearVoiceError: () => void;

  // Push-to-talk
  isRecording: boolean;
  /** performance.now() when the current recording started, for the on-screen timer. */
  recordingStartedAt: number | null;
  startRecording: () => Promise<void>;
  stopRecording: () => Promise<void>;
  cancelRecording: () => void;
  /** Live input level 0..1, read in rAF loops (not React state). */
  readLevel: () => number;
  pending: PendingTranscript | null;
  setPendingText: (text: string) => void;
  discardPending: () => void;
  playPendingAudio: () => void;

  // Speech output
  outputEnabled: boolean;
  setOutputEnabled: (enabled: boolean) => void;
  isSpeaking: boolean;
  speak: (text: string) => Promise<void>;
  stopSpeaking: () => void;

  // Devices and engine
  config: VoiceConfigResponse | null;
  configError: string | null;
  refreshConfig: () => Promise<void>;
  voices: string[];
  selectedVoice: string | null;
  setSelectedVoice: (voice: string | null) => void;
  /** Recognizers the backend can run right now. */
  sttEngines: string[];
  /** The user's choice; null means the backend's configured default. */
  selectedEngine: string | null;
  setSelectedEngine: (engine: string | null) => void;
  microphones: MediaDeviceInfo[];
  selectedMicrophone: string | null;
  setSelectedMicrophone: (deviceId: string | null) => void;
  refreshMicrophones: () => Promise<void>;

  /** Stop recording and speech immediately. Independent of the model. */
  stopAll: () => void;
}

/** A UI-side event recorded for this session (not persisted). */
export interface SessionEvent {
  id: string;
  at: number;
  kind: 'conversation' | 'voice' | 'world' | 'location' | 'system';
  title: string;
  details?: string;
  outcome: 'ok' | 'denied' | 'failed' | 'info' | 'cancelled';
}

export interface AuditEvent {
  seq: number;
  at_utc: string;
  kind: 'decision' | 'consent' | 'memory';
  tool: string;
  outcome: string;
  reason: string;
  args_digest: string | null;
}

export interface MemoryItem {
  id: string;
  kind: 'preference' | 'profile' | 'project' | 'decision' | 'procedure' | 'fact';
  content: string;
  scope: string;
  source_kind: 'explicit_user_statement' | 'user_correction' | 'imported' | 'model_suggestion';
  source_reference: string | null;
  status: 'active' | 'deleted' | 'expired';
  created_at: string;
  updated_at: string;
  expires_at: string | null;
}

export interface CapabilityTool {
  name: string;
  description: string;
  permission: string;
  permitted: boolean;
  parameters: Record<string, unknown>;
}

export type ConsentKey = 'media_control' | 'location_read' | 'places_search' | 'world_read';

export interface CapabilitiesResponse {
  tools: CapabilityTool[];
  consents: Record<ConsentKey, boolean>;
}

export interface HealthInfo {
  status: string;
  version: string;
  model: string;
  ollama_reachable: boolean;
  workspace_root: string;
  media_control_enabled: boolean;
  location_read_enabled: boolean;
  location_tracking_enabled: boolean;
  places_search_enabled: boolean;
  world_read_enabled: boolean;
}
