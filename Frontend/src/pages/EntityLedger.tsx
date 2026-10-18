import React, { useState, useEffect } from 'react';
import { AppShell } from '../components/AppShell';
import { useWorldStore } from '../store/useWorldStore';
import type { Entity } from '../data/mockData';

export const EntityLedger: React.FC = () => {
  const { 
    entities, 
    activeWorldId, 
    fetchEntitiesForWorld, 
    setActiveEntity, 
    addEntity,
    mergeEntities,
    bulkDeleteEntities 
  } = useWorldStore();

  useEffect(() => {
    if (activeWorldId) {
      fetchEntitiesForWorld(activeWorldId);
    }
  }, [activeWorldId, fetchEntitiesForWorld]);
  
  const [activeTab, setActiveTab] = useState<'all' | 'character' | 'location' | 'object' | 'event'>('all');
  const [searchQuery, setSearchQuery] = useState('');
  
  // Selection mode states
  const [isSelectMode, setIsSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  // Merge Modal states
  const [isMergeModalOpen, setIsMergeModalOpen] = useState(false);
  const [survivorId, setSurvivorId] = useState<string>('');
  const [isMerging, setIsMerging] = useState(false);
  const [mergeError, setMergeError] = useState<string | null>(null);

  // Bulk Delete Modal states
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // Forge Entity Form Modal states
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [modalType, setModalType] = useState<'character' | 'location' | 'object' | 'event'>('character');
  const [entityName, setEntityName] = useState('');
  const [entitySubtype, setEntitySubtype] = useState('');
  const [entityDesc, setEntityDesc] = useState('');

  const filteredEntities = entities.filter((e) => {
    const matchesTab = activeTab === 'all' || e.type === activeTab;
    const matchesSearch = e.name.toLowerCase().includes(searchQuery.toLowerCase()) || 
                          e.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
                          e.subtype?.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesTab && matchesSearch;
  });

  const toggleSelect = (id: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    setSelectedIds(prev => 
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    );
  };

  const handleSelectAll = () => {
    if (selectedIds.length === filteredEntities.length) {
      setSelectedIds([]);
    } else {
      setSelectedIds(filteredEntities.map(e => e.id));
    }
  };

  const handleOpenMergeModal = () => {
    if (selectedIds.length !== 2) return;
    setSurvivorId(selectedIds[0]);
    setMergeError(null);
    setIsMergeModalOpen(true);
  };

  const handleExecuteMerge = async () => {
    if (selectedIds.length !== 2) return;
    const sourceId = selectedIds.find(id => id !== survivorId);
    if (!sourceId || !survivorId) return;

    setIsMerging(true);
    setMergeError(null);
    try {
      await mergeEntities(sourceId, survivorId);
      setIsMergeModalOpen(false);
      setSelectedIds([]);
      setIsSelectMode(false);
    } catch (err: any) {
      setMergeError(err?.message || 'Failed to merge entities.');
    } finally {
      setIsMerging(false);
    }
  };

  const handleOpenDeleteModal = () => {
    if (selectedIds.length === 0) return;
    setDeleteError(null);
    setIsDeleteModalOpen(true);
  };

  const handleExecuteBulkDelete = async () => {
    if (selectedIds.length === 0) return;
    setIsDeleting(true);
    setDeleteError(null);
    try {
      await bulkDeleteEntities(selectedIds);
      setIsDeleteModalOpen(false);
      setSelectedIds([]);
      setIsSelectMode(false);
    } catch (err: any) {
      setDeleteError(err?.message || 'Failed to delete entities.');
    } finally {
      setIsDeleting(false);
    }
  };

  const handleOpenModal = (type: typeof modalType) => {
    setModalType(type);
    setEntityName('');
    setEntitySubtype('');
    setEntityDesc('');
    setIsModalOpen(true);
  };

  const handleForgeEntity = (e: React.FormEvent) => {
    e.preventDefault();
    if (entityName.trim() && entityDesc.trim()) {
      addEntity({
        id: `entity-${Date.now()}`,
        name: entityName.trim(),
        type: modalType,
        subtype: entitySubtype.trim() || undefined,
        description: entityDesc.trim()
      });
      setIsModalOpen(false);
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

  const getTypeColor = (type: Entity['type']) => {
    switch (type) {
      case 'character': return 'text-copper-glow border-copper-glow/20';
      case 'location': return 'text-secondary border-secondary/20';
      case 'object': return 'text-tertiary border-tertiary/20';
      case 'event': return 'text-error border-error/20';
      default: return 'text-on-surface-variant border-starlight-white/5';
    }
  };

  return (
    <AppShell>
      {/* Background gradients */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_bottom_left,_var(--tw-gradient-stops))] from-surface-container-high/10 via-void-black to-void-black -z-10 pointer-events-none"></div>

      <main className="flex-1 min-h-screen overflow-y-auto px-8 md:px-12 py-10">
        <div className="max-w-7xl mx-auto flex flex-col gap-8 animate-fade-in-up">
          
          {/* Header */}
          <div className="flex flex-col md:flex-row justify-between items-start md:items-end gap-6 border-b border-starlight-white/5 pb-6">
            <div>
              <span className="font-label-sm text-[10px] text-primary uppercase tracking-[0.2em] mb-1.5 block">World Archive</span>
              <h2 className="font-headline-lg text-starlight-white mb-2">World Ledger</h2>
              <p className="font-body-lg text-body-lg text-on-surface-variant/80 max-w-2xl">
                Browse, search, and edit the characters, landmarks, and key objects of your universe.
              </p>
            </div>
            
            {/* Quick Forge Menu & Selection Mode Toggle */}
            <div className="flex flex-wrap items-center gap-2.5 shrink-0">
              <button 
                onClick={() => {
                  setIsSelectMode(!isSelectMode);
                  setSelectedIds([]);
                }}
                className={`flex items-center gap-1.5 font-label-sm text-[11px] px-3.5 py-2 rounded uppercase tracking-wider font-semibold border transition-all ${
                  isSelectMode 
                    ? 'bg-primary text-void-black border-primary shadow-[0_0_12px_rgba(230,162,126,0.3)]' 
                    : 'text-on-surface-variant border-starlight-white/10 hover:border-primary/40 hover:text-white'
                }`}
              >
                <span className="material-symbols-outlined text-sm font-light">
                  {isSelectMode ? 'check_box' : 'checklist'}
                </span>
                {isSelectMode ? 'Exit Selection' : 'Select / Merge'}
              </button>
              <button 
                onClick={() => handleOpenModal('character')}
                className="flex items-center gap-1.5 font-label-sm text-[11px] text-primary border border-primary/20 hover:border-primary px-4 py-2 rounded uppercase tracking-wider font-semibold hover:bg-primary/5 transition-all"
              >
                <span className="material-symbols-outlined text-sm font-light">group</span> Character
              </button>
              <button 
                onClick={() => handleOpenModal('location')}
                className="flex items-center gap-1.5 font-label-sm text-[11px] text-secondary border border-secondary/20 hover:border-secondary px-4 py-2 rounded uppercase tracking-wider font-semibold hover:bg-secondary/5 transition-all"
              >
                <span className="material-symbols-outlined text-sm font-light">location_on</span> Location
              </button>
            </div>
          </div>

          {/* Search and Filters Bar */}
          <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4">
            
            {/* Tabs */}
            <div className="flex bg-surface-container-lowest/80 border border-starlight-white/10 p-1 rounded-lg">
              {([
                { id: 'all', label: 'All Entries', icon: 'list' },
                { id: 'character', label: 'Characters', icon: 'group' },
                { id: 'location', label: 'Locations', icon: 'location_on' },
                { id: 'object', label: 'Objects', icon: 'category' }
              ] as const).map(tab => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-2 px-4 py-1.5 rounded font-label-sm text-xs uppercase tracking-wider transition-all ${
                    activeTab === tab.id 
                      ? 'bg-primary text-void-black font-semibold' 
                      : 'text-on-surface-variant hover:text-white'
                  }`}
                >
                  <span className="material-symbols-outlined text-[15px] font-light">{tab.icon}</span>
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Search Input */}
            <div className="relative group min-w-[260px]">
              <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant/40 text-lg group-focus-within:text-primary transition-colors font-light">search</span>
              <input 
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search ledger entries..."
                className="w-full bg-surface-container-lowest border border-starlight-white/10 rounded px-10 py-2.5 font-body-md text-xs text-on-surface placeholder:text-on-surface-variant/30 focus:border-primary focus:ring-0 focus:outline-none"
              />
            </div>

          </div>

          {/* Batch Actions Bar (shown when in Selection Mode) */}
          {isSelectMode && (
            <div className="flex flex-wrap items-center justify-between gap-4 bg-surface-container-high/60 border border-primary/20 p-3.5 rounded-xl backdrop-blur-md animate-fade-in-up">
              <div className="flex items-center gap-3">
                <button 
                  onClick={handleSelectAll}
                  className="flex items-center gap-1.5 text-xs text-on-surface-variant hover:text-white font-label-sm uppercase tracking-wider"
                >
                  <span className="material-symbols-outlined text-base text-primary">
                    {selectedIds.length === filteredEntities.length && filteredEntities.length > 0
                      ? 'check_box' 
                      : selectedIds.length > 0 
                        ? 'indeterminate_check_box' 
                        : 'check_box_outline_blank'}
                  </span>
                  {selectedIds.length === filteredEntities.length ? 'Deselect All' : 'Select All'}
                </button>
                <span className="h-4 w-px bg-starlight-white/10" />
                <span className="text-xs text-starlight-white font-semibold">
                  {selectedIds.length} {selectedIds.length === 1 ? 'entity' : 'entities'} selected
                </span>
                {selectedIds.length === 2 && (
                  <span className="text-[11px] text-primary bg-primary/10 border border-primary/20 px-2 py-0.5 rounded-full">
                    Ready to merge
                  </span>
                )}
              </div>

              <div className="flex items-center gap-2.5">
                <button
                  onClick={handleOpenMergeModal}
                  disabled={selectedIds.length !== 2}
                  className="flex items-center gap-1.5 font-label-sm text-xs px-3.5 py-1.5 rounded uppercase tracking-wider font-semibold border transition-all disabled:opacity-30 disabled:cursor-not-allowed bg-primary/10 border-primary/40 text-primary hover:bg-primary hover:text-void-black"
                  title={selectedIds.length !== 2 ? 'Select exactly 2 entities to merge' : 'Merge the 2 selected entities'}
                >
                  <span className="material-symbols-outlined text-sm">merge</span>
                  Merge Entities (2)
                </button>
                <button
                  onClick={handleOpenDeleteModal}
                  disabled={selectedIds.length === 0}
                  className="flex items-center gap-1.5 font-label-sm text-xs px-3.5 py-1.5 rounded uppercase tracking-wider font-semibold border transition-all disabled:opacity-30 disabled:cursor-not-allowed bg-error/10 border-error/30 text-error hover:bg-error hover:text-void-black"
                >
                  <span className="material-symbols-outlined text-sm">delete</span>
                  Bulk Delete ({selectedIds.length})
                </button>
                <button
                  onClick={() => {
                    setIsSelectMode(false);
                    setSelectedIds([]);
                  }}
                  className="text-xs text-on-surface-variant hover:text-white px-2 py-1 uppercase tracking-wider"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {/* Grid List */}
          {filteredEntities.length === 0 ? (
            <div className="py-20 text-center text-sm text-on-surface-variant/40 italic bg-surface-container-low/20 rounded-xl border border-dashed border-starlight-white/5">
              No chronicle ledger entries match your filter.
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 pb-24">
              {filteredEntities.map((e) => {
                const isSelected = selectedIds.includes(e.id);

                return (
                  <article 
                    key={e.id}
                    onClick={() => {
                      if (isSelectMode) {
                        toggleSelect(e.id);
                      } else {
                        setActiveEntity(e.id);
                      }
                    }}
                    className={`bg-surface-container-low/40 border rounded-xl p-5 hover-glow transition-all duration-300 flex flex-col gap-4 cursor-pointer relative overflow-hidden group ${
                      isSelected 
                        ? 'border-primary ring-1 ring-primary bg-primary/5' 
                        : 'border-starlight-white/5 hover:border-primary/30'
                    }`}
                  >
                    {/* Checkbox badge when in selection mode */}
                    {isSelectMode && (
                      <div 
                        onClick={(evt) => toggleSelect(e.id, evt)}
                        className="absolute top-4 right-4 z-20 cursor-pointer text-primary"
                        title={isSelected ? 'Deselect entity' : 'Select entity'}
                      >
                        <span className="material-symbols-outlined text-xl">
                          {isSelected ? 'check_box' : 'check_box_outline_blank'}
                        </span>
                      </div>
                    )}

                    {/* Subtle hover glow accent */}
                    <div className="absolute inset-0 bg-gradient-to-br from-primary/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none"></div>

                    <header className="flex justify-between items-start border-b border-starlight-white/5 pb-3 pr-6">
                      <div>
                        <span className={`font-label-sm text-[9px] uppercase tracking-widest border px-2 py-0.5 rounded-full flex items-center gap-1.5 ${getTypeColor(e.type)}`}>
                          <span className="material-symbols-outlined text-[12px] font-light">{getTypeIcon(e.type)}</span>
                          {e.type}
                        </span>
                        <h3 className="font-headline-md text-starlight-white mt-2 group-hover:text-primary transition-colors text-base font-semibold">
                          {e.name}
                        </h3>
                      </div>
                      {e.alias && !isSelectMode && (
                        <span className="font-body-md text-xs text-on-surface-variant/50 italic">
                          "{e.alias}"
                        </span>
                      )}
                    </header>

                    <p className="font-body-md text-xs text-on-surface-variant/80 leading-relaxed flex-1 line-clamp-3">
                      {e.description}
                    </p>

                    {/* Footer details */}
                    <footer className="mt-4 pt-3 border-t border-starlight-white/5 flex items-center justify-between text-[10px] font-label-sm text-on-surface-variant/40 uppercase tracking-widest">
                      <span>{e.subtype || 'Ledger entry'}</span>
                      <span>{e.facts.length} {e.facts.length === 1 ? 'Fact' : 'Facts'}</span>
                    </footer>
                  </article>
                );
              })}
            </div>
          )}

        </div>
      </main>

      {/* Merge Confirmation Modal */}
      {isMergeModalOpen && selectedIds.length === 2 && (
        <div className="fixed inset-0 bg-void-black/85 backdrop-blur-md z-50 flex items-center justify-center p-4">
          <div className="bg-surface-container border border-primary/20 rounded-2xl max-w-2xl w-full p-6 shadow-2xl relative animate-fade-in-up">
            <button 
              onClick={() => {
                setIsMergeModalOpen(false);
                setMergeError(null);
              }}
              className="absolute top-4 right-4 text-on-surface-variant hover:text-white p-1 rounded-full hover:bg-white/5"
            >
              <span className="material-symbols-outlined font-light">close</span>
            </button>

            <div className="flex items-center gap-2 mb-2">
              <span className="material-symbols-outlined text-primary text-xl">merge</span>
              <h2 className="font-headline-md text-starlight-white text-lg font-bold">
                Merge Entities
              </h2>
            </div>
            <p className="text-xs text-on-surface-variant/80 mb-6">
              Select which entity will be the <span className="text-emerald-400 font-semibold">Surviving Target</span>. The other entity will be merged into it and permanently deleted.
            </p>

            {mergeError && (
              <div className="mb-4 p-3 rounded-lg bg-error/10 border border-error/30 text-error text-xs flex items-center gap-2">
                <span className="material-symbols-outlined text-sm">error</span>
                {mergeError}
              </div>
            )}

            {/* Side-by-side selection */}
            {(() => {
              const entityA = entities.find(e => e.id === selectedIds[0]);
              const entityB = entities.find(e => e.id === selectedIds[1]);
              if (!entityA || !entityB) return null;

              const survivor = survivorId === entityB.id ? entityB : entityA;
              const source = survivor.id === entityA.id ? entityB : entityA;

              return (
                <div className="space-y-4">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    {/* Entity A */}
                    <div 
                      onClick={() => setSurvivorId(entityA.id)}
                      className={`p-4 rounded-xl border cursor-pointer transition-all ${
                        survivor.id === entityA.id 
                          ? 'border-emerald-400 bg-emerald-500/10 ring-1 ring-emerald-400/50' 
                          : 'border-error/40 bg-error/5 hover:border-error/60'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <span className={`text-[10px] font-label-sm uppercase tracking-wider px-2 py-0.5 rounded-full font-bold ${
                          survivor.id === entityA.id 
                            ? 'bg-emerald-500/20 text-emerald-300' 
                            : 'bg-error/20 text-error'
                        }`}>
                          {survivor.id === entityA.id ? 'Surviving Target' : 'Source (Will Delete)'}
                        </span>
                        <span className="material-symbols-outlined text-base">
                          {survivor.id === entityA.id ? 'check_circle' : 'delete'}
                        </span>
                      </div>
                      <h3 className="font-semibold text-starlight-white text-sm mb-1">{entityA.name}</h3>
                      <p className="text-[11px] text-on-surface-variant/70 line-clamp-2">{entityA.description}</p>
                      <div className="mt-3 pt-2 border-t border-starlight-white/5 text-[10px] text-on-surface-variant/50">
                        {entityA.facts.length} facts • Type: {entityA.type}
                      </div>
                    </div>

                    {/* Entity B */}
                    <div 
                      onClick={() => setSurvivorId(entityB.id)}
                      className={`p-4 rounded-xl border cursor-pointer transition-all ${
                        survivor.id === entityB.id 
                          ? 'border-emerald-400 bg-emerald-500/10 ring-1 ring-emerald-400/50' 
                          : 'border-error/40 bg-error/5 hover:border-error/60'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <span className={`text-[10px] font-label-sm uppercase tracking-wider px-2 py-0.5 rounded-full font-bold ${
                          survivor.id === entityB.id 
                            ? 'bg-emerald-500/20 text-emerald-300' 
                            : 'bg-error/20 text-error'
                        }`}>
                          {survivor.id === entityB.id ? 'Surviving Target' : 'Source (Will Delete)'}
                        </span>
                        <span className="material-symbols-outlined text-base">
                          {survivor.id === entityB.id ? 'check_circle' : 'delete'}
                        </span>
                      </div>
                      <h3 className="font-semibold text-starlight-white text-sm mb-1">{entityB.name}</h3>
                      <p className="text-[11px] text-on-surface-variant/70 line-clamp-2">{entityB.description}</p>
                      <div className="mt-3 pt-2 border-t border-starlight-white/5 text-[10px] text-on-surface-variant/50">
                        {entityB.facts.length} facts • Type: {entityB.type}
                      </div>
                    </div>
                  </div>

                  {/* Summary of what merge rules execute */}
                  <div className="bg-void-black/60 p-3.5 rounded-lg border border-starlight-white/5 text-xs text-on-surface-variant/80 space-y-1.5">
                    <p className="font-semibold text-starlight-white text-[11px] uppercase tracking-wider flex items-center gap-1.5 text-primary">
                      <span className="material-symbols-outlined text-sm">info</span>
                      Merge Transaction Details
                    </p>
                    <ul className="list-disc pl-4 space-y-1 text-[11px] text-on-surface-variant/70">
                      <li>"<span className="text-starlight-white font-medium">{source.name}</span>" will be added as an alias to "<span className="text-emerald-300 font-medium">{survivor.name}</span>".</li>
                      <li>All mentions, facts, relationships, and event appearances will fold into the survivor.</li>
                      <li>Any self-loops and duplicate participations are automatically pruned.</li>
                    </ul>
                  </div>

                  <div className="flex justify-end gap-3 pt-2">
                    <button
                      type="button"
                      onClick={() => setIsMergeModalOpen(false)}
                      className="px-4 py-2 border border-starlight-white/10 rounded text-xs text-on-surface-variant hover:text-white uppercase tracking-wider"
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      disabled={isMerging}
                      onClick={handleExecuteMerge}
                      className="px-5 py-2 bg-primary hover:bg-copper-glow text-void-black font-semibold text-xs rounded uppercase tracking-wider transition-all disabled:opacity-50"
                    >
                      {isMerging ? 'Merging...' : 'Confirm & Execute Merge'}
                    </button>
                  </div>
                </div>
              );
            })()}
          </div>
        </div>
      )}

      {/* Bulk Delete Modal */}
      {isDeleteModalOpen && selectedIds.length > 0 && (
        <div className="fixed inset-0 bg-void-black/85 backdrop-blur-md z-50 flex items-center justify-center p-4">
          <div className="bg-surface-container border border-error/30 rounded-2xl max-w-md w-full p-6 shadow-2xl relative animate-fade-in-up">
            <button 
              onClick={() => {
                setIsDeleteModalOpen(false);
                setDeleteError(null);
              }}
              className="absolute top-4 right-4 text-on-surface-variant hover:text-white p-1 rounded-full hover:bg-white/5"
            >
              <span className="material-symbols-outlined font-light">close</span>
            </button>

            <div className="flex items-center gap-2 mb-2 text-error">
              <span className="material-symbols-outlined text-xl">warning</span>
              <h2 className="font-headline-md text-starlight-white text-lg font-bold">
                Delete {selectedIds.length} {selectedIds.length === 1 ? 'Entity' : 'Entities'}?
              </h2>
            </div>
            <p className="text-xs text-on-surface-variant/80 mb-4">
              This action cannot be undone. All selected entities and their facts, aliases, mentions, and participations will be removed.
            </p>

            {deleteError && (
              <div className="mb-4 p-3 rounded-lg bg-error/10 border border-error/30 text-error text-xs flex items-center gap-2">
                <span className="material-symbols-outlined text-sm">error</span>
                {deleteError}
              </div>
            )}

            <div className="max-h-40 overflow-y-auto bg-void-black/50 rounded-lg p-3 border border-starlight-white/5 mb-6 divide-y divide-starlight-white/5">
              {selectedIds.map(id => {
                const ent = entities.find(e => e.id === id);
                return (
                  <div key={id} className="py-1.5 flex items-center justify-between text-xs">
                    <span className="text-starlight-white font-medium">{ent?.name || id}</span>
                    <span className="text-[10px] uppercase text-on-surface-variant/50">{ent?.type}</span>
                  </div>
                );
              })}
            </div>

            <div className="flex justify-end gap-3">
              <button
                type="button"
                onClick={() => setIsDeleteModalOpen(false)}
                className="px-4 py-2 border border-starlight-white/10 rounded text-xs text-on-surface-variant hover:text-white uppercase tracking-wider"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={isDeleting}
                onClick={handleExecuteBulkDelete}
                className="px-5 py-2 bg-error hover:bg-red-400 text-void-black font-semibold text-xs rounded uppercase tracking-wider transition-all disabled:opacity-50"
              >
                {isDeleting ? 'Deleting...' : 'Delete Selected'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Creation Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 bg-void-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-gutter">
          <div className="bg-surface-container-low border border-starlight-white/10 rounded-xl max-w-lg w-full p-6 shadow-2xl relative animate-fade-in-up">
            <button 
              onClick={() => setIsModalOpen(false)}
              className="absolute top-4 right-4 text-on-surface-variant hover:text-white p-1 rounded-full hover:bg-white/5"
            >
              <span className="material-symbols-outlined font-light">close</span>
            </button>
            
            <h2 className="font-headline-md text-headline-md text-primary mb-2 capitalize">
              Forge New {modalType}
            </h2>
            <p className="text-xs text-on-surface-variant/60 mb-6">
              Create a new entity in the ledger. It will instantly link with manuscripts, timelines, and graphs.
            </p>

            <form onSubmit={handleForgeEntity} className="space-y-4">
              <div>
                <label className="block text-xs font-label-sm text-on-surface-variant/80 uppercase mb-2">Name</label>
                <input 
                  type="text"
                  required
                  value={entityName}
                  onChange={(e) => setEntityName(e.target.value)}
                  placeholder={`e.g. ${modalType === 'character' ? 'Valerius Thorne' : modalType === 'location' ? 'The Iron Valley' : 'Aetheric compass'}`}
                  className="w-full bg-void-black text-sm text-starlight-white border border-starlight-white/10 rounded p-2.5 focus:border-primary focus:ring-0 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-label-sm text-on-surface-variant/80 uppercase mb-2">Subtype / Role</label>
                <input 
                  type="text"
                  value={entitySubtype}
                  onChange={(e) => setEntitySubtype(e.target.value)}
                  placeholder={`e.g. ${modalType === 'character' ? 'Antagonist / Trader' : modalType === 'location' ? 'Syndicate Outpost' : 'Key Lore Item'}`}
                  className="w-full bg-void-black text-sm text-starlight-white border border-starlight-white/10 rounded p-2.5 focus:border-primary focus:ring-0 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-label-sm text-on-surface-variant/80 uppercase mb-2">Description / Synopsis</label>
                <textarea 
                  required
                  value={entityDesc}
                  onChange={(e) => setEntityDesc(e.target.value)}
                  placeholder="Enter a brief history or description..."
                  rows={3}
                  className="w-full bg-void-black text-sm text-starlight-white border border-starlight-white/10 rounded p-2.5 focus:border-primary focus:ring-0 focus:outline-none"
                />
              </div>

              <div className="flex justify-end gap-3 pt-4 border-t border-starlight-white/5">
                <button 
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="px-4 py-2 text-xs font-label-sm uppercase tracking-widest text-on-surface-variant hover:text-white"
                >
                  Cancel
                </button>
                <button 
                  type="submit"
                  className="px-6 py-2 bg-primary hover:bg-copper-glow text-void-black font-label-sm text-xs uppercase tracking-widest font-semibold rounded shadow-lg hover:shadow-primary/10 transition-all"
                >
                  Forge Entity
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </AppShell>
  );
};
