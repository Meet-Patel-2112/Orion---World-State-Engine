import React, { useState } from 'react';
import { useWorldStore } from '../store/useWorldStore';
import type { Entity } from '../data/mockData';
import { useNavigate } from 'react-router-dom';

interface EntityPanelProps {
  entityId: string;
  onClose: () => void;
}

export const EntityPanel: React.FC<EntityPanelProps> = ({ entityId, onClose }) => {
  const navigate = useNavigate();
  const { 
    entities, 
    addFact, 
    deleteFact, 
    updateEntity, 
    addAlias, 
    removeAlias, 
    activeWorldId, 
    setActiveChapter, 
    setActiveManuscript 
  } = useWorldStore();
  const entity = entities.find((e) => e.id === entityId);

  const [activeTab, setActiveTab] = useState<'details' | 'relations' | 'history'>('details');
  const [factProperty, setFactProperty] = useState('');
  const [factValue, setFactValue] = useState('');
  const [factError, setFactError] = useState<string | null>(null);
  const [isSubmittingFact, setIsSubmittingFact] = useState(false);
  const [isAddingFact, setIsAddingFact] = useState(false);

  const [newAlias, setNewAlias] = useState('');
  const [isAddingAlias, setIsAddingAlias] = useState(false);
  const [aliasError, setAliasError] = useState<string | null>(null);

  const [newTrait, setNewTrait] = useState('');
  const [isAddingTrait, setIsAddingTrait] = useState(false);

  if (!entity) {
    return (
      <div className="p-6 text-center text-on-surface-variant/50">
        Entity not found.
      </div>
    );
  }

  const aliasList = (entity.aliases && entity.aliases.length > 0)
    ? entity.aliases
    : (entity.alias ? [entity.alias] : []);

  const handleAddFact = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!factProperty.trim() || !factValue.trim()) return;
    setFactError(null);
    setIsSubmittingFact(true);
    try {
      await addFact(entity.id, factProperty.trim(), factValue.trim(), 'Manual Entry');
      setFactProperty('');
      setFactValue('');
      setIsAddingFact(false);
    } catch (err: any) {
      setFactError(err?.message || 'Failed to add fact.');
    } finally {
      setIsSubmittingFact(false);
    }
  };

  const handleAddAlias = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newAlias.trim()) return;
    setAliasError(null);
    try {
      await addAlias(entity.id, newAlias.trim());
      setNewAlias('');
      setIsAddingAlias(false);
    } catch (err: any) {
      setAliasError(err?.message || 'Failed to add alias.');
    }
  };

  const handleRemoveAlias = async (aliasToRemove: string) => {
    try {
      await removeAlias(entity.id, aliasToRemove);
    } catch (err: any) {
      console.error('Failed to remove alias:', err);
    }
  };

  const handleAddTrait = () => {
    if (newTrait.trim()) {
      const updatedTraits = [...(entity.traits || []), newTrait.trim()];
      updateEntity(entity.id, { traits: updatedTraits });
      setNewTrait('');
      setIsAddingTrait(false);
    }
  };

  const handleRemoveTrait = (traitIndex: number) => {
    if (entity.traits) {
      const updatedTraits = entity.traits.filter((_, idx) => idx !== traitIndex);
      updateEntity(entity.id, { traits: updatedTraits });
    }
  };

  const navigateToChapter = (chapterId: string) => {
    // We assume manuscript 1 since it's the primary demo, but can locate it
    setActiveManuscript('ms-1');
    setActiveChapter(chapterId);
    navigate(`/worlds/${activeWorldId}/manuscripts/ms-1`);
  };

  // Color mapping based on entity type
  const getTypeColor = (type: Entity['type']) => {
    switch (type) {
      case 'character': return 'text-copper-glow border-copper-glow/20 bg-copper-glow/5';
      case 'location': return 'text-secondary border-secondary/20 bg-secondary/5';
      case 'object': return 'text-tertiary border-tertiary/20 bg-tertiary/5';
      case 'event': return 'text-error border-error/20 bg-error/5';
      default: return 'text-on-surface-variant border-starlight-white/5';
    }
  };

  const getTypeIcon = (type: Entity['type']) => {
    switch (type) {
      case 'character': return 'group';
      case 'location': return 'location_on';
      case 'object': return 'category';
      case 'event': return 'event_note';
      default: return 'help';
    }
  };

  return (
    <div className="flex flex-col h-full bg-surface-container-low/95 backdrop-blur-xl border-l border-starlight-white/10 shadow-2xl relative overflow-hidden">
      {/* Decorative Blur Ambient */}
      <div className="absolute top-0 right-0 w-32 h-32 bg-primary/5 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2 pointer-events-none"></div>

      {/* Header */}
      <div className="p-6 border-b border-starlight-white/5 bg-gradient-to-b from-surface-container-highest/30 to-transparent pt-8">
        <div className="flex justify-between items-start mb-4 relative z-10">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className={`material-symbols-outlined text-sm font-light ${getTypeColor(entity.type).split(' ')[0]}`}>
                {getTypeIcon(entity.type)}
              </span>
              <label className="text-[10px] font-label-sm text-on-surface-variant/60 uppercase tracking-widest">Type:</label>
              <select
                value={entity.type}
                onChange={(e) => updateEntity(entity.id, { type: e.target.value as Entity['type'] })}
                className={`font-label-sm text-[11px] uppercase tracking-wider py-0.5 px-2.5 rounded-full border bg-surface-container cursor-pointer focus:outline-none focus:ring-1 focus:ring-primary ${getTypeColor(entity.type)}`}
              >
                <option value="character" className="bg-void-black text-starlight-white">Character</option>
                <option value="location" className="bg-void-black text-starlight-white">Location</option>
                <option value="object" className="bg-void-black text-starlight-white">Object</option>
                <option value="event" className="bg-void-black text-starlight-white">Event</option>
              </select>
            </div>
            <h2 className="font-headline-md text-headline-md text-starlight-white leading-tight mt-1">{entity.name}</h2>
          </div>
          <button onClick={onClose} className="text-on-surface-variant hover:text-white transition-colors p-1 hover:bg-white/5 rounded-full">
            <span className="material-symbols-outlined font-light">close</span>
          </button>
        </div>

        {/* Panel Tabs */}
        <div className="flex gap-4 border-b border-starlight-white/10 relative z-10 mt-6">
          <button 
            onClick={() => setActiveTab('details')}
            className={`font-label-sm text-label-sm pb-2 px-1 flex items-center gap-1.5 transition-all border-b-2 ${activeTab === 'details' ? 'border-primary text-primary' : 'border-transparent text-on-surface-variant hover:text-primary-fixed-dim'}`}
          >
            <span className="material-symbols-outlined text-sm font-light">subject</span> Details
          </button>
          <button 
            onClick={() => setActiveTab('relations')}
            className={`font-label-sm text-label-sm pb-2 px-1 flex items-center gap-1.5 transition-all border-b-2 ${activeTab === 'relations' ? 'border-primary text-primary' : 'border-transparent text-on-surface-variant hover:text-primary-fixed-dim'}`}
          >
            <span className="material-symbols-outlined text-sm font-light">share</span> Relations
          </button>
          <button 
            onClick={() => setActiveTab('history')}
            className={`font-label-sm text-label-sm pb-2 px-1 flex items-center gap-1.5 transition-all border-b-2 ${activeTab === 'history' ? 'border-primary text-primary' : 'border-transparent text-on-surface-variant hover:text-primary-fixed-dim'}`}
          >
            <span className="material-symbols-outlined text-sm font-light">history</span> Appearances
          </button>
        </div>
      </div>

      {/* Scrollable Content */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        
        {activeTab === 'details' && (
          <>
            {/* Portrait Card */}
            {entity.image && (
              <div className="bg-surface-container-high/50 border border-starlight-white/5 rounded-lg overflow-hidden p-1">
                <div className="w-full h-44 bg-surface-container-lowest rounded relative overflow-hidden group">
                  <img src={entity.image} alt={entity.name} className="w-full h-full object-cover opacity-80 group-hover:opacity-100 transition-opacity duration-500" />
                  <div className="absolute inset-0 bg-gradient-to-t from-void-black/85 via-void-black/20 to-transparent flex items-end p-3">
                    <span className="font-label-sm text-label-sm text-starlight-white/60 text-[10px] uppercase tracking-wider">Visual Reference</span>
                  </div>
                </div>
              </div>
            )}

            {/* Quick Meta: Subtype & Aliases */}
            <div className="space-y-4 bg-surface-container-lowest/40 p-4 rounded-lg border border-starlight-white/5">
              <div>
                <p className="font-label-sm text-label-sm text-on-surface-variant/60 uppercase text-[10px] mb-1">Subtype / Role</p>
                <p className="font-body-md text-body-md text-on-surface text-sm">{entity.subtype || 'Supporting entry'}</p>
              </div>

              {/* Aliases Tag Manager */}
              <div className="pt-2 border-t border-starlight-white/5">
                <div className="flex justify-between items-center mb-2">
                  <p className="font-label-sm text-label-sm text-on-surface-variant/70 uppercase text-[10px] tracking-wider flex items-center gap-1.5">
                    <span className="material-symbols-outlined text-[12px]">sell</span>
                    Aliases
                  </p>
                  {!isAddingAlias && (
                    <button
                      onClick={() => setIsAddingAlias(true)}
                      className="font-label-sm text-[10px] text-primary hover:text-white flex items-center gap-1 uppercase tracking-wider transition-colors"
                    >
                      <span className="material-symbols-outlined text-[11px]">add</span> Add Alias
                    </button>
                  )}
                </div>

                <div className="flex flex-wrap gap-1.5">
                  {aliasList.length === 0 && !isAddingAlias && (
                    <span className="text-xs text-on-surface-variant/40 italic">No aliases recorded.</span>
                  )}
                  {aliasList.map((a, idx) => (
                    <span
                      key={idx}
                      className="px-2.5 py-0.5 bg-surface-container text-on-surface-variant font-label-sm text-[11px] rounded-full border border-starlight-white/5 flex items-center gap-1.5 group/alias hover:border-primary/30"
                    >
                      "{a}"
                      <button
                        onClick={() => handleRemoveAlias(a)}
                        className="opacity-40 group-hover/alias:opacity-100 hover:text-error transition-opacity"
                        title={`Remove alias "${a}"`}
                      >
                        <span className="material-symbols-outlined text-[10px]">close</span>
                      </button>
                    </span>
                  ))}
                  {isAddingAlias && (
                    <form onSubmit={handleAddAlias} className="flex items-center gap-1 mt-1">
                      <input
                        type="text"
                        value={newAlias}
                        onChange={(e) => setNewAlias(e.target.value)}
                        placeholder="New alias..."
                        autoFocus
                        className="bg-surface-container-high border border-outline-variant/30 text-xs rounded px-2 py-0.5 text-starlight-white focus:outline-none focus:ring-1 focus:ring-primary w-28"
                      />
                      <button type="submit" className="text-primary hover:text-white">
                        <span className="material-symbols-outlined text-sm">check</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setIsAddingAlias(false);
                          setAliasError(null);
                        }}
                        className="text-on-surface-variant"
                      >
                        <span className="material-symbols-outlined text-sm">close</span>
                      </button>
                    </form>
                  )}
                </div>
                {aliasError && (
                  <p className="text-[11px] text-error mt-1.5">{aliasError}</p>
                )}
              </div>
            </div>

            {/* Description */}
            <div>
              <p className="font-label-sm text-label-sm text-on-surface-variant/60 uppercase text-[10px] mb-2">Synopsis</p>
              <p className="font-body-md text-body-md text-on-surface-variant text-sm leading-relaxed bg-surface-container-lowest/30 p-3 rounded border border-starlight-white/5">
                {entity.description}
              </p>
            </div>

            {/* Traits */}
            {entity.type === 'character' && (
              <div className="space-y-3">
                <p className="font-label-sm text-label-sm text-copper-glow uppercase tracking-wider flex items-center gap-2">
                  <span className="material-symbols-outlined text-sm font-light">psychology</span>
                  Core Traits
                </p>
                <div className="flex flex-wrap gap-2">
                  {entity.traits?.map((trait, idx) => (
                    <span 
                      key={idx} 
                      className="px-2.5 py-1 bg-surface-container text-on-surface-variant font-label-sm text-[11px] rounded border border-starlight-white/5 flex items-center gap-1.5 group/trait"
                    >
                      {trait}
                      <button 
                        onClick={() => handleRemoveTrait(idx)}
                        className="opacity-0 group-hover/trait:opacity-100 hover:text-error transition-opacity"
                        title="Remove trait"
                      >
                        <span className="material-symbols-outlined text-[10px]">close</span>
                      </button>
                    </span>
                  ))}
                  {isAddingTrait ? (
                    <div className="flex items-center gap-1">
                      <input 
                        type="text" 
                        value={newTrait}
                        onChange={(e) => setNewTrait(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && handleAddTrait()}
                        className="bg-surface-container-high border border-outline-variant/30 text-xs rounded px-2 py-0.5 text-starlight-white focus:outline-none focus:ring-1 focus:ring-primary w-24"
                        placeholder="New trait..."
                        autoFocus
                      />
                      <button onClick={handleAddTrait} className="text-primary hover:text-white">
                        <span className="material-symbols-outlined text-sm">check</span>
                      </button>
                      <button onClick={() => setIsAddingTrait(false)} className="text-on-surface-variant">
                        <span className="material-symbols-outlined text-sm">close</span>
                      </button>
                    </div>
                  ) : (
                    <button 
                      onClick={() => setIsAddingTrait(true)}
                      className="px-2.5 py-1 bg-transparent text-primary/60 hover:text-primary font-label-sm text-[11px] rounded border border-dashed border-primary/30 hover:border-primary/60 transition-colors flex items-center gap-1"
                    >
                      <span className="material-symbols-outlined text-[10px]">add</span> Add
                    </button>
                  )}
                </div>
              </div>
            )}

            {/* Facts Ledger */}
            <div className="space-y-3 pt-2">
              <div className="flex justify-between items-center border-b border-starlight-white/5 pb-2">
                <p className="font-label-sm text-label-sm text-copper-glow uppercase tracking-wider flex items-center gap-2">
                  <span className="material-symbols-outlined text-sm font-light">format_list_bulleted</span>
                  Known Facts
                </p>
                <button 
                  onClick={() => setIsAddingFact(!isAddingFact)}
                  className="font-label-sm text-[10px] text-primary/80 hover:text-primary flex items-center gap-1 uppercase tracking-wider border border-primary/20 hover:border-primary/50 px-2 py-0.5 rounded transition-all"
                >
                  <span className="material-symbols-outlined text-[12px]">{isAddingFact ? 'close' : 'add'}</span> 
                  {isAddingFact ? 'Cancel' : 'Add Fact'}
                </button>
              </div>

              {isAddingFact && (
                <form onSubmit={handleAddFact} className="flex flex-col gap-2.5 p-3 bg-surface-container rounded border border-outline-variant/30 animate-fade-in-up">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    <div>
                      <label className="block text-[10px] font-label-sm text-on-surface-variant/70 uppercase mb-1">Property Name</label>
                      <input 
                        type="text"
                        value={factProperty}
                        onChange={(e) => setFactProperty(e.target.value)}
                        placeholder="e.g. status, title, weapon"
                        className="w-full bg-void-black text-xs text-starlight-white placeholder:text-on-surface-variant/40 rounded border border-starlight-white/10 p-2 focus:border-primary focus:ring-0 focus:outline-none"
                        required
                      />
                    </div>
                    <div>
                      <label className="block text-[10px] font-label-sm text-on-surface-variant/70 uppercase mb-1">Value</label>
                      <input 
                        type="text"
                        value={factValue}
                        onChange={(e) => setFactValue(e.target.value)}
                        placeholder="e.g. deceased, High Commander"
                        className="w-full bg-void-black text-xs text-starlight-white placeholder:text-on-surface-variant/40 rounded border border-starlight-white/10 p-2 focus:border-primary focus:ring-0 focus:outline-none"
                        required
                      />
                    </div>
                  </div>
                  {factError && (
                    <p className="text-[11px] text-error">{factError}</p>
                  )}
                  <div className="flex gap-2">
                    <button 
                      type="submit" 
                      disabled={isSubmittingFact}
                      className="flex-1 py-1.5 bg-primary text-void-black font-label-sm text-xs rounded hover:bg-copper-glow transition-all uppercase tracking-wider font-semibold disabled:opacity-50"
                    >
                      {isSubmittingFact ? 'Recording...' : 'Submit Fact'}
                    </button>
                    <button 
                      type="button" 
                      onClick={() => {
                        setIsAddingFact(false);
                        setFactError(null);
                      }}
                      className="px-3 py-1.5 border border-starlight-white/10 text-on-surface-variant font-label-sm text-xs rounded hover:text-white uppercase tracking-wider"
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              )}

              <div className="space-y-3">
                {entity.facts.length === 0 ? (
                  <p className="text-xs text-on-surface-variant/40 italic">No facts recorded yet.</p>
                ) : (
                  entity.facts.map((fact) => (
                    <div 
                      key={fact.id} 
                      className="group relative pl-3.5 py-1.5 border-l border-outline-variant/35 hover:border-primary/50 transition-colors flex justify-between items-start"
                    >
                      <div className="absolute -left-[5px] top-[14px] w-2.5 h-2.5 rounded-full bg-outline-variant/80 group-hover:bg-primary transition-all"></div>
                      <div className="flex-1 pr-2">
                        <p className="font-body-md text-xs text-on-surface leading-relaxed">{fact.text}</p>
                        <div className="flex items-center gap-2 mt-1">
                          <span className={`text-[9px] uppercase tracking-wider font-label-sm px-1.5 py-0.2 rounded ${fact.type === 'extracted' ? 'bg-primary/10 text-primary border border-primary/20' : 'bg-surface-container text-on-surface-variant/60 border border-starlight-white/5'}`}>
                            {fact.type}
                          </span>
                          <span className="text-[10px] text-on-surface-variant/40">{fact.source}</span>
                        </div>
                      </div>
                      <button 
                        onClick={() => deleteFact(entity.id, fact.id)}
                        className="opacity-0 group-hover:opacity-100 text-on-surface-variant/40 hover:text-error transition-all p-1"
                        title="Delete fact"
                      >
                        <span className="material-symbols-outlined text-sm font-light">delete</span>
                      </button>
                    </div>
                  ))
                )}
              </div>
            </div>
          </>
        )}

        {activeTab === 'relations' && (
          <div className="space-y-4">
            <p className="font-label-sm text-label-sm text-copper-glow uppercase tracking-wider flex items-center gap-2 border-b border-starlight-white/5 pb-2">
              <span className="material-symbols-outlined text-sm font-light">hub</span>
              Web of Influence
            </p>
            {entity.relationships.length === 0 ? (
              <p className="text-xs text-on-surface-variant/40 italic">No active relationships mapped in ledger.</p>
            ) : (
              <div className="space-y-2">
                {entity.relationships.map((rel, idx) => (
                  <div 
                    key={idx} 
                    className="flex items-center justify-between p-3 rounded bg-surface-container-lowest/80 border border-starlight-white/5 hover:border-primary/30 transition-colors cursor-pointer group"
                    onClick={() => {
                      // Navigate to target if exists
                      const targetExists = entities.some(e => e.id === rel.targetId);
                      if (targetExists) {
                        useWorldStore.getState().setActiveEntity(rel.targetId);
                      }
                    }}
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <div className={`w-8 h-8 rounded-full flex items-center justify-center font-headline-md text-sm shrink-0 border ${
                        rel.targetType === 'character' ? 'border-primary/20 text-primary' : 
                        rel.targetType === 'location' ? 'border-secondary/20 text-secondary' : 'border-tertiary/20 text-tertiary'
                      }`}>
                        {rel.targetName[0]}
                      </div>
                      <div className="min-w-0">
                        <p className="font-body-md text-xs text-starlight-white group-hover:text-primary transition-colors truncate">{rel.targetName}</p>
                        <p className={`font-label-sm text-[10px] uppercase tracking-wider truncate ${rel.isNegative ? 'text-error' : 'text-on-surface-variant'}`}>{rel.relation}</p>
                      </div>
                    </div>
                    <span className="material-symbols-outlined text-sm text-on-surface-variant/30 group-hover:text-primary/70 group-hover:translate-x-1 transition-all">chevron_right</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {activeTab === 'history' && (
          <div className="space-y-4">
            <p className="font-label-sm text-label-sm text-copper-glow uppercase tracking-wider flex items-center gap-2 border-b border-starlight-white/5 pb-2">
              <span className="material-symbols-outlined text-sm font-light">auto_stories</span>
              Chapter Appearances
            </p>
            {entity.appearances.length === 0 ? (
              <p className="text-xs text-on-surface-variant/40 italic">This entity has no extracted chapter appearances.</p>
            ) : (
              <div className="flex flex-wrap gap-2.5">
                {entity.appearances.map((chapId) => {
                  // Find chapter details
                  const chMap: { [key: string]: string } = {
                    ch1: 'Ch. 1 - The Awakening',
                    ch2: 'Ch. 2 - Descent into the Archives',
                    ch3: 'Ch. 3 - Echoes of the Precursors',
                    ch4: 'Ch. 4 - The Descent',
                  };
                  return (
                    <button 
                      key={chapId}
                      onClick={() => navigateToChapter(chapId)}
                      className="px-3 py-2 rounded bg-surface-container-lowest hover:bg-surface-container border border-starlight-white/5 hover:border-primary/40 text-xs text-on-surface-variant hover:text-primary transition-all flex items-center gap-2"
                    >
                      <span className="material-symbols-outlined text-xs text-primary/70 font-light">bookmark_border</span>
                      {chMap[chapId] || chapId.toUpperCase()}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>
      
      {/* Bottom info banner */}
      <div className="p-4 border-t border-starlight-white/5 bg-void-black/80 flex items-center justify-between text-[11px] font-label-sm text-on-surface-variant/40 uppercase tracking-widest">
        <span>ID: {entity.id}</span>
        <span>Engine Ledger</span>
      </div>
    </div>
  );
};
