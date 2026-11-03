import React from 'react';
import ReactDOM from 'react-dom/client';
import { App } from './App';
import { VoiceProvider } from './context/VoiceProvider';
import { AppProvider } from './context/AppProvider';
import { LocationProvider } from './context/LocationProvider';
import './index.css';

const rootElement = document.getElementById('root');
if (!rootElement) {
  throw new Error('Root element #root not found in document.');
}

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <VoiceProvider>
      <AppProvider>
        <LocationProvider>
          <App />
        </LocationProvider>
      </AppProvider>
    </VoiceProvider>
  </React.StrictMode>
);
