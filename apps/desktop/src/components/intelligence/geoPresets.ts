import { GeoLocation } from '../../types/intelligence';

export interface GeoPreset extends GeoLocation {
  label: string;
  city: string;
  /** Lower-case words in a query that refer to this place. */
  aliases: string[];
}

export const GEO_PRESETS: GeoPreset[] = [
  { label: 'Bangalore', city: 'Bangalore, India', lat: 12.9716, lng: 77.5946, aliases: ['bangalore', 'bengaluru', 'india'] },
  { label: 'Geneva', city: 'Geneva, Switzerland', lat: 46.2044, lng: 6.1432, aliases: ['geneva', 'cern', 'switzerland'] },
  { label: 'Tokyo', city: 'Tokyo, Japan', lat: 35.6762, lng: 139.6503, aliases: ['tokyo', 'japan'] },
  { label: 'San Francisco', city: 'San Francisco, USA', lat: 37.7749, lng: -122.4194, aliases: ['san francisco', 'california'] },
  { label: 'Singapore', city: 'Singapore', lat: 1.3521, lng: 103.8198, aliases: ['singapore', 'malacca'] },
  { label: 'Valparaíso', city: 'Valparaíso, Chile', lat: -33.0472, lng: -71.6127, aliases: ['valparaiso', 'valparaíso', 'chile'] },
];
