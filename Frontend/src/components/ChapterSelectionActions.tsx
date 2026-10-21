import React, { useEffect, useState } from 'react';
import { createEntity } from '../api/entities';
import { createEvent } from '../api/events';
import { useWorldStore } from '../store/useWorldStore';

interface ChapterSelectionActionsProps {
  worldId: string;
  chapterId: string;
  readingRef: React.RefObject<HTMLDivElement | null>;
  textareaRef: React.RefObject<HTMLTextAreaElement | null>;
  isEditing: boolean;
}

export const ChapterSelectionActions: React.FC<ChapterSelectionActionsProps> = ({ worldId, chapterId, readingRef, textareaRef, isEditing }) => {
  const [selectedText, setSelectedText] = useState('');
  const [kind, setKind] = useState<'entity' | 'location' | 'event' | null>(null);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [entityType, setEntityType] = useState<'character' | 'object'>('character');
  const [eventType, setEventType] = useState('EVENT');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState('');

  useEffect(() => {
    const captureSelection = () => {
      if (kind) return;
      const editor = textareaRef.current;
      if (isEditing && editor && document.activeElement === editor) {
        setSelectedText(editor.value.slice(editor.selectionStart, editor.selectionEnd).trim());
        return;
      }
      const selection = window.getSelection();
      if (!isEditing && selection && readingRef.current?.contains(selection.anchorNode) && readingRef.current.contains(selection.focusNode)) {
        setSelectedText(selection.toString().trim());
      } else {
        setSelectedText('');
      }
    };
    document.addEventListener('selectionchange', captureSelection);
    document.addEventListener('select', captureSelection, true);
    return () => {
      document.removeEventListener('selectionchange', captureSelection);
      document.removeEventListener('select', captureSelection, true);
    };
  }, [isEditing, kind, readingRef, textareaRef]);

  const openForm = (nextKind: NonNullable<typeof kind>) => {
    setName(selectedText.slice(0, 255));
    setDescription(selectedText);
    setEntityType('character');
    setEventType('EVENT');
    setError(null);
    setNotice('');
    setKind(nextKind);
  };

  const handleCreate = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!kind || busy) return;
    if (kind === 'event' ? !description.trim() || !eventType.trim() : !name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      if (kind === 'event') {
        await createEvent(worldId, { description: description.trim(), event_type: eventType.trim().toUpperCase().replace(/\s+/g, '_'), chapter_id: chapterId });
        setNotice('Event saved to Timeline for this chapter.');
      } else {
        await createEntity(worldId, {
          canonical_name: name.trim(),
          entity_type: kind === 'location' ? 'location' : entityType,
          attributes: { description: description.trim() },
        });
        await useWorldStore.getState().fetchEntitiesForWorld(worldId);
        setNotice(kind === 'location' ? 'Location saved to World Ledger.' : 'Entity saved to World Ledger.');
      }
      setKind(null);
      setSelectedText('');
      window.getSelection()?.removeAllRanges();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save. Please try again.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="shrink-0 flex flex-wrap items-center gap-3 px-8 py-2 border-b border-starlight-white/5 bg-surface-container-lowest text-xs select-none">
        {selectedText ? <>
          <span className="text-on-surface-variant/60 truncate max-w-48" title={selectedText}>“{selectedText}”</span>
          {(['entity', 'location', 'event'] as const).map(item => (
            <button key={item} onMouseDown={event => event.preventDefault()} onClick={() => openForm(item)} className="px-3 py-1.5 rounded border border-primary/30 text-primary hover:bg-primary/10 capitalize">Create {item}</button>
          ))}
        </> : <span className="text-on-surface-variant/60">Select chapter text to create an entity, location, or event.</span>}
        {notice && <span role="status" className="text-primary">{notice}</span>}
      </div>
      {kind && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-void-black/80 backdrop-blur-sm">
          <section role="dialog" aria-modal="true" aria-labelledby="selection-create-title" className="w-full max-w-lg max-h-[85vh] overflow-y-auto p-6 rounded-xl bg-surface-container border border-primary/30 shadow-2xl">
            <h2 id="selection-create-title" className="text-xl text-starlight-white mb-4 capitalize">Create {kind} from selection</h2>
            <p className="text-xs text-on-surface-variant/60 mb-2">Selected chapter text</p>
            <blockquote className="text-sm text-on-surface-variant border-l-2 border-primary/40 pl-3 mb-5 max-h-28 overflow-y-auto whitespace-pre-wrap">{selectedText}</blockquote>
            <form onSubmit={handleCreate} className="space-y-4">
              <fieldset disabled={busy} className="space-y-4 disabled:opacity-60">
                {kind !== 'event' && <label className="block text-xs text-on-surface-variant">Name
                  <input autoFocus required maxLength={255} value={name} onChange={event => setName(event.target.value)} className="block w-full mt-1 p-3 rounded bg-void-black border border-starlight-white/10 text-sm text-starlight-white" />
                </label>}
                {kind === 'entity' && <label className="block text-xs text-on-surface-variant">Entity type
                  <select aria-label="Entity type" value={entityType} onChange={event => setEntityType(event.target.value as typeof entityType)} className="block w-full mt-1 p-3 rounded bg-void-black text-sm text-starlight-white"><option value="character">Character</option><option value="object">Object</option></select>
                </label>}
                {kind === 'event' && <label className="block text-xs text-on-surface-variant">Event type
                  <input autoFocus required maxLength={100} value={eventType} onChange={event => setEventType(event.target.value)} className="block w-full mt-1 p-3 rounded bg-void-black border border-starlight-white/10 text-sm text-starlight-white" />
                </label>}
                <label className="block text-xs text-on-surface-variant">Description
                  <textarea required={kind === 'event'} value={description} onChange={event => setDescription(event.target.value)} rows={4} className="block w-full mt-1 p-3 rounded bg-void-black border border-starlight-white/10 text-sm text-starlight-white" />
                </label>
                {kind === 'event' && <p className="text-xs text-on-surface-variant/60">This event will appear in Timeline under the current chapter.</p>}
              </fieldset>
              {error && <p role="alert" className="text-sm text-error">{error}</p>}
              <div className="flex justify-end gap-3">
                <button type="button" disabled={busy} onClick={() => setKind(null)} className="px-4 py-2 text-sm text-on-surface-variant">Cancel</button>
                <button disabled={busy} type="submit" className="px-4 py-2 rounded bg-primary text-void-black text-sm disabled:opacity-50">{busy ? 'Saving...' : `Create ${kind}`}</button>
              </div>
            </form>
          </section>
        </div>
      )}
    </>
  );
};
