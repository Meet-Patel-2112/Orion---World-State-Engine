import React, { useState, useEffect } from 'react';
import { AppShell } from '../components/AppShell';
import { useWorldStore } from '../store/useWorldStore';
import { AnimatePresence, motion } from 'framer-motion';

export const Contradictions: React.FC = () => {
  const { contradictions, activeWorldId, fetchContradictionsForWorld, resolveContradictionInBackend, setActiveEntity } = useWorldStore();

  useEffect(() => {
    if (activeWorldId) {
      fetchContradictionsForWorld(activeWorldId);
    }
  }, [activeWorldId, fetchContradictionsForWorld]);
  
  // Track which contradiction is actively resolving (to show resolution choices)
  const [resolvingId, setResolvingId] = useState<string | null>(null);
  const [resolutionChoice, setResolutionChoice] = useState<string | null>(null);

  // Unresolved contradictions list
  const activeContradictions = contradictions.filter((c) => !c.resolved);

  const handleStartResolve = (id: string) => {
    setResolvingId(id);
    setResolutionChoice(null);
  };

  const handleExecuteResolve = (
    id: string,
    correctText: string,
    preferredFactVersionId?: string | null,
    preferredRelationshipVersionId?: string | null
  ) => {
    setResolutionChoice(correctText);
    
    // Briefly show selection, then animate out
    setTimeout(async () => {
      if (activeWorldId) {
        await resolveContradictionInBackend(
          activeWorldId,
          id,
          preferredFactVersionId,
          preferredRelationshipVersionId
        );
      }
      setResolvingId(null);
      setResolutionChoice(null);
    }, 800);
  };

  // Helper to render choice selectors based on contradiction data
  const renderResolveChoices = (c: typeof contradictions[0]) => {
    if (c.old_fact_version_id && c.new_fact_version_id) {
      return (
        <div className="space-y-3 mt-4 bg-void-black/60 p-4 rounded-lg border border-copper-glow/20 animate-fade-in-up">
          <p className="font-label-sm text-[10px] text-copper-glow uppercase tracking-wider">
            Establish Authority Fact Version
          </p>
          <div className="flex flex-col sm:flex-row gap-3">
            <button 
              onClick={() => handleExecuteResolve(c.id, 'Retained Old Version', c.old_fact_version_id, null)}
              className="flex-1 text-left p-3 rounded bg-surface-container hover:bg-surface-container-high border border-starlight-white/10 hover:border-copper-glow/50 text-xs text-starlight-white transition-all group"
            >
              <div className="font-semibold text-copper-glow text-xs mb-1 group-hover:underline flex items-center gap-1.5">
                <span className="material-symbols-outlined text-sm">history</span> Keep Old Version
              </div>
              <p className="text-[11px] text-on-surface-variant/70">
                Preserve the previously accepted fact version as ACTIVE and supersede the new conflicting version.
              </p>
            </button>
            <button 
              onClick={() => handleExecuteResolve(c.id, 'Adopted New Version', c.new_fact_version_id, null)}
              className="flex-1 text-left p-3 rounded bg-surface-container hover:bg-surface-container-high border border-starlight-white/10 hover:border-copper-glow/50 text-xs text-starlight-white transition-all group"
            >
              <div className="font-semibold text-emerald-400 text-xs mb-1 group-hover:underline flex items-center gap-1.5">
                <span className="material-symbols-outlined text-sm">update</span> Keep New Version
              </div>
              <p className="text-[11px] text-on-surface-variant/70">
                Adopt the new incoming version as ACTIVE and retire the older version to SUPERSEDED.
              </p>
            </button>
          </div>
        </div>
      );
    }

    if (c.old_relationship_version_id && c.new_relationship_version_id) {
      return (
        <div className="space-y-3 mt-4 bg-void-black/60 p-4 rounded-lg border border-copper-glow/20 animate-fade-in-up">
          <p className="font-label-sm text-[10px] text-copper-glow uppercase tracking-wider">
            Establish Authority Relationship Version
          </p>
          <div className="flex flex-col sm:flex-row gap-3">
            <button 
              onClick={() => handleExecuteResolve(c.id, 'Retained Old Relationship', null, c.old_relationship_version_id)}
              className="flex-1 text-left p-3 rounded bg-surface-container hover:bg-surface-container-high border border-starlight-white/10 hover:border-copper-glow/50 text-xs text-starlight-white transition-all group"
            >
              <div className="font-semibold text-copper-glow text-xs mb-1 group-hover:underline flex items-center gap-1.5">
                <span className="material-symbols-outlined text-sm">history</span> Keep Old Relationship
              </div>
              <p className="text-[11px] text-on-surface-variant/70">
                Preserve the previously recorded relationship type as ACTIVE.
              </p>
            </button>
            <button 
              onClick={() => handleExecuteResolve(c.id, 'Adopted New Relationship', null, c.new_relationship_version_id)}
              className="flex-1 text-left p-3 rounded bg-surface-container hover:bg-surface-container-high border border-starlight-white/10 hover:border-copper-glow/50 text-xs text-starlight-white transition-all group"
            >
              <div className="font-semibold text-emerald-400 text-xs mb-1 group-hover:underline flex items-center gap-1.5">
                <span className="material-symbols-outlined text-sm">update</span> Keep New Relationship
              </div>
              <p className="text-[11px] text-on-surface-variant/70">
                Adopt the newly asserted relationship version as ACTIVE.
              </p>
            </button>
          </div>
        </div>
      );
    }
    
    // Default fallback resolution choice
    return (
      <div className="space-y-2 mt-4 bg-void-black/60 p-4 rounded-lg border border-primary/20 animate-fade-in-up">
        <p className="font-label-sm text-[10px] text-primary uppercase tracking-wider mb-2">Establish Authority Value</p>
        <button 
          onClick={() => handleExecuteResolve(c.id, 'Acknowledged & Resolved')}
          className="w-full text-left p-3 rounded bg-surface-container hover:bg-surface-container-high border border-starlight-white/5 hover:border-primary/40 text-xs text-starlight-white transition-all"
        >
          <span className="text-primary font-bold">Acknowledge & Resolve</span>: Keep current state as canonical
        </button>
      </div>
    );
  };

  return (
    <AppShell>
      {/* Background gradients */}
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_bottom_right,rgba(230,162,126,0.025),transparent_40%)] -z-10 pointer-events-none"></div>

      <main className="flex-1 min-h-screen overflow-y-auto px-8 md:px-12 py-10">
        <div className="max-w-7xl mx-auto flex flex-col gap-8 animate-fade-in-up">
          
          {/* Header */}
          <header className="mb-6 max-w-3xl border-b border-starlight-white/5 pb-6">
            <div className="flex items-center gap-3 mb-4">
              <span className="material-symbols-outlined text-copper-glow text-2xl font-light">rule</span>
              <h1 className="font-display-lg text-display-lg text-starlight-white">Contradictions</h1>
            </div>
            <p className="font-body-lg text-body-lg text-on-surface-variant/80 max-w-2xl leading-relaxed">
              The Engine has detected potential inconsistencies within the active world state. Resolve conflicts to update manuscripts and sync ledger facts.
            </p>
          </header>

          {/* Conflict statistics summary */}
          <div className="flex items-center gap-6 bg-surface-container-low/30 border border-starlight-white/5 p-4 rounded-lg w-fit text-xs font-label-sm">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-error animate-pulse shadow-[0_0_8px_rgba(255,180,171,0.6)]" />
              <span className="text-on-surface-variant/80 uppercase tracking-wider">Unresolved Issues:</span>
              <span className="text-error font-bold text-sm ml-1">{activeContradictions.length}</span>
            </div>
            <div className="h-4 w-px bg-starlight-white/10" />
            <div className="text-on-surface-variant/40 uppercase tracking-wider">
              Scan Status: <span className="text-emerald-400 font-semibold ml-1">Live Engine Sync</span>
            </div>
          </div>

          {/* Cards Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 max-w-7xl pb-32">
            <AnimatePresence>
              {activeContradictions.map((c) => {
                const isResolving = resolvingId === c.id;

                return (
                  <motion.article 
                    key={c.id}
                    layout
                    initial={{ opacity: 0, y: 15 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, scale: 0.95, y: -20, transition: { duration: 0.4 } }}
                    className={`glass-panel rounded-xl p-6 flex flex-col gap-4 border transition-all duration-300 relative overflow-hidden group ${
                      c.severity === 'high' 
                        ? 'lg:col-span-2 border-starlight-white/5 hover:border-error/30' 
                        : 'border-starlight-white/5 hover:border-copper-glow/30'
                    }`}
                  >
                    {/* Radial light */}
                    <div className="absolute inset-0 bg-gradient-to-br from-copper-glow/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none"></div>

                    {/* Card Header */}
                    <header className="flex justify-between items-start border-b border-starlight-white/5 pb-4 select-none">
                      <div>
                        <span 
                          onClick={() => {
                            // Link character click to side wing
                            setActiveEntity(c.targetEntityId);
                          }}
                          className="font-label-sm text-xs text-copper-glow uppercase tracking-widest mb-1 block cursor-pointer hover:underline"
                        >
                          {c.category}
                        </span>
                        <h2 className="font-headline-md text-headline-md text-starlight-white font-bold">{c.title}</h2>
                      </div>
                      
                      <div className={`px-3 py-1 rounded-full border flex items-center gap-1.5 text-[10px] font-label-sm uppercase tracking-wider ${
                        c.severity === 'high' 
                          ? 'bg-error/5 text-error border-error/20' 
                          : 'bg-surface-container text-on-surface-variant/60 border-starlight-white/5'
                      }`}>
                        <span className="material-symbols-outlined text-[13px] font-light">info</span>
                        {c.severity} Priority
                      </div>
                    </header>

                    {/* Sources Side-by-side display */}
                    <div className={`flex-1 grid grid-cols-1 gap-4 py-2 ${c.severity === 'high' ? 'md:grid-cols-2' : ''}`}>
                      {c.sources.map((source, idx) => (
                        <div key={idx} className="bg-deep-charcoal/50 rounded-lg p-4 border border-starlight-white/5 flex flex-col gap-2">
                          <div className="font-label-sm text-[10px] text-on-surface-variant/40 mb-1 flex items-center gap-1.5 uppercase tracking-wider select-none">
                            <span className="material-symbols-outlined text-[14px] font-light">menu_book</span>
                            {source.sourceName}
                          </div>
                          
                          {/* Text passage with highlighted conflicting word */}
                          <p className="font-body-md text-sm text-inverse-surface leading-relaxed">
                            {source.text.split(source.highlightedWord).map((part, pIdx, arr) => (
                              <React.Fragment key={pIdx}>
                                {part}
                                {pIdx < arr.length - 1 && (
                                  <span className="text-error border-b border-error border-dashed px-0.5 font-semibold">
                                    {source.highlightedWord}
                                  </span>
                                )}
                              </React.Fragment>
                            ))}
                          </p>
                        </div>
                      ))}
                    </div>

                    {/* Interactive resolution panel */}
                    {isResolving && (
                      resolutionChoice ? (
                        <div className="bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 p-4 rounded-lg text-center text-xs font-semibold animate-pulse select-none">
                          <span className="material-symbols-outlined text-base align-middle mr-1.5">check_circle</span>
                          RESOLVED: {resolutionChoice}
                        </div>
                      ) : (
                        renderResolveChoices(c)
                      )
                    )}

                    {/* Card Footer Actions */}
                    {!isResolving && (
                      <footer className="mt-auto pt-4 flex items-center justify-between border-t border-starlight-white/5 select-none">
                        <p className="font-body-md text-xs text-on-surface-variant/50 italic">
                          {c.summary}
                        </p>
                        <div className="flex gap-2.5">
                          <button 
                            onClick={() => activeWorldId && resolveContradictionInBackend(activeWorldId, c.id)}
                            className="font-label-sm text-xs text-on-surface-variant hover:text-white px-3 py-1.5 transition-colors uppercase tracking-wider"
                          >
                            Ignore
                          </button>
                          <button 
                            onClick={() => handleStartResolve(c.id)}
                            className="font-label-sm text-xs border border-copper-glow text-copper-glow hover:bg-copper-glow hover:text-void-black px-4 py-1.5 rounded transition-all shadow-[0_0_15px_rgba(230,162,126,0.05)] font-semibold uppercase tracking-wider"
                          >
                            Resolve Conflict
                          </button>
                        </div>
                      </footer>
                    )}
                  </motion.article>
                );
              })}
            </AnimatePresence>
          </div>

        </div>
      </main>
    </AppShell>
  );
};
