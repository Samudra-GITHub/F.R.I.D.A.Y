import React from 'react';
import './PageHero.css';

export interface HeroStat {
  label: string;
  value: React.ReactNode;
  tone?: 'danger' | 'accent';
}

/**
 * The header every document screen shares: kicker, title, lede, and the figures
 * that matter, sitting above the planet's horizon line from the Earth screen.
 */
export const PageHero: React.FC<{
  kicker: string;
  title: string;
  lede: React.ReactNode;
  stats?: HeroStat[];
  actions?: React.ReactNode;
}> = ({ kicker, title, lede, stats, actions }) => (
  <header className="hero">
    <div className="hero__top">
      <div className="hero__text">
        <span className="hero__kicker">{kicker}</span>
        <h2 className="hero__title">{title}</h2>
        <p className="hero__lede">{lede}</p>
      </div>
      {actions && <div className="hero__actions">{actions}</div>}
    </div>
    {stats && stats.length > 0 && (
      <dl className="hero__stats">
        {stats.map((s) => (
          <div key={s.label} className="hero__stat">
            <dt>{s.label}</dt>
            <dd className={s.tone ? `hero__value hero__value--${s.tone}` : 'hero__value'}>{s.value}</dd>
          </div>
        ))}
      </dl>
    )}
    <svg className="hero__horizon" viewBox="0 0 1000 40" preserveAspectRatio="none" aria-hidden="true">
      <path d="M0 40 Q500 -18 1000 40" />
    </svg>
  </header>
);
