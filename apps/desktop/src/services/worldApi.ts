/**
 * World Intelligence API Client — Phase 3
 * Connects the frontend to the local FastAPI /world endpoints via the Vite proxy.
 */

import {
  EarthquakesResponse,
  WeatherResponse,
  NaturalEventsResponse,
  DisastersResponse,
  NewsResponse,
  WorldStatusResponse,
  SatellitesResponse,
  SatelliteTrackResponse,
  FlightsResponse,
  LaunchesResponse,
  FiresResponse,
} from '../types/intelligence';

export async function fetchWorldStatus(): Promise<WorldStatusResponse | null> {
  try {
    const res = await fetch('/api/world/status');
    if (!res.ok) return null;
    return (await res.json()) as WorldStatusResponse;
  } catch (err) {
    console.error('Failed to fetch world status:', err);
    return null;
  }
}

export async function fetchEarthquakes(
  minMagnitude = 2.5,
  limit = 100,
  period = 'all_day'
): Promise<EarthquakesResponse | null> {
  try {
    const params = new URLSearchParams({
      min_magnitude: minMagnitude.toString(),
      limit: limit.toString(),
      period,
    });
    const res = await fetch(`/api/world/earthquakes?${params.toString()}`);
    if (!res.ok) return null;
    return (await res.json()) as EarthquakesResponse;
  } catch (err) {
    console.error('Failed to fetch earthquakes:', err);
    return null;
  }
}

export async function fetchWeather(lat: number, lng: number): Promise<WeatherResponse | null> {
  try {
    const params = new URLSearchParams({
      lat: lat.toString(),
      lng: lng.toString(),
    });
    const res = await fetch(`/api/world/weather?${params.toString()}`);
    if (!res.ok) return null;
    return (await res.json()) as WeatherResponse;
  } catch (err) {
    console.error('Failed to fetch weather:', err);
    return null;
  }
}

export async function fetchNaturalEvents(days = 30, limit = 100): Promise<NaturalEventsResponse | null> {
  try {
    const params = new URLSearchParams({
      days: days.toString(),
      limit: limit.toString(),
    });
    const res = await fetch(`/api/world/events?${params.toString()}`);
    if (!res.ok) return null;
    return (await res.json()) as NaturalEventsResponse;
  } catch (err) {
    console.error('Failed to fetch natural events:', err);
    return null;
  }
}

export async function fetchDisasters(limit = 50, alertLevel?: string): Promise<DisastersResponse | null> {
  try {
    const params = new URLSearchParams({
      limit: limit.toString(),
    });
    if (alertLevel) {
      params.set('alert_level', alertLevel);
    }
    const res = await fetch(`/api/world/disasters?${params.toString()}`);
    if (!res.ok) return null;
    return (await res.json()) as DisastersResponse;
  } catch (err) {
    console.error('Failed to fetch disasters:', err);
    return null;
  }
}

export async function fetchWorldNews(limit = 30): Promise<NewsResponse | null> {
  try {
    const params = new URLSearchParams({
      limit: limit.toString(),
    });
    const res = await fetch(`/api/world/news?${params.toString()}`);
    if (!res.ok) return null;
    return (await res.json()) as NewsResponse;
  } catch (err) {
    console.error('Failed to fetch world news:', err);
    return null;
  }
}

// ---- Place search & device location ---------------------------------------------

export interface PlaceSearchResult {
  name: string;
  display_name?: string | null;
  category?: string | null;
  type?: string | null;
  latitude: number;
  longitude: number;
  bbox?: [number, number, number, number] | null;
  osm_uri?: string | null;
}

export interface PlaceSearchResponse {
  status: 'ok' | 'empty' | 'provider_not_configured' | 'rate_limited' | 'timeout' | 'provider_error';
  query: string;
  results: PlaceSearchResult[];
  attribution?: string;
  details?: string;
}

export async function searchPlaces(q: string, signal?: AbortSignal): Promise<PlaceSearchResponse> {
  const res = await fetch(`/api/location/search?q=${encodeURIComponent(q)}`, { signal });
  if (!res.ok) throw new Error(`Place search failed (HTTP ${res.status})`);
  return res.json();
}


// ---- Additional Earth layers ------------------------------------------------------

async function getJson<T>(url: string, signal?: AbortSignal): Promise<T | null> {
  try {
    const res = await fetch(url, { signal });
    if (!res.ok) {
      console.warn(`${url} → HTTP ${res.status}`);
      return null;
    }
    return (await res.json()) as T;
  } catch (err) {
    if (!(err instanceof DOMException && err.name === 'AbortError')) console.warn(`${url} failed:`, err);
    return null;
  }
}

export const fetchSatellites = () => getJson<SatellitesResponse>('/api/world/satellites?limit=600');
export const fetchSatelliteTrack = (noradId: number) =>
  getJson<SatelliteTrackResponse>(`/api/world/satellites/${noradId}/track?minutes=50`);
export const fetchFlights = (lat: number, lng: number, radiusNm: number, signal?: AbortSignal) =>
  getJson<FlightsResponse>(
    `/api/world/flights?lat=${lat.toFixed(2)}&lng=${lng.toFixed(2)}&radius_nm=${Math.round(radiusNm)}`,
    signal
  );
export const fetchLaunches = () => getJson<LaunchesResponse>('/api/world/launches?limit=25');
export const fetchFires = () => getJson<FiresResponse>('/api/world/fires');
