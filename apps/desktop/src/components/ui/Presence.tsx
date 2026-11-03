import React from 'react';
import { AssistantPhase } from '../../types/voice';
import './Presence.css';

const LABELS: Record<AssistantPhase, string> = {
  idle: 'Ready',
  listening: 'Listening',
  transcribing: 'Transcribing',
  reviewing: 'Review transcript',
  thinking: 'Thinking',
  retrieving: 'Retrieving data',
  awaiting: 'Waiting for your approval',
  executing: 'Running an approved action',
  speaking: 'Speaking',
  error: 'Needs attention',
};

const W = 'M22 44 L38 80 L60 50 L82 80 L98 44';

/**
 * The intelligence core: the W of the name under the planet's limb. Each state is
 * a different behaviour of that one line, so it reads at a glance without colour.
 * Pure CSS on SVG: no per-frame JavaScript and no React re-renders.
 */
export const Presence: React.FC<{ phase: AssistantPhase; size?: number; showLabel?: boolean }> = ({
  phase,
  size = 120,
  showLabel = false,
}) => (
  <div className="core" data-phase={phase} style={{ '--core-size': `${size}px` } as React.CSSProperties}>
    <svg className="core__mark" viewBox="0 0 120 120" aria-hidden="true">
      <path className="core__limb" d="M12 74A52 52 0 0 1 108 74" pathLength={100} />
      <path className="core__w" d={W} pathLength={100} />
      <path className="core__trace" d={W} pathLength={100} />
      <g className="core__nodes">
        <circle cx="22" cy="44" r="2.6" />
        <circle cx="38" cy="80" r="2.6" />
        <circle cx="60" cy="50" r="2.6" />
        <circle cx="82" cy="80" r="2.6" />
        <circle cx="98" cy="44" r="2.6" />
      </g>
    </svg>
    {showLabel ? (
      <span className="core__label" aria-live="polite">{LABELS[phase]}</span>
    ) : (
      <span className="sr-only" aria-live="polite">{LABELS[phase]}</span>
    )}
  </div>
);

export const phaseLabel = (phase: AssistantPhase) => LABELS[phase];
