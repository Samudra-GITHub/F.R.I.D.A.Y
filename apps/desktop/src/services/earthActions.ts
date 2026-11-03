/**
 * The desktop side of the Earth action contract.
 *
 * Actions come from the backend (validated there) or from this app's own screens,
 * are checked again here, wait in a queue until the Earth screen can take them, and
 * are only reported as done when Earth sends back what really happened.
 */
import { useSyncExternalStore } from 'react';

export type Preset = 'global' | 'continent' | 'regional' | 'local' | 'street';
export type EarthLayer = 'earthquakes' | 'flights' | 'satellites' | 'military' | 'vessels' | 'fires' | 'cyclones' | 'weather';
export type RecordGroup = 'ask' | 'time' | 'compare' | 'investigate' | 'pulse';
export type RecordCategory = 'earthquake' | 'event' | 'disaster' | 'aircraft' | 'weather' | 'place';

export interface EarthRecord {
  id: string;
  category: RecordCategory;
  latitude: number;
  longitude: number;
  title: string;
  time_utc?: string;
  magnitude?: number;
  source: string;
  url?: string;
  distance_km?: number;
}

export type EarthAction =
  | { type: 'set_preset'; preset: Preset }
  | { type: 'focus'; latitude: number; longitude: number; preset?: Preset; label?: string }
  | { type: 'focus_user' }
  | { type: 'return_global' }
  | { type: 'set_layer'; layer: EarthLayer; enabled: boolean }
  | { type: 'show_records'; records: EarthRecord[]; group?: RecordGroup; label?: string }
  | { type: 'select_record'; id: string }
  | { type: 'select_aircraft' | 'select_satellite'; query: string }
  | { type: 'clear_selection' };

export interface ActionResult {
  type: string;
  ok: boolean;
  error?: string;
  drawn?: number;
}

const PRESETS: Preset[] = ['global', 'continent', 'regional', 'local', 'street'];
const LAYERS: EarthLayer[] = ['earthquakes', 'flights', 'satellites', 'military', 'vessels', 'fires', 'cyclones', 'weather'];
const GROUPS: RecordGroup[] = ['ask', 'time', 'compare', 'investigate', 'pulse'];
const QUERY = /^[A-Za-z0-9 ()/.-]{1,40}$/;
const MAX_RECORDS = 500;

const inRange = (v: unknown, limit: number): v is number => typeof v === 'number' && Number.isFinite(v) && Math.abs(v) <= limit;

/** One action checked against the contract, or null. Only known fields are kept. */
export function validateEarthAction(raw: unknown): EarthAction | null {
  if (!raw || typeof raw !== 'object') return null;
  const a = raw as Record<string, unknown>;
  switch (a.type) {
    case 'set_preset':
      return PRESETS.includes(a.preset as Preset) ? { type: 'set_preset', preset: a.preset as Preset } : null;
    case 'focus':
      if (!inRange(a.latitude, 90) || !inRange(a.longitude, 180)) return null;
      return {
        type: 'focus',
        latitude: a.latitude,
        longitude: a.longitude,
        preset: PRESETS.includes(a.preset as Preset) ? (a.preset as Preset) : 'regional',
      };
    case 'focus_user':
    case 'return_global':
    case 'clear_selection':
      return { type: a.type };
    case 'set_layer':
      return LAYERS.includes(a.layer as EarthLayer) && typeof a.enabled === 'boolean'
        ? { type: 'set_layer', layer: a.layer as EarthLayer, enabled: a.enabled }
        : null;
    case 'show_records':
      if (!Array.isArray(a.records) || a.records.length > MAX_RECORDS) return null;
      return {
        type: 'show_records',
        records: a.records as EarthRecord[],
        group: GROUPS.includes(a.group as RecordGroup) ? (a.group as RecordGroup) : 'ask',
        label: typeof a.label === 'string' ? a.label.slice(0, 120) : undefined,
      };
    case 'select_record':
      return typeof a.id === 'string' && a.id.length > 0 && a.id.length <= 120 ? { type: 'select_record', id: a.id } : null;
    case 'select_aircraft':
    case 'select_satellite':
      return typeof a.query === 'string' && QUERY.test(a.query) ? { type: a.type, query: a.query } : null;
    default:
      return null;
  }
}

/** Plain words for an action, for the "what Earth is doing" list. */
export function describeAction(a: EarthAction): string {
  switch (a.type) {
    case 'set_preset':
      return `Camera to ${a.preset}`;
    case 'focus':
      return `Fly to ${a.latitude.toFixed(2)}, ${a.longitude.toFixed(2)}`;
    case 'focus_user':
      return 'Fly to your position';
    case 'return_global':
      return 'Return to the whole planet';
    case 'set_layer':
      return `${a.enabled ? 'Turn on' : 'Turn off'} ${a.layer}`;
    case 'show_records':
      return `Show ${a.records.length} record${a.records.length === 1 ? '' : 's'}`;
    case 'select_record':
      return 'Select a record';
    case 'select_aircraft':
      return `Follow aircraft ${a.query}`;
    case 'select_satellite':
      return `Follow satellite ${a.query}`;
    case 'clear_selection':
      return 'Clear the selection';
  }
}

const TOOL_WORDS: Record<string, string> = {
  get_earthquakes: 'Earthquakes',
  get_weather: 'Weather',
  get_natural_events: 'Natural events',
  get_disaster_alerts: 'Disaster alerts',
  get_aircraft_nearby: 'Aircraft nearby',
  get_world_status: 'Provider status',
  get_device_location: 'Your location',
  control_earth: 'Earth view',
  get_local_time: 'Local time',
};

/** How the assistant read a request, from the arguments it actually ran tools with. */
export function describeToolCall(name: string, args: Record<string, unknown> = {}): string {
  const parts: string[] = [TOOL_WORDS[name] ?? name.replace(/_/g, ' ')];
  if (typeof args.min_magnitude === 'number') parts.push(`magnitude ${args.min_magnitude}+`);
  if (typeof args.days === 'number') parts.push(`past ${args.days} days`);
  if (typeof args.location_name === 'string') parts.push(args.location_name);
  if (typeof args.latitude === 'number' && typeof args.longitude === 'number' && typeof args.location_name !== 'string') {
    parts.push(`near ${args.latitude.toFixed(1)}, ${args.longitude.toFixed(1)}`);
  }
  if (typeof args.radius_nm === 'number') parts.push(`within ${args.radius_nm} nm`);
  if (typeof args.alert_level === 'string') parts.push(`${args.alert_level} alerts`);
  if (name === 'control_earth' && typeof args.action === 'string') parts.push(args.action.replace(/_/g, ' '));
  return parts.join(' · ');
}

// ---- The queue and its results ------------------------------------------------

export interface EarthBatch {
  id: string;
  label: string;
  actions: EarthAction[];
  state: 'waiting' | 'sent' | 'done';
  results?: ActionResult[];
}

let batches: EarthBatch[] = [];
const listeners = new Set<() => void>();
let counter = 0;
const emit = () => {
  batches = [...batches];
  listeners.forEach((l) => l());
};

/** Queue actions for Earth. Invalid ones are dropped here and listed as refused. */
export function queueEarthActions(rawActions: unknown[], label: string): string | null {
  const actions: EarthAction[] = [];
  const refused: ActionResult[] = [];
  for (const raw of rawActions) {
    const a = validateEarthAction(raw);
    if (a) actions.push(a);
    else refused.push({ type: String((raw as { type?: unknown })?.type ?? 'unknown'), ok: false, error: 'Refused: not a valid Earth action.' });
  }
  if (!actions.length && !refused.length) return null;
  const id = `earth-${Date.now().toString(36)}-${++counter}`;
  batches.push({ id, label, actions, state: actions.length ? 'waiting' : 'done', results: actions.length ? undefined : refused });
  if (batches.length > 40) batches = batches.slice(-40);
  emit();
  return id;
}

export function takeWaitingBatches(): EarthBatch[] {
  const waiting = batches.filter((b) => b.state === 'waiting');
  if (waiting.length) {
    batches = batches.map((b) => (b.state === 'waiting' ? { ...b, state: 'sent' } : b));
    emit();
  }
  return waiting;
}

export function recordBatchResults(id: string, results: unknown): void {
  const list = Array.isArray(results)
    ? results.slice(0, 20).map((r) => {
        const x = (r ?? {}) as Record<string, unknown>;
        return {
          type: String(x.type ?? '').slice(0, 30),
          ok: x.ok === true,
          error: typeof x.error === 'string' ? x.error.slice(0, 200) : undefined,
          drawn: typeof x.drawn === 'number' ? x.drawn : undefined,
        };
      })
    : [];
  let changed = false;
  batches = batches.map((b) => {
    if (b.id !== id) return b;
    changed = true;
    return { ...b, state: 'done', results: list };
  });
  if (changed) emit();
}

export function useEarthBatch(id: string | null | undefined): EarthBatch | undefined {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => (id ? batches.find((b) => b.id === id) : undefined)
  );
}

export function useEarthQueue(): EarthBatch[] {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => batches
  );
}

export function _resetEarthQueueForTest(): void {
  batches = [];
  counter = 0;
}
