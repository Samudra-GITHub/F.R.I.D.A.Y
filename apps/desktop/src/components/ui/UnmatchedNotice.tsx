import React from 'react';
import { Icon } from './Icon';

/** Warns when an answer names records that none of the sources returned. */
export const UnmatchedNotice: React.FC<{ mentions?: string[] }> = ({ mentions }) => {
  if (!mentions?.length) return null;
  return (
    <div className="notice notice--warn" role="alert">
      <Icon name="alert" size={14} />
      <div>
        The answer names {mentions.length === 1 ? 'a record' : `${mentions.length} records`} that no source returned:{' '}
        {mentions.join('; ')}. The local model can get details wrong; the records listed from the sources are the facts.
      </div>
    </div>
  );
};
