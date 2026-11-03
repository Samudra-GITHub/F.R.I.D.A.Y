import { createContext, useContext } from 'react';
import { VoiceContextValue } from '../types/voice';

export const VoiceContext = createContext<VoiceContextValue | undefined>(undefined);

export const useVoice = (): VoiceContextValue => {
  const context = useContext(VoiceContext);
  if (!context) {
    throw new Error('useVoice must be used within a VoiceProvider');
  }
  return context;
};
