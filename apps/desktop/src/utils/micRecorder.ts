/**
 * One push-to-talk microphone recorder shared by the Assistant and the Voice Lab.
 *
 * Captures raw Float32 PCM at the device's native rate. Nothing is recorded until
 * start() is called by a user gesture, and every track is stopped on stop()/cancel().
 * Audio stays in memory; callers decide whether to send or discard it.
 */

export interface RecordingResult {
  samples: Float32Array;
  sampleRate: number;
  deviceLabel: string | null;
  trackSettings: MediaTrackSettings | null;
}

export interface CaptureOptions {
  deviceId?: string | null;
  /** Browser DSP. Defaults on: echo cancellation stops the assistant's own voice being captured. */
  echoCancellation?: boolean;
  noiseSuppression?: boolean;
  autoGainControl?: boolean;
}

/** Time to keep capturing after the user stops, so the last syllable is not clipped. */
const TAIL_MS = 220;

/** Batches the audio thread's 128-sample blocks into chunks of about 43 ms at 48 kHz. */
const CAPTURE_WORKLET = `
class FridayCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = new Float32Array(2048);
    this.filled = 0;
  }
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel) {
      let offset = 0;
      while (offset < channel.length) {
        const n = Math.min(channel.length - offset, this.buffer.length - this.filled);
        this.buffer.set(channel.subarray(offset, offset + n), this.filled);
        this.filled += n;
        offset += n;
        if (this.filled === this.buffer.length) {
          this.port.postMessage(this.buffer);
          this.buffer = new Float32Array(2048);
          this.filled = 0;
        }
      }
    }
    return true;
  }
}
registerProcessor('friday-capture', FridayCapture);
`;

export class MicRecorder {
  private stream: MediaStream | null = null;
  private ctx: AudioContext | null = null;
  private processor: AudioWorkletNode | ScriptProcessorNode | null = null;
  private chunks: Float32Array[] = [];
  /** Latest RMS level 0..1 of the incoming signal, for meters. Not React state. */
  level = 0;
  peak = 0;

  get active(): boolean {
    return this.stream !== null;
  }

  async start(options: CaptureOptions = {}): Promise<void> {
    if (this.active) return;
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error('Microphone capture is not supported in this browser.');
    }
    const constraints: MediaTrackConstraints = {
      channelCount: 1,
      echoCancellation: options.echoCancellation ?? true,
      noiseSuppression: options.noiseSuppression ?? true,
      autoGainControl: options.autoGainControl ?? true,
    };
    if (options.deviceId) constraints.deviceId = { exact: options.deviceId };

    this.chunks = [];
    this.level = 0;
    this.peak = 0;
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: constraints });
    try {
      const Ctx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      this.ctx = new Ctx();
      if (this.ctx.state === 'suspended') await this.ctx.resume();
      const source = this.ctx.createMediaStreamSource(this.stream);
      // Route through a silent gain node: the capture node only runs when connected to the
      // destination, and a direct connection would play the microphone through the speakers.
      const mute = this.ctx.createGain();
      mute.gain.value = 0;
      mute.connect(this.ctx.destination);
      if (this.ctx.audioWorklet) {
        // Runs on the audio thread, so a busy page (or CPU) can't drop samples.
        const moduleUrl = URL.createObjectURL(new Blob([CAPTURE_WORKLET], { type: 'text/javascript' }));
        try {
          await this.ctx.audioWorklet.addModule(moduleUrl);
        } finally {
          URL.revokeObjectURL(moduleUrl);
        }
        const node = new AudioWorkletNode(this.ctx, 'friday-capture', { numberOfInputs: 1, numberOfOutputs: 1, outputChannelCount: [1] });
        node.port.onmessage = (e: MessageEvent<Float32Array>) => this.accept(e.data);
        this.processor = node;
      } else {
        const node = this.ctx.createScriptProcessor(2048, 1, 1);
        node.onaudioprocess = (e) => this.accept(new Float32Array(e.inputBuffer.getChannelData(0)));
        this.processor = node;
      }
      source.connect(this.processor);
      this.processor.connect(mute);
    } catch (err) {
      this.teardown();
      throw err;
    }
  }

  async stop(): Promise<RecordingResult> {
    if (!this.active || !this.ctx) throw new Error('Not recording.');
    await new Promise((r) => setTimeout(r, TAIL_MS));
    const sampleRate = this.ctx.sampleRate;
    const track = this.stream?.getAudioTracks()[0] ?? null;
    const deviceLabel = track?.label || null;
    const trackSettings = track?.getSettings?.() ?? null;
    const chunks = this.chunks;
    this.teardown();

    const total = chunks.reduce((n, c) => n + c.length, 0);
    const samples = new Float32Array(total);
    let offset = 0;
    for (const c of chunks) {
      samples.set(c, offset);
      offset += c.length;
    }
    return { samples, sampleRate, deviceLabel, trackSettings };
  }

  cancel(): void {
    this.teardown();
    this.chunks = [];
  }

  private accept(chunk: Float32Array): void {
    this.chunks.push(chunk);
    let sum = 0;
    let pk = 0;
    for (let i = 0; i < chunk.length; i++) {
      const v = chunk[i];
      sum += v * v;
      const a = v < 0 ? -v : v;
      if (a > pk) pk = a;
    }
    this.level = Math.sqrt(sum / chunk.length);
    if (pk > this.peak) this.peak = pk;
  }

  private teardown(): void {
    if (this.processor) {
      if (this.processor instanceof ScriptProcessorNode) this.processor.onaudioprocess = null;
      else this.processor.port.onmessage = null;
      try {
        this.processor.disconnect();
      } catch {
        /* already disconnected */
      }
      this.processor = null;
    }
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
    if (this.ctx && this.ctx.state !== 'closed') this.ctx.close().catch(() => {});
    this.ctx = null;
    this.level = 0;
  }
}

/** The Claude desktop app's built-in browser pane blocks microphone capture by design. */
export const isEmbeddedAppBrowser = (ua: string = navigator.userAgent): boolean => /\bClaude\//.test(ua);

export const EMBEDDED_MIC_MESSAGE =
  'This built-in browser pane blocks the microphone. Open W.E.D.N.E.S.D.A.Y. in Chrome or Edge to record.';

/** Turns a getUserMedia failure into a message that says what to do next. */
export function describeMicError(err: unknown, ua?: string): string {
  const name = (err as { name?: string } | null)?.name ?? '';
  switch (name) {
    case 'NotAllowedError':
    case 'SecurityError':
      if (isEmbeddedAppBrowser(ua)) return EMBEDDED_MIC_MESSAGE;
      return 'Microphone access is blocked for this page. Allow it from the icon at the left of the address bar, then reload. If it stays blocked, check Windows Settings → Privacy & security → Microphone.';
    case 'NotFoundError':
    case 'OverconstrainedError':
      return 'The selected microphone is not available. Choose another input in Settings → Voice, or check that it is plugged in.';
    case 'NotReadableError':
    case 'AbortError':
      return 'Windows could not open the microphone. Another app may be using it exclusively; close that app and try again.';
    default:
      return `Could not open the microphone: ${err instanceof Error ? err.message : String(err)}`;
  }
}

export type MicAccess = 'granted' | 'prompt' | 'denied' | 'unknown';

/** Reads the permission state without prompting and without opening the microphone. */
export async function microphoneAccess(): Promise<MicAccess> {
  try {
    const status = await navigator.permissions.query({ name: 'microphone' as PermissionName });
    return status.state;
  } catch {
    return 'unknown';
  }
}

export async function listMicrophones(): Promise<MediaDeviceInfo[]> {
  if (!navigator.mediaDevices?.enumerateDevices) return [];
  const devices = await navigator.mediaDevices.enumerateDevices();
  return devices.filter((d) => d.kind === 'audioinput');
}
