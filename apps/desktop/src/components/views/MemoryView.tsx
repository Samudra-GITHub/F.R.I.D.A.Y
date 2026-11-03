import React, { useCallback, useEffect, useState } from 'react';
import { createMemory, deleteMemory, listMemories, updateMemory } from '../../services/voiceApi';
import { MemoryItem } from '../../types/voice';
import { useApp } from '../../context/AppProvider';
import { PageHero } from '../ui/PageHero';
import { Icon } from '../ui/Icon';
import './Page.css';
import './MemoryView.css';

const KINDS: { id: MemoryItem['kind']; label: string; hint: string }[] = [
  { id: 'preference', label: 'Preference', hint: 'How you like answers. Always given to the model.' },
  { id: 'profile', label: 'Profile', hint: 'Facts about you. Always given to the model.' },
  { id: 'project', label: 'Project', hint: 'Context for a project. Used when relevant.' },
  { id: 'decision', label: 'Decision', hint: 'A choice and its reason. Used when relevant.' },
  { id: 'procedure', label: 'Procedure', hint: 'A workflow you approved. Used when relevant.' },
  { id: 'fact', label: 'Fact', hint: 'Anything else worth remembering. Used when relevant.' },
];

const SOURCE_LABEL: Record<MemoryItem['source_kind'], string> = {
  explicit_user_statement: 'You wrote this',
  user_correction: 'Edited by you',
  imported: 'Imported',
  model_suggestion: 'Suggested by the model',
};

const formatDate = (iso: string) =>
  new Date(iso).toLocaleString([], { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });

export const MemoryView: React.FC = () => {
  const { backend, logEvent } = useApp();
  const [items, setItems] = useState<MemoryItem[]>([]);
  const [show, setShow] = useState<'all' | MemoryItem['kind']>('all');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [kind, setKind] = useState<MemoryItem['kind']>('preference');
  const [content, setContent] = useState('');
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState<{ id: string; text: string } | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  const load = useCallback(async (q?: string) => {
    try {
      setItems(await listMemories(q || undefined));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const t = window.setTimeout(() => load(query.trim()), query ? 250 : 0);
    return () => window.clearTimeout(t);
  }, [query, load]);

  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!content.trim()) return;
    setSaving(true);
    try {
      await createMemory(kind, content.trim());
      setContent('');
      logEvent({ kind: 'system', title: 'Memory saved', details: kind, outcome: 'ok' });
      await load(query.trim());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  const saveEdit = async () => {
    if (!editing || !editing.text.trim()) return;
    try {
      await updateMemory(editing.id, { content: editing.text.trim() });
      setEditing(null);
      await load(query.trim());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const remove = async (id: string) => {
    try {
      await deleteMemory(id);
      setConfirmDelete(null);
      logEvent({ kind: 'system', title: 'Memory deleted', outcome: 'ok' });
      setItems((prev) => prev.filter((m) => m.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const selectedKind = KINDS.find((k) => k.id === kind)!;
  const counts = items.reduce<Record<string, number>>((acc, m) => ({ ...acc, [m.kind]: (acc[m.kind] ?? 0) + 1 }), {});
  const shown = show === 'all' ? items : items.filter((m) => m.kind === show);

  return (
    <div className="page">
      <div className="page__inner">
        <PageHero
          kicker="Yours to edit"
          title="Memory"
          lede={
            <>
              What W.E.D.N.E.S.D.A.Y. remembers between conversations. Only you can add, edit, or delete memories. The model
              reads them as context but can’t write them or use them to gain permissions. Stored on this computer in{' '}
              <code>~/.friday/memory.sqlite3</code>.
            </>
          }
          stats={[
            { label: 'Remembered', value: items.length },
            { label: 'Always given to the model', value: (counts.preference ?? 0) + (counts.profile ?? 0), tone: 'accent' },
          ]}
        />

        <div className="memory-layout">
        <aside className="memory-layout__side">
        <form className="card memory__composer" onSubmit={add}>
          <div className="memory__kinds" role="radiogroup" aria-label="Memory type">
            {KINDS.map((k) => (
              <button key={k.id} type="button" role="radio" aria-checked={kind === k.id} className="chip" aria-pressed={kind === k.id} onClick={() => setKind(k.id)}>
                {k.label}
              </button>
            ))}
          </div>
          <textarea
            className="field"
            rows={2}
            maxLength={1000}
            placeholder="e.g. Keep answers short and use metric units."
            value={content}
            onChange={(e) => setContent(e.target.value)}
            disabled={backend !== 'online'}
            aria-label="Memory content"
          />
          <div className="row">
            <span className="small muted">{selectedKind.hint}</span>
            <span className="spacer" />
            <span className="small muted mono tabular">{content.length}/1000</span>
            <button type="submit" className="btn btn--primary btn--sm" disabled={!content.trim() || saving || backend !== 'online'}>
              {saving ? <span className="spinner" /> : <Icon name="plus" size={13} />} Remember
            </button>
          </div>
        </form>

        <nav className="card memory__filters" aria-label="Show memories of type">
          {[{ id: 'all' as const, label: 'All' }, ...KINDS].map((k) => (
            <button key={k.id} type="button" className="memory__filter" aria-pressed={show === k.id} onClick={() => setShow(k.id)}>
              <span>{k.label}</span>
              <span className="mono tabular">{k.id === 'all' ? items.length : counts[k.id] ?? 0}</span>
            </button>
          ))}
        </nav>
        </aside>

        <div className="memory-layout__main">
        <div className="toolbar">
          <div className="memory__search">
            <Icon name="search" size={15} />
            <input className="field" type="search" placeholder="Search memories" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search memories" />
          </div>
          <span className="small muted">{items.length} active</span>
        </div>

        {error && (
          <div className="notice notice--danger" role="alert">
            <Icon name="alert" size={15} />
            <div>{error}</div>
          </div>
        )}

        <section className="card">
          {loading ? (
            <div className="activity__loading" style={{ padding: 16, display: 'grid', gap: 12 }}>
              {[0, 1].map((i) => <div key={i} className="skeleton" style={{ height: 56 }} />)}
            </div>
          ) : shown.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state__icon"><Icon name="memory" size={20} /></div>
              <div className="empty-state__title">{query || show !== 'all' ? 'No matches' : 'No memories yet'}</div>
              <p className="empty-state__body">
                {query ? 'Try different words.' : 'Add a preference above. It will be given to the model as reference context in future conversations.'}
              </p>
            </div>
          ) : (
            <ul className="list">
              {shown.map((m) => (
                <li key={m.id} className="memory__item">
                  <span className={`badge memory__kind memory__kind--${m.kind}`}>{m.kind}</span>
                  <div className="memory__main">
                    {editing?.id === m.id ? (
                      <div className="stack">
                        <textarea className="field" rows={2} value={editing.text} maxLength={1000} onChange={(e) => setEditing({ id: m.id, text: e.target.value })} autoFocus aria-label="Edit memory" />
                        <div className="row">
                          <button type="button" className="btn btn--primary btn--sm" onClick={saveEdit}>Save</button>
                          <button type="button" className="btn btn--ghost btn--sm" onClick={() => setEditing(null)}>Cancel</button>
                        </div>
                      </div>
                    ) : (
                      <p className="memory__content">{m.content}</p>
                    )}
                    <div className="memory__meta">
                      <span>{SOURCE_LABEL[m.source_kind]}</span>
                      <span>·</span>
                      <span>Updated {formatDate(m.updated_at)}</span>
                      {m.expires_at && (<><span>·</span><span>Expires {formatDate(m.expires_at)}</span></>)}
                    </div>
                  </div>
                  <div className="memory__actions">
                    {confirmDelete === m.id ? (
                      <>
                        <button type="button" className="btn btn--danger btn--sm" onClick={() => remove(m.id)}>Delete</button>
                        <button type="button" className="btn btn--ghost btn--sm" onClick={() => setConfirmDelete(null)}>Keep</button>
                      </>
                    ) : (
                      <>
                        <button type="button" className="icon-btn icon-btn--sm" onClick={() => setEditing({ id: m.id, text: m.content })} aria-label="Edit memory" title="Edit">
                          <Icon name="edit" size={14} />
                        </button>
                        <button type="button" className="icon-btn icon-btn--sm" onClick={() => setConfirmDelete(m.id)} aria-label="Delete memory" title="Delete">
                          <Icon name="trash" size={14} />
                        </button>
                      </>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
        </div>
        </div>
        <p className="small muted">
          Deleting a memory erases its text and removes it from search immediately. A content-free tombstone remains so it
          can’t be re-created by re-indexing.
        </p>
      </div>
    </div>
  );
};
