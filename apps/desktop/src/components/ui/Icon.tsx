import React from 'react';

/**
 * W.E.D.N.E.S.D.A.Y. icon set: 24×24 grid, 1.5px round strokes, currentColor.
 * Original drawings; sized with the --icon-* tokens via the `size` prop.
 */
const PATHS = {
  assistant: 'M12 3.5a8.5 8.5 0 1 0 0 17 8.5 8.5 0 0 0 0-17Zm0 4.5a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z',
  earth:
    'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm-8.6 7h4.3c1.6 0 1.9 2.4 3.3 2.6 1.4.2 1.2 2.3.5 3.6l-1.6 3.4M14 3.4l-.8 2.1c-.4 1.1.3 2.3 1.5 2.4l2.2.2c1 .1 1.6 1.1 1.3 2l-.6 1.9c-.3 1 .3 2 1.3 2.3l1.6.4',
  activity: 'M3 12h4l2.5-6 5 12L17 12h4',
  memory: 'M6 4.5h12a1.5 1.5 0 0 1 1.5 1.5v12a1.5 1.5 0 0 1-1.5 1.5H6A1.5 1.5 0 0 1 4.5 18V6A1.5 1.5 0 0 1 6 4.5ZM8.5 9h7M8.5 12h7M8.5 15h4',
  shield: 'M12 3l7 3v5.5c0 4.3-3 7.9-7 9.5-4-1.6-7-5.2-7-9.5V6l7-3Zm-3 9 2 2 4-4.5',
  settings:
    'M12 9.25a2.75 2.75 0 1 0 0 5.5 2.75 2.75 0 0 0 0-5.5ZM19 12c0-.5-.05-.98-.14-1.45l1.9-1.5-1.8-3.1-2.28.9a7 7 0 0 0-2.5-1.45L13.8 3h-3.6l-.38 2.4a7 7 0 0 0-2.5 1.45l-2.28-.9-1.8 3.1 1.9 1.5a7.1 7.1 0 0 0 0 2.9l-1.9 1.5 1.8 3.1 2.28-.9a7 7 0 0 0 2.5 1.45l.38 2.4h3.6l.38-2.4a7 7 0 0 0 2.5-1.45l2.28.9 1.8-3.1-1.9-1.5c.09-.47.14-.95.14-1.45Z',
  mic: 'M12 3.5a3 3 0 0 0-3 3V12a3 3 0 0 0 6 0V6.5a3 3 0 0 0-3-3ZM6 11.5a6 6 0 0 0 12 0M12 17.5V21M9 21h6',
  micOff: 'M15 10V6.5a3 3 0 0 0-5.6-1.5M9 9v3a3 3 0 0 0 4.6 2.5M6 11.5a6 6 0 0 0 9.6 4.8M18 11.5c0 .7-.1 1.3-.3 1.9M12 17.5V21M9 21h6M4 4l16 16',
  send: 'M5 12h13M13 6l6 6-6 6',
  stop: 'M7.5 7.5h9v9h-9z',
  play: 'M8 6v12l10-6L8 6Z',
  volume: 'M4 9.5h3L11.5 6v12L7 14.5H4v-5ZM15 9a4.2 4.2 0 0 1 0 6M17.5 6.5a7.8 7.8 0 0 1 0 11',
  volumeOff: 'M4 9.5h3L11.5 6v12L7 14.5H4v-5ZM16 10l4 4M20 10l-4 4',
  refresh: 'M19.5 12a7.5 7.5 0 1 1-2.2-5.3M19.5 4.5v4h-4',
  reset: 'M4.5 12a7.5 7.5 0 1 0 2.2-5.3M4.5 4.5v4h4',
  close: 'M6.5 6.5l11 11M17.5 6.5l-11 11',
  check: 'M5 12.5l4.5 4.5L19 7.5',
  x: 'M7 7l10 10M17 7 7 17',
  alert: 'M12 4 2.8 19.5h18.4L12 4Zm0 6v4.5M12 17.2v.1',
  info: 'M12 3.5a8.5 8.5 0 1 0 0 17 8.5 8.5 0 0 0 0-17Zm0 7.5v5M12 8v.1',
  search: 'M10.5 4a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13ZM15.5 15.5 20 20',
  plus: 'M12 5v14M5 12h14',
  minus: 'M5 12h14',
  edit: 'M14.5 5.5l4 4M4.5 19.5l1-4.5L16 4.5l3.5 3.5L9 18.5l-4.5 1Z',
  trash: 'M4.5 7h15M9.5 7V4.5h5V7M6.5 7l.9 12.5h9.2L17.5 7M10 11v5M14 11v5',
  layers: 'M12 4 3 8.5l9 4.5 9-4.5L12 4ZM3 12.5l9 4.5 9-4.5M3 16.5l9 4.5 9-4.5',
  locate: 'M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7ZM12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3',
  pin: 'M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 0 1 13 0C18.5 15.4 12 21 12 21Zm0-13.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5Z',
  home: 'M4 11 12 4l8 7M6.5 9.5V20h11V9.5',
  rotate: 'M20 12a8 8 0 1 1-3-6.2M20 4v4h-4',
  external: 'M14 4.5h5.5V10M19.5 4.5 11 13M17 14v5.5H4.5V7H10',
  chevronDown: 'M6 9.5l6 6 6-6',
  chevronRight: 'M9.5 6l6 6-6 6',
  chevronLeft: 'M14.5 6l-6 6 6 6',
  clock: 'M12 3.5a8.5 8.5 0 1 0 0 17 8.5 8.5 0 0 0 0-17ZM12 7.5V12l3 2',
  wave: 'M3 12h2M7 8.5v7M11 5v14M15 8v8M19 10.5v3M21 12h0',
  bolt: 'M13 3 5 13.5h6L10 21l8-10.5h-6L13 3Z',
  quake: 'M2.5 12h4l2-5 3 10 3-13 2.5 8H21.5',
  flame: 'M12 21c-3.6 0-6-2.5-6-5.8 0-3.6 3-5.2 3.5-9.2 2.5 1.5 3.5 3.5 3.3 6 1.2-.6 2-1.8 2.2-3.2 1.8 1.6 3 3.6 3 6.4C18 18.5 15.6 21 12 21Z',
  cloud: 'M7.5 18.5h9.5a4 4 0 0 0 .5-8 5.5 5.5 0 0 0-10.7 1.2A3.4 3.4 0 0 0 7.5 18.5Z',
  newspaper: 'M5 5.5h11v13H6.5A1.5 1.5 0 0 1 5 17V5.5ZM16 9h3v8.5a1 1 0 0 1-2 0V9M8 9h5M8 12h5M8 15h3',
  keyboard: 'M3.5 7h17v10h-17zM7 10.5h.1M10.5 10.5h.1M14 10.5h.1M17.5 10.5h.1M8 14h8',
  power: 'M12 3.5V11M7.2 6.5a7 7 0 1 0 9.6 0',
  cpu: 'M8 8h8v8H8zM5.5 5.5h13v13h-13zM9.5 2.5v3M14.5 2.5v3M9.5 18.5v3M14.5 18.5v3M2.5 9.5h3M2.5 14.5h3M18.5 9.5h3M18.5 14.5h3',
  lock: 'M7 10.5V8a5 5 0 0 1 10 0v2.5M5.5 10.5h13v10h-13z',
  sparkle: 'M12 3.5c.6 4.4 3.9 7.8 8.5 8.5-4.6.7-7.9 4.1-8.5 8.5-.6-4.4-3.9-7.8-8.5-8.5 4.6-.7 7.9-4.1 8.5-8.5Z',
  link: 'M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1',
  filter: 'M4 5.5h16l-6.2 7.3v5.7l-3.6 1.5v-7.2L4 5.5Z',
  ear: 'M7 9.5a5 5 0 0 1 10 0c0 3-2.5 3.5-3 6s-1.5 4-3.5 4-3-1-3-2.5M10 10a2 2 0 0 1 4 0',
} as const;

export type IconName = keyof typeof PATHS;

interface IconProps {
  name: IconName;
  size?: number;
  className?: string;
  strokeWidth?: number;
  /** Provide a label only when the icon carries meaning on its own. */
  label?: string;
}

export const Icon: React.FC<IconProps> = ({ name, size = 16, className, strokeWidth = 1.5, label }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    role={label ? 'img' : undefined}
    aria-label={label}
    aria-hidden={label ? undefined : true}
    focusable="false"
  >
    <path d={PATHS[name]} />
  </svg>
);
