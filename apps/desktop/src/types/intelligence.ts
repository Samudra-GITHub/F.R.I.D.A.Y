/**
 * World Intelligence System — Data Contracts and Layer Types
 * All coordinates, layers, and fixtures adhere to these interfaces.
 */

export type IntelligenceLayerId = 'events' | 'seismic' | 'weather' | 'orbital';

export interface IntelligenceLayerConfig {
  id: IntelligenceLayerId;
  name: string;
  description: string;
  color: string;
  enabled: boolean;
  itemCount: number;
  status: 'active_fixture' | 'live_pending' | 'offline';
}

export interface GeoLocation {
  lat: number;
  lng: number;
  city?: string;
  country?: string;
  region?: string;
}

export interface WorldEventMarker {
  id: string;
  title: string;
  category: 'geopolitics' | 'science_tech' | 'humanitarian' | 'economy';
  lat: number;
  lng: number;
  locationName: string;
  timestamp: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  summary: string;
  source: string;
  isSimulatedFixture: true; // Explicitly declared
  verificationStatus: 'unverified_fixture' | 'verified_live';
  details?: string;
  metrics?: Record<string, string | number>;
}

export interface SeismicEventMarker {
  id: string;
  magnitude: number;
  lat: number;
  lng: number;
  depthKm: number;
  place: string;
  timestamp: string;
  isSimulatedFixture: true;
  tsunamiAlert: boolean;
}

export interface WeatherTelemetry {
  locationName: string;
  lat: number;
  lng: number;
  temperatureC: number;
  feelsLikeC: number;
  condition: string;
  humidityPercent: number;
  windSpeedKmh: number;
  barometricPressureHpa: number;
  uvIndex: number;
  forecastSummary: string;
  isSimulatedFixture: true;
}

export interface OrbitalEventMarker {
  id: string;
  name: string;
  type: 'satellite' | 'space_station' | 'launch_site' | 'astronomy';
  lat: number;
  lng: number;
  altitudeKm: number;
  velocityKmS?: number;
  operator?: string;
  isSimulatedFixture: true;
}

export interface IntelligenceDossier {
  title: string;
  subtitle: string;
  coordinates: GeoLocation;
  timestamp: string;
  confidenceScore: number; // 0.0 to 1.0
  summary: string;
  primaryEvidence: string[];
  recommendedInvestigations: string[];
  isSimulatedFixture: boolean;
  layerId: IntelligenceLayerId;
}

/**
 * Everything the World Intelligence screen can display. Today it is always a
 * sample fixture set; the Phase 3 live gateway will supply the same shape.
 */
export interface IntelligenceDataset {
  events: WorldEventMarker[];
  seismic: SeismicEventMarker[];
  weather: Record<string, WeatherTelemetry>;
  orbital: OrbitalEventMarker[];
}

export type DeviceFixStatus =
  | 'fresh'
  | 'stale'
  | 'unavailable'
  | 'denied'
  | 'error'
  | 'disabled'
  | 'initializing';

export interface DeviceLocationFix {
  latitude?: number | null;
  longitude?: number | null;
  accuracy_m?: number | null;
  timestamp_utc?: string | null;
  status: DeviceFixStatus;
  windows_status?: string | null;
  provider: string;
  is_stale: boolean;
  details?: string | null;
}

export type LocationMode = 'off' | 'once' | 'continuous';

export interface LocationServiceStatus {
  mode?: LocationMode;
  tracking_enabled: boolean;
  is_paused: boolean;
  worker_running: boolean;
  worker_pid?: number | null;
  update_interval_s: number;
  latest_fix?: DeviceLocationFix | null;
  details?: string | null;
}

export interface GeocodedAddress {
  formatted_address: string;
  street_number?: string | null;
  route?: string | null;
  locality?: string | null;
  sublocality?: string | null;
  admin_area?: string | null;
  country?: string | null;
  postal_code?: string | null;
  place_id?: string | null;
}

export interface ReverseGeocodeResponse {
  status: string;
  latitude?: number | null;
  longitude?: number | null;
  address?: GeocodedAddress | null;
  provider: string;
  osm_uri?: string | null;
  attribution?: string | null;
  details?: string | null;
}

export interface PlaceSummary {
  id: string;
  name: string;
  formatted_address?: string | null;
  latitude: number;
  longitude: number;
  types: string[];
  rating?: number | null;
  distance_m?: number | null;
  google_maps_uri?: string | null;
  osm_uri?: string | null;
  attribution?: string | null;
}

export interface NearbySearchResponse {
  status: string;
  query?: string | null;
  category?: string | null;
  center_lat?: number | null;
  center_lng?: number | null;
  radius_m: number;
  places: PlaceSummary[];
  provider: string;
  attribution?: string | null;
  details?: string | null;
}

// ============================================================================
// World feeds — mirrors schemas/contracts.py exactly (ProviderStatus, *Record, *Response)
// ============================================================================

export type ProviderStatusCode = 'ok' | 'empty' | 'stale' | 'rate_limited' | 'timeout' | 'provider_error' | 'not_configured';

export interface FeedEnvelope {
  status: ProviderStatusCode;
  provider: string;
  attribution: string;
  /** ISO-8601 UTC time the backend retrieved (or served from cache) this data. */
  retrieved_at: string;
  is_stale: boolean;
  details?: string | null;
}

export interface EarthquakeRecord {
  id: string;
  title: string;
  magnitude: number;
  place: string;
  latitude: number;
  longitude: number;
  depth_km: number;
  time_utc: string;
  updated_utc?: string | null;
  url?: string | null;
  tsunami_alert: boolean;
  felt_reports?: number | null;
  /** USGS PAGER level: green, yellow, orange, red. */
  alert_level?: string | null;
}

export interface EarthquakesResponse extends FeedEnvelope {
  count: number;
  earthquakes: EarthquakeRecord[];
}

export interface WeatherDailyForecast {
  date: string;
  max_temp_c?: number | null;
  min_temp_c?: number | null;
  condition?: string | null;
}

export interface WeatherConditionRecord {
  latitude: number;
  longitude: number;
  location_name?: string | null;
  temperature_c: number;
  feels_like_c: number;
  condition: string;
  weather_code: number;
  humidity_percent: number;
  wind_speed_kmh: number;
  wind_direction_deg: number;
  precipitation_mm: number;
  is_day: boolean;
  forecast_summary?: string | null;
  daily_forecasts: WeatherDailyForecast[];
  /** Model time in the location's local timezone (no offset suffix). */
  source_time_utc: string;
}

export interface WeatherResponse extends FeedEnvelope {
  weather?: WeatherConditionRecord | null;
}

export interface NaturalEventRecord {
  id: string;
  title: string;
  category: string;
  category_title: string;
  latitude: number;
  longitude: number;
  timestamp_utc: string;
  source_url?: string | null;
  description?: string | null;
  geometry_type: string;
  is_closed: boolean;
}

export interface NaturalEventsResponse extends FeedEnvelope {
  count: number;
  events: NaturalEventRecord[];
}

export interface DisasterRecord {
  id: string;
  title: string;
  event_type: string;
  alert_level: string;
  severity?: string | null;
  latitude: number;
  longitude: number;
  country?: string | null;
  /** RFC 2822 or ISO date string, as published by GDACS. */
  timestamp_utc: string;
  url?: string | null;
  details?: string | null;
}

export interface DisastersResponse extends FeedEnvelope {
  count: number;
  disasters: DisasterRecord[];
}

export interface NewsArticleRecord {
  id: string;
  title: string;
  publisher: string;
  url: string;
  published_at_utc: string;
  summary?: string | null;
}

export interface NewsResponse extends FeedEnvelope {
  count: number;
  articles: NewsArticleRecord[];
}

export interface ProviderHealth {
  provider: string;
  status: ProviderStatusCode;
  last_successful_retrieval?: string | null;
  is_stale: boolean;
  cached_items_count: number;
  error_message?: string | null;
}

export interface WorldStatusResponse {
  status: string;
  providers: Record<string, ProviderHealth>;
  retrieved_at: string;
}

export interface SatelliteRecord {
  norad_id: number;
  name: string;
  group: string;
  latitude: number;
  longitude: number;
  altitude_km: number;
  velocity_kms: number;
  inclination_deg: number;
  period_min: number;
  orbit_class: 'LEO' | 'MEO' | 'GEO' | 'HEO';
  elements_epoch_utc: string;
}

export interface SatellitesResponse extends FeedEnvelope {
  count: number;
  satellites: SatelliteRecord[];
  positions_at: string;
}

export interface SatelliteTrackResponse extends FeedEnvelope {
  norad_id: number;
  name?: string | null;
  points: [number, number, number][];
}

export interface FlightRecord {
  hex: string;
  callsign?: string | null;
  registration?: string | null;
  aircraft_type?: string | null;
  latitude: number;
  longitude: number;
  altitude_ft?: number | null;
  on_ground: boolean;
  ground_speed_kt?: number | null;
  track_deg?: number | null;
  vertical_rate_fpm?: number | null;
  squawk?: string | null;
  emergency?: string | null;
  position_source?: string | null;
  position_age_s?: number | null;
}

export interface FlightsResponse extends FeedEnvelope {
  count: number;
  flights: FlightRecord[];
  center_lat: number;
  center_lng: number;
  radius_nm: number;
}

export interface LaunchRecord {
  id: string;
  name: string;
  net_utc?: string | null;
  net_precision?: string | null;
  window_start_utc?: string | null;
  window_end_utc?: string | null;
  status?: string | null;
  status_abbrev?: string | null;
  provider_name?: string | null;
  rocket?: string | null;
  mission_name?: string | null;
  mission_description?: string | null;
  orbit?: string | null;
  pad_name?: string | null;
  location_name?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  probability?: number | null;
  webcast_live: boolean;
  url?: string | null;
}

export interface LaunchesResponse extends FeedEnvelope {
  count: number;
  launches: LaunchRecord[];
}

export interface FireRecord {
  latitude: number;
  longitude: number;
  brightness_k?: number | null;
  frp_mw?: number | null;
  confidence?: string | null;
  acquired_utc?: string | null;
  satellite?: string | null;
  daynight?: string | null;
}

export interface FiresResponse extends FeedEnvelope {
  count: number;
  total_detections: number;
  fires: FireRecord[];
}
