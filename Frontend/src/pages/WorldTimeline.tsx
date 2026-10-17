import React, { useEffect, useState } from 'react';
import { AppShell } from '../components/AppShell';
import { useWorldStore } from '../store/useWorldStore';
import { useNavigate } from 'react-router-dom';
import {
  getTimeline,
  reorderEvents,
  deleteEvent,
  createEvent,
  type EventResponse,
} from '../api/events';

export const WorldTimeline: React.FC = () => {
  const navigate = useNavigate();
  const {
    activeWorldId,
    setActiveManuscript,
    setActiveChapter,
    manuscripts,
  } = useWorldStore();

  const [events, setEvents] = useState<EventResponse[]>([]);
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // New event modal state
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [newDescription, setNewDescription] = useState('');
  const [newEventType, setNewEventType] = useState('EVENT');
  const [newChapterId, setNewChapterId] = useState<string>('');
  const [creating, setCreating] = useState(false);

  const chapters = manuscripts.flatMap((m) => m.chapters || []);

  const loadTimeline = async (worldId: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await getTimeline(worldId);
      setEvents(data.events || []);
      if (data.events?.length > 0 && !selectedEventId) {
        setSelectedEventId(data.events[0].id);
      }
    } catch (err: any) {
      console.error('Failed to load timeline:', err);
      setError(err?.message || 'Failed to load timeline');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (activeWorldId) {
      loadTimeline(activeWorldId);
    }
  }, [activeWorldId]);

  const selectedEvent = events.find((e) => e.id === selectedEventId) || events[0];

  const handleSelectEvent = (id: string) => {
    setSelectedEventId(id);
  };

  const navigateToChapter = (chapterId: string) => {
    setActiveManuscript('ms-1');
    setActiveChapter(chapterId);
    navigate(`/worlds/${activeWorldId}/manuscripts/ms-1`);
  };

  const handleMoveUp = async (e: React.MouseEvent, event: EventResponse) => {
    e.stopPropagation();
    if (!activeWorldId) return;

    const chapterEvents = events.filter((ev) => ev.chapter_id === event.chapter_id);
    const idx = chapterEvents.findIndex((ev) => ev.id === event.id);
    if (idx <= 0) return;

    const newOrder = [...chapterEvents];
    const temp = newOrder[idx - 1];
    newOrder[idx - 1] = newOrder[idx];
    newOrder[idx] = temp;
    const eventIds = newOrder.map((ev) => ev.id);

    try {
      await reorderEvents(activeWorldId, {
        chapter_id: event.chapter_id,
        event_ids: eventIds,
      });
      await loadTimeline(activeWorldId);
    } catch (err: any) {
      console.error('Failed to reorder events:', err);
      setError(err?.message || 'Failed to reorder events');
    }
  };

  const handleMoveDown = async (e: React.MouseEvent, event: EventResponse) => {
    e.stopPropagation();
    if (!activeWorldId) return;

    const chapterEvents = events.filter((ev) => ev.chapter_id === event.chapter_id);
    const idx = chapterEvents.findIndex((ev) => ev.id === event.id);
    if (idx < 0 || idx >= chapterEvents.length - 1) return;

    const newOrder = [...chapterEvents];
    const temp = newOrder[idx + 1];
    newOrder[idx + 1] = newOrder[idx];
    newOrder[idx] = temp;
    const eventIds = newOrder.map((ev) => ev.id);

    try {
      await reorderEvents(activeWorldId, {
        chapter_id: event.chapter_id,
        event_ids: eventIds,
      });
      await loadTimeline(activeWorldId);
    } catch (err: any) {
      console.error('Failed to reorder events:', err);
      setError(err?.message || 'Failed to reorder events');
    }
  };

  const handleDeleteEvent = async (e: React.MouseEvent, eventId: string) => {
    e.stopPropagation();
    if (!activeWorldId) return;
    if (!confirm('Are you sure you want to delete this event?')) return;

    try {
      await deleteEvent(activeWorldId, eventId);
      if (selectedEventId === eventId) {
        setSelectedEventId(null);
      }
      await loadTimeline(activeWorldId);
    } catch (err: any) {
      console.error('Failed to delete event:', err);
      setError(err?.message || 'Failed to delete event');
    }
  };

  const handleCreateEvent = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeWorldId || !newDescription.trim()) return;

    setCreating(true);
    try {
      await createEvent(activeWorldId, {
        description: newDescription.trim(),
        event_type: newEventType.trim() || 'EVENT',
        chapter_id: newChapterId || null,
      });
      setNewDescription('');
      setNewEventType('EVENT');
      setNewChapterId('');
      setIsModalOpen(false);
      await loadTimeline(activeWorldId);
    } catch (err: any) {
      console.error('Failed to create event:', err);
      setError(err?.message || 'Failed to create event');
    } finally {
      setCreating(false);
    }
  };

  return (
    <AppShell>
      {/* Background radial effects */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-surface-container-high/20 via-void-black to-void-black -z-10 pointer-events-none"></div>

      <main className="flex-1 h-screen flex relative overflow-hidden select-none">
        {/* Timeline Canvas (Scrollable) */}
        <div className="flex-1 overflow-y-auto overflow-x-hidden relative scroll-smooth px-8 py-12 scrollbar-hide">
          <div className="max-w-4xl mx-auto relative min-h-full pb-32 pt-6">
            {/* Page Header */}
            <header className="mb-14 flex items-start justify-between">
              <div>
                <div className="flex items-center gap-3 mb-3">
                  <span className="material-symbols-outlined text-copper-glow text-2xl font-light">timeline</span>
                  <h1 className="font-display-lg text-display-lg text-starlight-white">Chronicle Timeline</h1>
                </div>
                <p className="font-body-lg text-body-lg text-on-surface-variant/80 leading-relaxed max-w-xl">
                  Track how world parameters, faction controls, and character states transition across chronological milestones.
                </p>
              </div>

              <button
                onClick={() => setIsModalOpen(true)}
                className="flex items-center gap-2 px-4 py-2 bg-primary/20 hover:bg-primary/30 text-primary border border-primary/40 rounded-lg text-sm font-medium transition-colors"
              >
                <span className="material-symbols-outlined text-base">add</span>
                Add Event
              </button>
            </header>

            {error && (
              <div className="mb-6 p-4 rounded-lg bg-error/10 border border-error/30 text-error text-sm flex items-center justify-between">
                <span>{error}</span>
                <button onClick={() => setError(null)} className="text-xs hover:underline">Dismiss</button>
              </div>
            )}

            {/* The Central Line */}
            {events.length > 0 && (
              <div className="absolute left-[50%] top-44 bottom-24 w-[1px] timeline-line -translate-x-1/2 z-0" />
            )}

            {/* Timeline Events Stack */}
            {events.length === 0 && !loading ? (
              <div className="text-center py-24 text-on-surface-variant/60">
                <span className="material-symbols-outlined text-4xl mb-2 opacity-50">event_busy</span>
                <p>No events recorded in this timeline yet.</p>
              </div>
            ) : (
              <div className="relative z-10 flex flex-col gap-20 mt-12">
                {events.map((event, idx) => {
                  const isLeft = idx % 2 === 0;
                  const isActive = event.id === selectedEventId;

                  // Find index within the same chapter
                  const chapterEvents = events.filter((ev) => ev.chapter_id === event.chapter_id);
                  const idxInChapter = chapterEvents.findIndex((ev) => ev.id === event.id);
                  const canMoveUp = idxInChapter > 0;
                  const canMoveDown = idxInChapter >= 0 && idxInChapter < chapterEvents.length - 1;

                  return (
                    <div
                      key={event.id}
                      onClick={() => handleSelectEvent(event.id)}
                      className={`flex items-center w-full relative group cursor-pointer ${
                        isLeft ? 'justify-end pr-12 text-right w-1/2' : 'justify-start pl-12 ml-auto w-1/2 text-left'
                      }`}
                    >
                      {/* Node Dot Indicator */}
                      <div
                        className={`absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full border border-background transition-all duration-300 z-20 ${
                          isLeft ? 'right-[-6px]' : 'left-[-6px]'
                        } ${
                          isActive
                            ? 'bg-primary timeline-node-active scale-125 border-primary shadow-[0_0_12px_rgba(254,182,141,0.8)]'
                            : 'bg-outline-variant group-hover:bg-primary'
                        }`}
                      />

                      {/* Active Halo Glow */}
                      {isActive && (
                        <div
                          className={`absolute top-1/2 -translate-y-1/2 w-10 h-10 rounded-full bg-primary/15 blur-[6px] z-10 pointer-events-none ${
                            isLeft ? 'right-[-20px]' : 'left-[-20px]'
                          }`}
                        />
                      )}

                      {/* Event Info Block */}
                      <div
                        className={`transition-all duration-300 w-full max-w-md ${
                          isActive
                            ? 'glass-card p-5 rounded-xl border border-primary/30 relative overflow-hidden shadow-2xl scale-[1.02]'
                            : 'opacity-65 hover:opacity-100'
                        }`}
                      >
                        {isActive && (
                          <div className="absolute inset-0 bg-gradient-to-r from-primary/5 to-transparent pointer-events-none" />
                        )}

                        <div className={`flex items-center gap-2 mb-1.5 ${isLeft ? 'justify-end' : 'justify-start'}`}>
                          <span
                            className={`font-label-sm text-[10px] uppercase tracking-widest ${
                              isActive ? 'text-primary' : 'text-primary/60'
                            }`}
                          >
                            {event.chapter_number !== null
                              ? `Chapter ${event.chapter_number}`
                              : 'No Chapter'}
                            {event.sequence_index !== null ? ` • Seq #${event.sequence_index}` : ''}
                          </span>

                          {/* Reordering Chevrons & Actions */}
                          <div
                            className="flex items-center gap-0.5 ml-2 opacity-0 group-hover:opacity-100 transition-opacity"
                            onClick={(e) => e.stopPropagation()}
                          >
                            <button
                              disabled={!canMoveUp}
                              onClick={(e) => handleMoveUp(e, event)}
                              className="p-0.5 rounded hover:bg-white/10 disabled:opacity-20 text-on-surface-variant hover:text-primary transition-colors"
                              title="Move earlier in chapter"
                            >
                              <span className="material-symbols-outlined text-sm">arrow_upward</span>
                            </button>
                            <button
                              disabled={!canMoveDown}
                              onClick={(e) => handleMoveDown(e, event)}
                              className="p-0.5 rounded hover:bg-white/10 disabled:opacity-20 text-on-surface-variant hover:text-primary transition-colors"
                              title="Move later in chapter"
                            >
                              <span className="material-symbols-outlined text-sm">arrow_downward</span>
                            </button>
                            <button
                              onClick={(e) => handleDeleteEvent(e, event.id)}
                              className="p-0.5 rounded hover:bg-white/10 text-on-surface-variant hover:text-error transition-colors"
                              title="Delete event"
                            >
                              <span className="material-symbols-outlined text-sm">delete</span>
                            </button>
                          </div>
                        </div>

                        <h3
                          className={`font-headline-md text-headline-md group-hover:text-primary transition-colors text-base font-bold ${
                            isActive ? 'text-starlight-white' : 'text-on-surface'
                          }`}
                        >
                          {event.event_type.replace(/_/g, ' ')}
                        </h3>

                        <p className="font-body-md text-xs text-on-surface-variant/80 mt-2 leading-relaxed">
                          {event.description}
                        </p>

                        {event.participants.length > 0 && (
                          <div className={`mt-3 flex flex-wrap gap-1.5 ${isLeft ? 'justify-end' : 'justify-start'}`}>
                            {event.participants.map((p, pIdx) => (
                              <span
                                key={pIdx}
                                className="px-2 py-0.5 rounded bg-surface-container/60 border border-white/5 text-[10px] text-on-surface-variant"
                              >
                                {p.entity_name || p.entity_id} ({p.role.toLowerCase()})
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* Dynamic World State Changes wing inside the main stage (Right side wing) */}
        <aside className="w-[340px] bg-surface-container-low/95 border-l border-starlight-white/10 flex flex-col h-full shrink-0 z-20">
          {/* Header */}
          <div className="p-6 border-b border-starlight-white/5 bg-gradient-to-b from-surface-container-highest/20 to-transparent pt-14">
            <span className="font-label-sm text-[10px] text-primary/70 block mb-1 tracking-wider uppercase">
              Event Chronicle
            </span>
            <h2 className="font-headline-md text-headline-md text-starlight-white leading-tight text-lg">
              {selectedEvent ? selectedEvent.event_type.replace(/_/g, ' ') : 'No Selection'}
            </h2>
            <p className="font-label-sm text-[10px] text-on-surface-variant/50 uppercase tracking-widest mt-1">
              {selectedEvent?.chapter_number !== null && selectedEvent?.chapter_number !== undefined
                ? `Chapter ${selectedEvent.chapter_number}`
                : 'No Chapter'}
              {selectedEvent?.sequence_index !== null && selectedEvent?.sequence_index !== undefined
                ? ` • Sequence #${selectedEvent.sequence_index}`
                : ''}
            </p>
          </div>

          {/* Details Scroll */}
          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            {selectedEvent ? (
              <>
                {/* Description */}
                <div className="space-y-2">
                  <h3 className="font-label-sm text-[11px] text-on-surface-variant uppercase tracking-wider border-b border-starlight-white/5 pb-2">
                    Description
                  </h3>
                  <p className="font-body-md text-xs text-on-surface leading-relaxed">
                    {selectedEvent.description}
                  </p>
                </div>

                {/* Participants */}
                <div className="space-y-3">
                  <h3 className="font-label-sm text-[11px] text-on-surface-variant uppercase tracking-wider flex items-center gap-2 border-b border-starlight-white/5 pb-2">
                    <span className="material-symbols-outlined text-[16px] font-light">group</span>
                    Participants ({selectedEvent.participants.length})
                  </h3>

                  {selectedEvent.participants.length === 0 ? (
                    <p className="text-xs text-on-surface-variant/40 italic">No participants listed.</p>
                  ) : (
                    <div className="space-y-2">
                      {selectedEvent.participants.map((p, idx) => (
                        <div
                          key={idx}
                          className="bg-surface-container/40 p-3 rounded-lg border border-starlight-white/5 flex items-center justify-between text-xs"
                        >
                          <div className="flex items-center gap-2">
                            <span className="material-symbols-outlined text-sm text-primary">person</span>
                            <span className="text-starlight-white font-medium">
                              {p.entity_name || p.entity_id}
                            </span>
                          </div>
                          <span className="text-[10px] px-2 py-0.5 rounded bg-primary/10 text-primary uppercase">
                            {p.role}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Source Manuscript / Chapter */}
                {selectedEvent.chapter_id && (
                  <div className="space-y-3">
                    <h3 className="font-label-sm text-[11px] text-on-surface-variant uppercase tracking-wider border-b border-starlight-white/5 pb-2">
                      Linked Chapter
                    </h3>
                    <button
                      onClick={() => navigateToChapter(selectedEvent.chapter_id!)}
                      className="w-full text-left p-3 rounded-lg border border-starlight-white/5 hover:border-primary/30 hover:bg-white/5 transition-all flex items-center gap-3 group"
                    >
                      <span className="material-symbols-outlined text-on-surface-variant group-hover:text-primary transition-colors text-lg font-light">
                        menu_book
                      </span>
                      <div className="min-w-0">
                        <span className="block font-body-md text-xs text-starlight-white group-hover:text-primary transition-colors truncate">
                          Chapter {selectedEvent.chapter_number ?? ''}
                        </span>
                        <span className="block font-label-sm text-[10px] text-on-surface-variant/50 mt-0.5 truncate">
                          ID: {selectedEvent.chapter_id}
                        </span>
                      </div>
                    </button>
                  </div>
                )}

                {/* Danger zone */}
                <div className="pt-4 border-t border-starlight-white/5">
                  <button
                    onClick={(e) => handleDeleteEvent(e, selectedEvent.id)}
                    className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-error/10 hover:bg-error/20 text-error border border-error/30 text-xs font-medium transition-colors"
                  >
                    <span className="material-symbols-outlined text-sm">delete</span>
                    Delete Event
                  </button>
                </div>
              </>
            ) : (
              <p className="text-xs text-on-surface-variant/40 italic">Select an event to view details.</p>
            )}
          </div>
        </aside>
      </main>

      {/* Create Event Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <div className="bg-surface-container border border-starlight-white/10 rounded-xl p-6 max-w-lg w-full shadow-2xl">
            <h2 className="text-lg font-bold text-starlight-white mb-4 flex items-center gap-2">
              <span className="material-symbols-outlined text-primary">add_circle</span>
              Add Chronicle Event
            </h2>

            <form onSubmit={handleCreateEvent} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-on-surface-variant mb-1 uppercase tracking-wider">
                  Description *
                </label>
                <textarea
                  rows={3}
                  required
                  value={newDescription}
                  onChange={(e) => setNewDescription(e.target.value)}
                  placeholder="Describe what occurs at this milestone..."
                  className="w-full rounded-lg bg-surface-container-high border border-starlight-white/10 px-3 py-2 text-sm text-starlight-white focus:outline-none focus:border-primary/50"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-on-surface-variant mb-1 uppercase tracking-wider">
                  Event Type
                </label>
                <input
                  type="text"
                  value={newEventType}
                  onChange={(e) => setNewEventType(e.target.value)}
                  placeholder="e.g. BATTLE, ARRIVAL, MEETING"
                  className="w-full rounded-lg bg-surface-container-high border border-starlight-white/10 px-3 py-2 text-sm text-starlight-white focus:outline-none focus:border-primary/50"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-on-surface-variant mb-1 uppercase tracking-wider">
                  Chapter
                </label>
                <select
                  value={newChapterId}
                  onChange={(e) => setNewChapterId(e.target.value)}
                  className="w-full rounded-lg bg-surface-container-high border border-starlight-white/10 px-3 py-2 text-sm text-starlight-white focus:outline-none focus:border-primary/50"
                >
                  <option value="">No chapter (unassigned)</option>
                  {chapters.map((ch) => (
                    <option key={ch.id} value={ch.id}>
                      Chapter {ch.number}: {ch.title}
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex items-center justify-end gap-3 pt-3 border-t border-starlight-white/5">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="px-4 py-2 rounded-lg text-sm text-on-surface-variant hover:text-starlight-white transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creating || !newDescription.trim()}
                  className="px-4 py-2 rounded-lg text-sm bg-primary text-surface-container font-semibold hover:bg-primary/90 transition-colors disabled:opacity-50"
                >
                  {creating ? 'Creating...' : 'Create Event'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </AppShell>
  );
};
