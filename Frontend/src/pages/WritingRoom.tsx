import React, { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { useWorldStore } from '../store/useWorldStore';
import { apiFetch } from '../api/client';
import { getProposals } from '../api/proposals';
import type { ProposalsResponse } from '../api/proposals';
import { ProposalReviewModal } from '../components/ProposalReviewModal';

export const WritingRoom: React.FC = () => {
  const navigate = useNavigate();
  const { worldId, manuscriptId } = useParams<{ worldId: string; manuscriptId: string }>();
  
  const { 
    manuscripts, 
    activeManuscriptId,
    activeChapterId,
    setActiveChapter, 
    entities,
    setActiveEntity,
    updateChapterContent,
    fetchManuscriptsForWorld,
    deleteChapter
  } = useWorldStore();

  const currentWorldId = worldId;
  const currentManuscriptId = manuscriptId || activeManuscriptId;

  useEffect(() => {
    if (currentWorldId && currentManuscriptId) {
      const exists = manuscripts.some((m) => m.id === currentManuscriptId);
      if (!exists || manuscripts.length === 0) {
        fetchManuscriptsForWorld(currentWorldId);
      }
    }
  }, [currentWorldId, currentManuscriptId, manuscripts, fetchManuscriptsForWorld]);

  // A link from a contradiction: ?chapter=<id>&start=<offset>&end=<offset> opens that chapter at the cited words
  const [searchParams] = useSearchParams();
  const linkedChapterId = searchParams.get('chapter');
  const linkStart = Number(searchParams.get('start'));
  const linkEnd = Number(searchParams.get('end'));
  useEffect(() => {
    if (linkedChapterId) setActiveChapter(linkedChapterId);
  }, [linkedChapterId, setActiveChapter]);

  const manuscript = manuscripts.find((m) => m.id === currentManuscriptId);
  const activeChapter = manuscript?.chapters.find((ch) => ch.id === activeChapterId) || manuscript?.chapters[0];

  const [isEditing, setIsEditing] = useState(false);
  const [editorContent, setEditorContent] = useState('');
  const [isExtracting, setIsExtracting] = useState(false);
  const [extractionStatus, setExtractionStatus] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [historyVersions, setHistoryVersions] = useState<any[]>([]);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [review, setReview] = useState<ProposalsResponse | null>(null);

  useEffect(() => {
    if (activeChapter) {
      setEditorContent(activeChapter.content);

      if (currentWorldId) {
        apiFetch<any>(`/worlds/${currentWorldId}/chapters/${activeChapter.id}`)
          .then(data => {
            if (data.content) {
              setEditorContent(data.content);
              updateChapterContent(currentManuscriptId, activeChapter.id, data.content);
            }
          })
          .catch(() => {});
      }
    }
  }, [activeChapterId, currentWorldId]);

  useEffect(() => {
    if (linkedChapterId && activeChapter?.id === linkedChapterId) {
      document.getElementById('orion-cited')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [linkedChapterId, activeChapter?.id, activeChapter?.content]);

  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const adjustTextareaHeight = () => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = 'auto';
      el.style.height = `${Math.max(400, el.scrollHeight)}px`;
    }
  };

  useEffect(() => {
    if (isEditing) {
      adjustTextareaHeight();
    }
  }, [isEditing, editorContent]);

  const handleStartEdit = () => {
    if (activeChapter) {
      setEditorContent(activeChapter.content);
      setIsEditing(true);
    }
  };

  const handleCancelEdit = () => {
    setIsEditing(false);
    if (activeChapter) {
      setEditorContent(activeChapter.content);
    }
  };

  const handleSaveEdit = async () => {
    if (!activeChapter || !manuscript) return;
    
    // Update local state first
    updateChapterContent(manuscript.id, activeChapter.id, editorContent);
    setIsEditing(false);

    // Call API to trigger re-extraction if real world
    if (currentWorldId) {
      setIsExtracting(true);
      setExtractionStatus('Re-extracting entities & facts...');
      try {
        const res = await apiFetch<any>(`/worlds/${currentWorldId}/chapters/${activeChapter.id}`, {
          method: 'PUT',
          body: JSON.stringify({
            title: activeChapter.title,
            content: editorContent
          })
        });

        if (res.job_id) {
          // Poll job status
          const poll = setInterval(async () => {
            try {
              const statusData = await apiFetch<any>(`/jobs/${res.job_id}/status`);
              if (statusData.status === 'done') {
                clearInterval(poll);
                setIsExtracting(false);
                // Re-extraction proposes; nothing changes in the world until the author applies it (docs/api.md §17)
                try {
                  const found = await getProposals(res.job_id);
                  setReview(found);
                  setExtractionStatus(null);
                } catch {
                  setExtractionStatus('Extraction finished, but its proposals could not be loaded.');
                  setTimeout(() => setExtractionStatus(null), 4000);
                }
              } else if (statusData.status === 'failed') {
                clearInterval(poll);
                setIsExtracting(false);
                setExtractionStatus('Extraction failed: ' + (statusData.error_message || 'Error'));
              }
            } catch (_) {
              clearInterval(poll);
              setIsExtracting(false);
            }
          }, 1500);
        } else {
          setIsExtracting(false);
          setExtractionStatus(null);
        }
      } catch (err: any) {
        setIsExtracting(false);
        console.error("Failed to update chapter via API", err);
      }
    }
  };

  const handleRerunExtraction = async () => {
    if (!activeChapter) return;
    handleSaveEdit();
  };

  const handleCreateChapter = async () => {
    const title = prompt('Enter new chapter title:');
    if (title && title.trim()) {
      const nextNum = (manuscript?.chapters.length || 0) + 1;
      let newChapter = {
        id: '',
        number: nextNum,
        title: title.trim(),
        content: '',
        wordCount: 0
      };

      if (currentWorldId && currentManuscriptId) {
        try {
          const res = await apiFetch<any>(`/worlds/${currentWorldId}/manuscripts/${currentManuscriptId}/chapters`, {
            method: 'POST',
            body: JSON.stringify({
              chapter_number: nextNum,
              title: title.trim(),
              content: ''
            })
          });
          newChapter.id = res.id;
          newChapter.number = res.chapter_number;
          newChapter.title = res.title;
          if (res.content) newChapter.content = res.content;
        } catch (err: any) {
          alert('Failed to create chapter: ' + err.message);
          return;
        }
      }

      if (manuscript) {
        const updated = [...manuscript.chapters, newChapter];
        const updatedManuscripts = manuscripts.map(m => 
          m.id === manuscript.id ? { ...m, chapters: updated } : m
        );
        useWorldStore.setState({ manuscripts: updatedManuscripts, activeChapterId: newChapter.id });
      }
    }
  };

  const handleDeleteChapter = (e: React.MouseEvent, chapterId: string) => {
    e.stopPropagation();
    setDeleteConfirmId(chapterId);
  };

  const executeDeleteChapter = async () => {
    if (!deleteConfirmId) return;
    const chapterId = deleteConfirmId;
    
    if (currentWorldId) {
      try {
        await apiFetch(`/worlds/${currentWorldId}/chapters/${chapterId}`, {
          method: 'DELETE'
        });
      } catch (err: any) {
        alert('Failed to delete chapter: ' + err.message);
        setDeleteConfirmId(null);
        return;
      }
    }

    if (manuscript) {
      const remaining = manuscript.chapters.filter(c => c.id !== chapterId);
      deleteChapter(manuscript.id, chapterId);
      if (remaining.length === 0) {
        navigate(`/worlds/${currentWorldId}/manuscripts`);
      } else if (activeChapterId === chapterId) {
        setActiveChapter(remaining[0]?.id || null);
      }
    }
    setDeleteConfirmId(null);
  };

  const handleViewHistory = async () => {
    if (!activeChapter || !currentWorldId) return;
    try {
      const versions = await apiFetch<any[]>(`/worlds/${currentWorldId}/chapters/${activeChapter.id}/versions`);
      setHistoryVersions(versions);
      setShowHistory(true);
    } catch (err: any) {
      alert('Failed to load history: ' + err.message);
    }
  };


  // Helper to split text by entity names and inject interactive highlight tags
  const renderTextWithHighlights = (text: string) => {
    if (!text) return null;
    const activeEntities = entities;

    if (activeEntities.length === 0) return <span>{text}</span>;

    const sortedEntityNames = [...activeEntities]
      .map(e => e.name)
      .filter(Boolean)
      .sort((a, b) => b.length - a.length);

    if (sortedEntityNames.length === 0) return <span>{text}</span>;

    const escapedNames = sortedEntityNames.map(name => 
      name.replace(/[-\/\\^$*+?.()|[\]{}]/g, '\\$&')
    );

    const regex = new RegExp(`\\b(${escapedNames.join('|')})\\b`, 'gi');
    const parts = text.split(regex);
    if (parts.length <= 1) return <span>{text}</span>;

    return (
      <span>
        {parts.map((part, index) => {
          const matchedEntity = activeEntities.find(
            e => e.name.toLowerCase() === part.toLowerCase()
          );

          if (matchedEntity) {
            return (
              <span 
                key={index} 
                className="entity-highlight text-starlight-white font-medium cursor-pointer hover:underline"
                title={`${matchedEntity.type.toUpperCase()}: Click to view profile`}
                onClick={(e) => {
                  e.stopPropagation();
                  setActiveEntity(matchedEntity.id);
                }}
              >
                {part}
              </span>
            );
          }
          return part;
        })}
      </span>
    );
  };

  return (
    <AppShell>
      {/* Editor Main Section */}
      <main className="flex-1 flex h-full bg-[#09090b] relative overflow-hidden select-text">
        
        {/* Left internal sidebar: Chapters List */}
        <aside className="w-72 border-r border-starlight-white/5 bg-surface-container-lowest flex flex-col shrink-0 select-none">
          <div className="p-4 border-b border-starlight-white/5 flex items-center justify-between bg-gradient-to-b from-surface-container-highest/20 to-transparent">
            <h2 className="font-label-sm text-label-sm text-on-surface-variant uppercase tracking-widest text-[10px]">Chapters</h2>
            <button 
              onClick={handleCreateChapter}
              className="text-on-surface-variant/65 hover:text-primary transition-colors p-1"
            >
              <span className="material-symbols-outlined text-sm font-light">add</span>
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-3 space-y-1">
            {manuscript?.chapters.map((ch) => {
              const isActive = ch.id === (activeChapterId || activeChapter?.id);
              return (
                <div 
                  key={ch.id}
                  onClick={() => {
                    setActiveChapter(ch.id);
                    setIsEditing(false);
                  }}
                  className={`group px-4 py-3 rounded-lg relative overflow-hidden cursor-pointer transition-all duration-300 border ${
                    isActive 
                      ? 'bg-surface-container-low border-starlight-white/10 text-starlight-white' 
                      : 'border-transparent text-on-surface-variant/75 hover:bg-surface-container-lowest/50 hover:text-on-surface'
                  }`}
                >
                  {isActive && (
                    <>
                      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-primary/5 via-transparent to-transparent opacity-50"></div>
                      <div className="absolute left-0 top-0 bottom-0 w-0.5 bg-primary"></div>
                    </>
                  )}
                  <div className={`font-label-sm text-[10px] uppercase tracking-wider mb-1 flex justify-between items-center ${isActive ? 'text-primary' : 'text-on-surface-variant/40'}`}>
                    <span>Chapter {ch.number}</span>
                    <button 
                      onClick={(e) => handleDeleteChapter(e, ch.id)}
                      className="opacity-0 group-hover:opacity-100 transition-opacity hover:text-red-400"
                      title="Delete Chapter"
                    >
                      <span className="material-symbols-outlined text-[14px]">delete</span>
                    </button>
                  </div>
                  <div className="font-body-md text-sm font-medium pr-4">{ch.title}</div>
                </div>
              );
            })}
          </div>
        </aside>

        {/* Right main panel: Editor Canvas */}
        <section className="flex-1 flex flex-col relative overflow-hidden">
          


          {/* Action Bar */}
          <div className="h-16 flex items-center justify-between px-8 border-b border-starlight-white/5 bg-surface-container-lowest/60 backdrop-blur-sm z-20 select-none">
            <div className="flex items-center gap-3">
              {isEditing ? (
                <>
                  <button 
                    onClick={handleSaveEdit}
                    className="px-5 py-1.5 rounded-full bg-primary hover:bg-copper-glow text-void-black font-label-sm text-xs font-semibold uppercase tracking-widest transition-all duration-300 shadow-md"
                  >
                    Save Changes
                  </button>
                  <button 
                    onClick={handleCancelEdit}
                    className="px-4 py-1.5 rounded-full border border-starlight-white/10 text-on-surface-variant/80 hover:text-starlight-white hover:border-starlight-white/30 font-label-sm text-xs font-semibold uppercase tracking-widest transition-all duration-300"
                  >
                    Cancel
                  </button>
                </>
              ) : (
                <button 
                  onClick={handleStartEdit}
                  className="px-5 py-1.5 rounded-full border border-copper-glow/50 text-copper-glow font-label-sm text-xs font-semibold uppercase tracking-widest hover:bg-copper-glow hover:text-void-black transition-all duration-300"
                >
                  Edit Text
                </button>
              )}

              <button 
                onClick={handleRerunExtraction}
                disabled={isExtracting}
                className="px-4 py-1.5 rounded-full text-on-surface-variant/80 font-label-sm text-xs uppercase tracking-wider hover:text-primary hover:bg-primary/5 transition-all flex items-center gap-2 disabled:opacity-50"
              >
                <span className={`material-symbols-outlined text-[16px] font-light ${isExtracting ? 'animate-spin' : ''}`}>
                  {isExtracting ? 'sync' : 'refresh'}
                </span>
                {isExtracting ? 'Extracting...' : 'Re-run Extraction'}
              </button>

              {!isEditing && (
                <button 
                  onClick={handleViewHistory}
                  className="px-4 py-1.5 rounded-full text-on-surface-variant/80 font-label-sm text-xs uppercase tracking-wider hover:text-primary hover:bg-primary/5 transition-all flex items-center gap-2"
                >
                  <span className="material-symbols-outlined text-[16px] font-light">history</span>
                  History
                </button>
              )}
            </div>

            <div className="flex items-center gap-4 text-on-surface-variant/40 font-label-sm text-[10px] uppercase tracking-wider">
              <span>Words: {activeChapter?.wordCount.toLocaleString()}</span>
              <span>•</span>
              <span>{isExtracting ? 'Re-extracting' : 'Synced'}</span>
            </div>
          </div>

          {/* Reading/Editing Area */}
          <div className="flex-1 overflow-y-auto px-8 md:px-24 py-16">
            <article className="max-w-3xl mx-auto pb-48">
              
              {/* Header Title */}
              <header className="mb-12 select-none">
                <span className="font-label-sm text-[10px] text-primary uppercase tracking-[0.2em] mb-3 block">
                  Chapter {activeChapter?.number}
                </span>
                <h1 className="font-display-lg text-display-lg text-starlight-white mb-6">
                  {activeChapter?.title}
                </h1>
                <div className="h-px w-24 bg-gradient-to-r from-copper-glow to-transparent opacity-50"></div>
              </header>

              {/* Editable Textbox or Formatted View */}
              {isEditing ? (
                <textarea 
                  ref={textareaRef}
                  value={editorContent}
                  onChange={(e) => {
                    setEditorContent(e.target.value);
                    adjustTextareaHeight();
                  }}
                  className="w-full bg-transparent border-0 text-body-lg text-on-surface-variant leading-relaxed focus:ring-0 focus:outline-none resize-none overflow-hidden"
                  style={{ fontFamily: 'Source Serif 4, serif', fontSize: '18px', lineHeight: '28px' }}
                />
              ) : (
                <div 
                  className="prose prose-invert prose-lg font-body-lg text-body-lg text-on-surface-variant leading-relaxed space-y-8 select-text"
                  style={{ fontFamily: 'Source Serif 4, serif', fontSize: '18px', lineHeight: '28px' }}
                >
                  {(() => {
                    const cited = activeChapter && activeChapter.id === linkedChapterId && linkEnd > linkStart
                      ? { start: linkStart, end: linkEnd } : null;
                    let offset = 0;                                   // each '\n\n' separator is 2 characters
                    return activeChapter?.content.split('\n\n').map((paragraph, index) => {
                      const from = offset;
                      offset += paragraph.length + 2;
                      if (!cited || cited.start >= from + paragraph.length || cited.end <= from) {
                        return <p key={index}>{renderTextWithHighlights(paragraph)}</p>;
                      }
                      const a = Math.max(0, cited.start - from), b = Math.min(paragraph.length, cited.end - from);
                      return (
                        <p key={index} id="orion-cited">
                          {renderTextWithHighlights(paragraph.slice(0, a))}
                          <mark className="bg-error/20 text-starlight-white border-b-2 border-error rounded-sm px-0.5">
                            {paragraph.slice(a, b)}
                          </mark>
                          {renderTextWithHighlights(paragraph.slice(b))}
                        </p>
                      );
                    });
                  })()}
                </div>
              )}

            </article>
          </div>

        </section>

      </main>

      {/* History Modal */}
      {showHistory && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-void-black/80 backdrop-blur-sm">
          <div className="bg-surface-container-high border border-starlight-white/10 rounded-lg shadow-2xl max-w-2xl w-full max-h-[80vh] flex flex-col">
            <div className="p-6 border-b border-starlight-white/5 flex justify-between items-center">
              <h2 className="font-headline-md text-starlight-white">Chapter History</h2>
              <button onClick={() => setShowHistory(false)} className="text-on-surface-variant/60 hover:text-primary">
                <span className="material-symbols-outlined">close</span>
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-6 space-y-4">
              {historyVersions.length === 0 ? (
                <p className="text-on-surface-variant/60 text-sm">No history available.</p>
              ) : (
                historyVersions.map((v: any) => (
                  <div key={v.id} className="p-4 rounded border border-starlight-white/5 bg-surface-container-low flex justify-between items-center">
                    <div>
                      <h3 className="text-starlight-white text-sm font-medium">Version {v.version_number} {v.is_current ? '(Current)' : ''}</h3>
                      <p className="text-on-surface-variant/60 text-xs mt-1">Saved: {new Date(v.created_at).toLocaleString()}</p>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {review && (
        <ProposalReviewModal
          worldId={currentWorldId}
          chapterNumber={review.chapter_number}
          proposals={review.proposals}
          onClose={(applied) => {
            setReview(null);
            if (applied) {
              useWorldStore.getState().fetchEntitiesForWorld(currentWorldId);
              setExtractionStatus('Changes applied to your world.');
              setTimeout(() => setExtractionStatus(null), 3000);
            }
          }}
        />
      )}

      {/* Floating Extraction Toast */}
      <div 
        className={`fixed bottom-8 right-8 z-50 flex items-center gap-3 px-5 py-3 rounded-xl bg-surface-container-high/90 backdrop-blur-md border border-primary/30 shadow-[0_8px_32px_rgba(235,166,134,0.15)] transition-all duration-500 transform ${
          extractionStatus ? 'translate-y-0 opacity-100' : 'translate-y-8 opacity-0 pointer-events-none'
        }`}
      >
        <span className="material-symbols-outlined text-primary text-xl animate-spin">refresh</span>
        <span className="font-label-sm text-sm text-starlight-white tracking-wide">{extractionStatus}</span>
      </div>

      {/* Delete Confirmation Modal */}
      {deleteConfirmId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-void-black/80 backdrop-blur-sm">
          <div className="bg-surface-container-high border border-primary/30 rounded-xl shadow-[0_8px_32px_rgba(235,166,134,0.15)] max-w-md w-full p-6 flex flex-col gap-4 animate-in fade-in zoom-in-95 duration-200">
            <h3 className="font-headline-sm text-starlight-white flex items-center gap-2">
              <span className="material-symbols-outlined text-primary">warning</span>
              Delete Chapter
            </h3>
            <p className="text-on-surface-variant text-sm leading-relaxed">
              Are you sure you want to delete this chapter? This action cannot be undone and will permanently remove its content.
            </p>
            <div className="flex justify-end gap-3 mt-4">
              <button
                onClick={() => setDeleteConfirmId(null)}
                className="px-4 py-2 rounded-lg font-label-sm text-sm text-starlight-white/70 hover:text-starlight-white hover:bg-surface-container-highest transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={executeDeleteChapter}
                className="px-4 py-2 rounded-lg font-label-sm text-sm bg-primary/20 text-primary border border-primary/50 hover:bg-primary hover:text-void-black transition-colors shadow-md"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
};

