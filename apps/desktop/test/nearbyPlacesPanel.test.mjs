import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { NearbyPlacesPanel } from '../src/components/intelligence/NearbyPlacesPanel.tsx';

test('NearbyPlacesPanel Suite', async (t) => {
  await t.test('Case 1: Renders safely when no device fix or location is available', () => {
    const html = renderToStaticMarkup(
      React.createElement(NearbyPlacesPanel, {
        deviceLocation: null,
        selectedLocation: null,
        onSelectPlace: () => {},
        onPlacesFound: () => {},
      })
    );

    assert.ok(html.includes('Places &amp; Discovery') || html.includes('Places & Discovery') || html.includes('Location Address'), 'Renders address card header');
    assert.ok(html.includes('No active device location fix or coordinate selected.'), 'Shows empty location notice');
    assert.ok(html.includes('Hospitals'), 'Renders hospital category chip');
    assert.ok(html.includes('Pharmacies'), 'Renders pharmacy category chip');
    assert.ok(html.includes('Fuel / EV'), 'Renders fuel category chip');
  });

  await t.test('Case 2: Renders coordinates when device fix is provided', () => {
    const html = renderToStaticMarkup(
      React.createElement(NearbyPlacesPanel, {
        deviceLocation: {
          latitude: 28.6139,
          longitude: 77.2090,
          accuracy_m: 15.0,
          status: 'fresh',
          provider: 'Windows.Devices.Geolocation',
          is_stale: false,
        },
        selectedLocation: null,
      })
    );

    assert.ok(html.includes('28.6139'), 'Displays device latitude');
    assert.ok(html.includes('77.2090'), 'Displays device longitude');
  });

  await t.test('Case 3: Renders category chips and radius selector options', () => {
    const html = renderToStaticMarkup(
      React.createElement(NearbyPlacesPanel, {
        deviceLocation: null,
        selectedLocation: { lat: 37.7749, lng: -122.4194 },
      })
    );

    assert.ok(html.includes('500m'), 'Includes 500m option');
    assert.ok(html.includes('1.5 km'), 'Includes 1.5km option');
    assert.ok(html.includes('5 km'), 'Includes 5km option');
    assert.ok(html.includes('Search places or keywords…'), 'Renders search placeholder');
  });

  await t.test('Case 4: Collapsed mode hides the scroll area', () => {
    const html = renderToStaticMarkup(
      React.createElement(NearbyPlacesPanel, {
        isCollapsed: true,
        onToggleCollapse: () => {},
      })
    );

    assert.ok(html.includes('collapsed'), 'Has collapsed CSS class');
    assert.ok(!html.includes('places-scroll-area'), 'Does not render scroll area when collapsed');
  });

  await t.test('Case 5: Renders visible OpenStreetMap attribution and link', () => {
    const html = renderToStaticMarkup(
      React.createElement(NearbyPlacesPanel, {
        deviceLocation: null,
        selectedLocation: { lat: 28.6139, lng: 77.2090 },
      })
    );

    assert.ok(html.includes('Data ©'), 'Renders attribution prefix');
    assert.ok(html.includes('OpenStreetMap'), 'Includes OpenStreetMap mention');
    assert.ok(html.includes('https://www.openstreetmap.org/copyright'), 'Includes official copyright link');
  });
});
