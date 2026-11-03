import React, { useState, useEffect, useCallback } from 'react';
import {
  DeviceLocationFix,
  GeoLocation,
  NearbySearchResponse,
  PlaceSummary,
  ReverseGeocodeResponse,
} from '../../types/intelligence';
import './NearbyPlacesPanel.css';

export interface NearbyPlacesPanelProps {
  deviceLocation?: DeviceLocationFix | null;
  selectedLocation?: GeoLocation | null;
  onSelectPlace?: (place: PlaceSummary) => void;
  onPlacesFound?: (places: PlaceSummary[]) => void;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
}

const CATEGORIES = [
  { id: 'hospital', label: 'Hospitals', icon: '🏥' },
  { id: 'pharmacy', label: 'Pharmacies', icon: '💊' },
  { id: 'gas_station', label: 'Fuel / EV', icon: '⛽' },
  { id: 'cafe', label: 'Cafes', icon: '☕' },
  { id: 'restaurant', label: 'Restaurants', icon: '🍽️' },
  { id: 'supermarket', label: 'Groceries', icon: '🛒' },
];

const RADII = [
  { value: 500, label: '500m' },
  { value: 1000, label: '1 km' },
  { value: 1500, label: '1.5 km' },
  { value: 3000, label: '3 km' },
  { value: 5000, label: '5 km' },
];

export const NearbyPlacesPanel: React.FC<NearbyPlacesPanelProps> = ({
  deviceLocation = null,
  selectedLocation = null,
  onSelectPlace,
  onPlacesFound,
  isCollapsed = false,
  onToggleCollapse,
}) => {
  const [selectedCategory, setSelectedCategory] = useState<string>('hospital');
  const [keyword, setKeyword] = useState<string>('');
  const [radiusM, setRadiusM] = useState<number>(1500);

  const [isGeocoding, setIsGeocoding] = useState<boolean>(false);
  const [geocodeResult, setGeocodeResult] = useState<ReverseGeocodeResponse | null>(null);

  const [isSearching, setIsSearching] = useState<boolean>(false);
  const [searchResult, setSearchResult] = useState<NearbySearchResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Determine active center: explicit selectedLocation or deviceLocation
  const activeLat = selectedLocation?.lat ?? deviceLocation?.latitude;
  const activeLng = selectedLocation?.lng ?? deviceLocation?.longitude;
  const hasCoordinates = typeof activeLat === 'number' && typeof activeLng === 'number';

  // Reverse geocode whenever device location or coordinates change
  const handleReverseGeocode = useCallback(async () => {
    if (!hasCoordinates || activeLat == null || activeLng == null) return;
    setIsGeocoding(true);
    setErrorMessage(null);
    try {
      const res = await fetch(`/api/location/geocode?lat=${activeLat}&lng=${activeLng}`);
      if (res.ok) {
        const data = (await res.json()) as ReverseGeocodeResponse;
        setGeocodeResult(data);
      } else {
        const err = await res.json().catch(() => ({}));
        setGeocodeResult({
          status: 'error',
          provider: 'None',
          details: err.detail || `Geocoding request failed (HTTP ${res.status})`,
        });
      }
    } catch (err) {
      setGeocodeResult({
        status: 'error',
        provider: 'None',
        details: err instanceof Error ? err.message : 'Network error',
      });
    } finally {
      setIsGeocoding(false);
    }
  }, [hasCoordinates, activeLat, activeLng]);

  // Execute nearby search
  const handleSearchNearby = useCallback(
    async (categoryToSearch?: string) => {
      const cat = categoryToSearch !== undefined ? categoryToSearch : selectedCategory;
      setIsSearching(true);
      setErrorMessage(null);

      try {
        const payload: Record<string, any> = {
          radius_m: radiusM,
          limit: 12,
        };
        if (cat) payload.category = cat;
        if (keyword.trim()) payload.keyword = keyword.trim();
        if (hasCoordinates && activeLat != null && activeLng != null) {
          payload.latitude = activeLat;
          payload.longitude = activeLng;
        }

        const res = await fetch('/api/location/nearby', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });

        if (res.ok) {
          const data = (await res.json()) as NearbySearchResponse;
          setSearchResult(data);
          onPlacesFound?.(data.places || []);
        } else {
          const err = await res.json().catch(() => ({}));
          setSearchResult({
            status: 'error',
            radius_m: radiusM,
            places: [],
            provider: 'GoogleMaps',
            details: err.detail || `Search failed with status ${res.status}`,
          });
        }
      } catch (err) {
        setSearchResult({
          status: 'error',
          radius_m: radiusM,
          places: [],
          provider: 'GoogleMaps',
          details: err instanceof Error ? err.message : 'Failed to reach backend',
        });
      } finally {
        setIsSearching(false);
      }
    },
    [selectedCategory, keyword, radiusM, hasCoordinates, activeLat, activeLng, onPlacesFound]
  );

  // Auto-reverse geocode on initial coordinate acquisition
  useEffect(() => {
    if (hasCoordinates) {
      handleReverseGeocode();
    }
  }, [hasCoordinates, activeLat, activeLng, handleReverseGeocode]);

  const handleCategoryClick = (catId: string) => {
    const newCat = selectedCategory === catId ? '' : catId;
    setSelectedCategory(newCat);
    handleSearchNearby(newCat);
  };

  const isProviderNotConfigured =
    searchResult?.status === 'provider_not_configured' ||
    geocodeResult?.status === 'provider_not_configured';

  return (
    <div className={`nearby-places-panel ${isCollapsed ? 'collapsed' : ''}`} aria-label="Nearby Places">
      {onToggleCollapse && (
        <div className="places-header-bar">
          <span className="places-header-title">Places & Discovery</span>
          <button
            type="button"
            className="collapse-icon-btn"
            onClick={onToggleCollapse}
            aria-label={isCollapsed ? 'Expand Places' : 'Collapse Places'}
          >
            {isCollapsed ? '‹' : '›'}
          </button>
        </div>
      )}

      {!isCollapsed && (
        <div className="places-scroll-area">
          {/* Resolved Address Banner */}
          <section className="places-address-card" aria-label="Geocoded Address">
            <div className="address-card-header">
              <span className="address-label">Location Address</span>
              {isGeocoding && <span className="geocoding-indicator">Resolving…</span>}
              {!isGeocoding && geocodeResult?.provider && geocodeResult.provider !== 'None' && (
                <div className="provider-tags-group">
                  <span className="address-provider-tag">{geocodeResult.provider}</span>
                  {geocodeResult.osm_uri && (
                    <a
                      href={geocodeResult.osm_uri}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="address-osm-link"
                      title="Inspect coordinates on OpenStreetMap"
                    >
                      OSM ↗
                    </a>
                  )}
                </div>
              )}
            </div>

            {hasCoordinates ? (
              <div className="address-content">
                {geocodeResult?.address?.formatted_address ? (
                  <p className="formatted-address-text">{geocodeResult.address.formatted_address}</p>
                ) : geocodeResult?.status === 'provider_not_configured' ? (
                  <p className="address-unconfigured-text">
                    Location enrichment is unconfigured. Coordinates: {activeLat?.toFixed(4)}°, {activeLng?.toFixed(4)}°
                  </p>
                ) : (
                  <p className="address-coords-text">
                    {activeLat?.toFixed(4)}° N, {activeLng?.toFixed(4)}° E
                  </p>
                )}
                {geocodeResult?.address?.locality && (
                  <span className="locality-badge">
                    {geocodeResult.address.locality}
                    {geocodeResult.address.country ? `, ${geocodeResult.address.country}` : ''}
                  </span>
                )}
              </div>
            ) : (
              <p className="address-empty-text">No active device location fix or coordinate selected.</p>
            )}
          </section>

          {/* Unconfigured Provider Guidance */}
          {isProviderNotConfigured && (
            <div className="places-unconfigured-notice" role="status">
              <div className="notice-icon">⚠️</div>
              <div className="notice-body">
                <strong>Location Enrichment Unconfigured</strong>
                <p>
                  No active location provider is configured. Set <code>LOCATION_PROVIDER=osm</code> in{' '}
                  <code>.env</code> for free OpenStreetMap intelligence (no API key required), or add{' '}
                  <code>GOOGLE_MAPS_API_KEY</code> for Google Maps.
                </p>
                <span className="notice-offline-guarantee">
                  ✓ Device location service operates fully offline without external providers.
                </span>
              </div>
            </div>
          )}

          {/* Search Controls */}
          <section className="places-search-controls" aria-label="Search Controls">
            {/* Category Chips */}
            <div className="places-category-chips" role="group" aria-label="Categories">
              {CATEGORIES.map((cat) => (
                <button
                  key={cat.id}
                  type="button"
                  className={`category-chip ${selectedCategory === cat.id ? 'active' : ''}`}
                  onClick={() => handleCategoryClick(cat.id)}
                  aria-pressed={selectedCategory === cat.id}
                >
                  <span className="chip-icon">{cat.icon}</span>
                  <span className="chip-label">{cat.label}</span>
                </button>
              ))}
            </div>

            {/* Keyword Input & Radius Select */}
            <div className="search-inputs-row">
              <input
                type="text"
                className="places-query-input"
                placeholder="Search places or keywords…"
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSearchNearby()}
                aria-label="Places search keyword"
              />
              <select
                className="radius-select"
                value={radiusM}
                onChange={(e) => setRadiusM(Number(e.target.value))}
                aria-label="Search radius"
              >
                {RADII.map((r) => (
                  <option key={r.value} value={r.value}>
                    {r.label}
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="places-search-btn"
                onClick={() => handleSearchNearby()}
                disabled={isSearching}
                aria-label="Execute search"
              >
                {isSearching ? '…' : 'Find'}
              </button>
            </div>
          </section>

          {/* Places Results List */}
          <section className="places-results-section" aria-label="Search Results">
            {isSearching && (
              <div className="places-loading-indicator" aria-live="polite">
                <span className="pulse-dot" /> Searching nearby points of interest…
              </div>
            )}

            {!isSearching && searchResult?.places && searchResult.places.length > 0 && (
              <div className="places-list">
                <div className="places-count-header">
                  <span>Found {searchResult.places.length} places</span>
                  <span className="radius-tag">within {searchResult.radius_m}m</span>
                </div>
                {searchResult.places.map((place) => (
                  <div key={place.id} className="place-item-card">
                    <div className="place-item-header">
                      <strong className="place-item-name">{place.name}</strong>
                      {place.distance_m != null && (
                        <span className="place-distance-tag">
                          {place.distance_m >= 1000
                            ? `${(place.distance_m / 1000).toFixed(1)} km`
                            : `${Math.round(place.distance_m)} m`}
                        </span>
                      )}
                    </div>
                    {place.formatted_address && (
                      <p className="place-item-address">{place.formatted_address}</p>
                    )}
                    <div className="place-item-footer">
                      <div className="place-tags-group">
                        {place.types?.slice(0, 2).map((t) => (
                          <span key={t} className="place-type-pill">
                            {t.replace(/_/g, ' ')}
                          </span>
                        ))}
                        {place.rating != null && (
                          <span className="place-rating-pill">★ {place.rating.toFixed(1)}</span>
                        )}
                      </div>
                      <div className="place-actions-group">
                        {onSelectPlace && (
                          <button
                            type="button"
                            className="place-focus-btn"
                            onClick={() => onSelectPlace(place)}
                            title="Focus place on globe"
                            aria-label={`Focus ${place.name} on globe`}
                          >
                            Focus
                          </button>
                        )}
                        {place.osm_uri && (
                          <a
                            href={place.osm_uri}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="place-osm-link"
                            title="Open in OpenStreetMap"
                            aria-label={`Open ${place.name} in OpenStreetMap`}
                          >
                            OSM ↗
                          </a>
                        )}
                        {place.google_maps_uri && (
                          <a
                            href={place.google_maps_uri}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="place-maps-link"
                            title="Open in Google Maps"
                            aria-label={`Open ${place.name} in Google Maps`}
                          >
                            Maps ↗
                          </a>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {!isSearching && searchResult?.status === 'empty' && (
              <div className="places-empty-state">
                <p>No places found matching your filter within {radiusM}m.</p>
                <button
                  type="button"
                  className="places-expand-radius-btn"
                  onClick={() => {
                    setRadiusM((prev) => Math.min(prev * 2, 10000));
                    handleSearchNearby();
                  }}
                >
                  Expand search radius
                </button>
              </div>
            )}

            {!isSearching && searchResult?.status === 'rate_limited' && (
              <div className="places-state-notice rate-limited" role="alert">
                <span className="state-notice-icon">⏳</span>
                <div className="state-notice-body">
                  <strong>Rate Limit Enforced</strong>
                  <p>{searchResult.details || 'Community API rate limit reached. Please wait a moment before searching again.'}</p>
                </div>
              </div>
            )}

            {!isSearching && searchResult?.status === 'timeout' && (
              <div className="places-state-notice timeout" role="alert">
                <span className="state-notice-icon">⏱️</span>
                <div className="state-notice-body">
                  <strong>Request Timed Out</strong>
                  <p>{searchResult.details || 'The location endpoint took too long to respond. Please try again.'}</p>
                  <button type="button" className="places-retry-btn" onClick={() => handleSearchNearby()}>
                    Retry Search
                  </button>
                </div>
              </div>
            )}

            {!isSearching && searchResult?.status === 'provider_error' && (
              <div className="places-state-notice error" role="alert">
                <span className="state-notice-icon">⚠️</span>
                <div className="state-notice-body">
                  <strong>Provider Service Unavailable</strong>
                  <p>{searchResult.details || 'Public location service endpoints are temporarily unavailable.'}</p>
                  <button type="button" className="places-retry-btn" onClick={() => handleSearchNearby()}>
                    Retry Search
                  </button>
                </div>
              </div>
            )}

            {!isSearching && (errorMessage || (searchResult?.status === 'error' && searchResult.details)) && (
              <div className="places-empty-state" role="alert">
                <p>Search diagnostic</p>
                <span>{errorMessage || searchResult?.details}</span>
              </div>
            )}

            {!isSearching && searchResult?.status === 'no_fix' && (
              <div className="places-no-fix-state">
                <p>Device coordinates are unavailable.</p>
                <span>Enable location tracking above or select a point on the globe to search.</span>
              </div>
            )}

            {/* OpenStreetMap Attribution Footer */}
            <div className="places-attribution-footer" role="contentinfo">
              <span>
                Data ©{' '}
                <a
                  href="https://www.openstreetmap.org/copyright"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="osm-copyright-link"
                >
                  OpenStreetMap
                </a>{' '}
                contributors
              </span>
            </div>
          </section>
        </div>
      )}
    </div>
  );
};
