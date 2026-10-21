import { create } from 'zustand';
import type { 
  World, 
  Entity, 
  TimelineEvent, 
  Contradiction, 
  Manuscript 
} from '../types/world';
import { apiFetch } from '../api/client';

// Everything shown comes from the API: failed or empty fetches show nothing rather than invented records.
const titleCase = (code: string) => code.toLowerCase().replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase());

interface WorldState {
  worlds: World[];
  entities: Entity[];
  timelineEvents: TimelineEvent[];
  contradictions: Contradiction[];
  manuscripts: Manuscript[];
  
  activeWorldId: string | null;
  activeManuscriptId: string | null;
  activeChapterId: string | null;
  activeEntityId: string | null;
  activeTimelineEventId: string | null;
  
  // Navigation / Panel states
  isEntityPanelOpen: boolean;
  
  // Actions
  setActiveWorld: (id: string | null) => void;
  setActiveManuscript: (id: string | null) => void;
  setActiveChapter: (id: string | null) => void;
  setActiveEntity: (id: string | null) => void;
  setActiveTimelineEvent: (id: string | null) => void;
  setEntityPanelOpen: (isOpen: boolean) => void;
  
  // World Actions
  setWorlds: (worlds: World[]) => void;
  addWorld: (world: World) => void;
  
  // Entity Actions
  fetchEntitiesForWorld: (worldId: string) => Promise<void>;
  addEntity: (entity: Omit<Entity, 'facts' | 'relationships' | 'appearances'>) => Promise<void>;
  updateEntity: (id: string, updated: Partial<Entity>) => Promise<void> | void;
  deleteEntity: (id: string) => Promise<void> | void;
  mergeEntities: (sourceId: string, targetId: string) => Promise<void>;
  bulkDeleteEntities: (entityIds: string[]) => Promise<void>;
  addAlias: (entityId: string, alias: string) => Promise<void>;
  removeAlias: (entityId: string, alias: string) => Promise<void>;
  
  // Fact Actions
  addFact: (entityId: string, propertyOrText: string, valueOrType?: unknown, source?: string) => Promise<void> | void;
  deleteFact: (entityId: string, factId: string) => Promise<void> | void;

  // Timeline & Contradictions Actions
  fetchTimelineForWorld: (worldId: string) => Promise<void>;
  fetchContradictionsForWorld: (worldId: string) => Promise<void>;
  resolveContradictionInBackend: (
    worldId: string,
    contradictionId: string,
    preferredFactVersionId?: string | null,
    preferredRelationshipVersionId?: string | null
  ) => Promise<void>;
  resolveContradiction: (id: string) => void;
  
  // Manuscript Actions
  fetchManuscriptsForWorld: (worldId: string) => Promise<Manuscript[]>;
  updateChapterContent: (manuscriptId: string, chapterId: string, content: string) => void;
  deleteChapter: (manuscriptId: string, chapterId: string) => void;
  deleteManuscript: (manuscriptId: string) => void;
}

export const useWorldStore = create<WorldState>((set, get) => ({
  worlds: [],
  entities: [],
  timelineEvents: [],
  contradictions: [],
  manuscripts: [],
  
  activeWorldId: null,
  activeManuscriptId: null,
  activeChapterId: null,
  activeEntityId: null,
  activeTimelineEventId: null,
  
  isEntityPanelOpen: false,
  
  setActiveWorld: (id) => set({ 
    activeWorldId: id,
    activeManuscriptId: null,
    activeChapterId: null,
    activeEntityId: null,
    activeTimelineEventId: null,
    isEntityPanelOpen: false,
    manuscripts: [],
    entities: [],                     // never show the previous world's data while this one loads
    timelineEvents: [],
    contradictions: []
  }),
  
  setActiveManuscript: (id) => set((state) => {
    const manuscript = state.manuscripts.find((m) => m.id === id);
    const firstChapterId = manuscript?.chapters[0]?.id || null;
    return {
      activeManuscriptId: id,
      activeChapterId: firstChapterId
    };
  }),
  
  setActiveChapter: (id) => set({ activeChapterId: id }),
  
  setActiveEntity: (id) => set(() => ({
    activeEntityId: id,
    isEntityPanelOpen: id !== null
  })),
  
  setActiveTimelineEvent: (id) => set((state) => {
    const updatedWorlds = state.worlds.map((w) => {
      if (w.id === state.activeWorldId && id) {
        const ev = state.timelineEvents.find((e) => e.id === id);
        if (ev) {
          return {
            ...w,
            description: `${ev.title} (${ev.period} • Year ${ev.year}): ${ev.description}`
          };
        }
      }
      return w;
    });
    return {
      activeTimelineEventId: id,
      worlds: updatedWorlds
    };
  }),
  
  setEntityPanelOpen: (isOpen) => set((state) => ({ 
    isEntityPanelOpen: isOpen,
    activeEntityId: isOpen ? state.activeEntityId : null
  })),
  
  setWorlds: (worlds) => set({ worlds }),
  
  addWorld: (world) => set((state) => ({
    worlds: [...state.worlds, world]
  })),

  fetchEntitiesForWorld: async (worldId: string) => {
    try {
      const data = await apiFetch<any[]>(`/worlds/${worldId}/entities`);
      const mapped: Entity[] = data.map((ent: any) => ({
        id: ent.id,
        name: ent.canonical_name,
        type: ent.entity_type as any,
        description: (ent.aliases || []).length ? `Also called: ${ent.aliases.join(', ')}` : '',
        alias: (ent.aliases || [])[0] || '',
        aliases: ent.aliases || [],
        facts: (ent.facts || []).map((f: any) => ({
          id: f.id,
          text: `${f.property_name}: ${f.current_version?.value ?? ''}`,
          source: f.current_version?.chapter_id || 'System',
          type: 'extracted',
          property_name: f.property_name,
          value: f.current_version?.value
        })),
        relationships: [],
        appearances: []
      }));

      set({ entities: mapped });
    } catch (e) {
      console.error("Could not fetch entities from API", e);
    }
  },

  fetchTimelineForWorld: async (worldId: string) => {
    try {
      const data = await apiFetch<any>(`/worlds/${worldId}/timeline`);
      const mapped: TimelineEvent[] = (data?.events || []).map((ev: any) => ({
        id: ev.id,
        year: ev.chapter_number ?? 0,           // the backend orders by chapter; there are no in-story years
        period: (ev.participants || []).map((p: any) => p.entity_name).filter(Boolean).join(', ') || 'No participants',
        title: titleCase(ev.event_type || 'EVENT'),
        description: ev.description || '',
        stateChanges: [],
        chapters: []
      }));
      set({ timelineEvents: mapped });
    } catch (e) {
      console.error("Could not fetch timeline from API", e);
    }
  },

  fetchContradictionsForWorld: async (worldId: string) => {
    try {
      const data = await apiFetch<any[]>(`/worlds/${worldId}/contradictions`);
      // explanation = "[RULE_ID] what the rule found" (app/consistency); confidence is the rule's own
      const mapped: Contradiction[] = (data || []).map((c: any) => {
        const [, rule = c.contradiction_type, text = c.explanation] = /^\[(\w+)\]\s*(.*)$/s.exec(c.explanation || '') || [];
        return {
          id: c.id,
          title: titleCase(rule || 'CONTRADICTION'),
          category: titleCase(c.contradiction_type || ''),
          targetEntityId: '',
          severity: c.confidence >= 0.85 ? 'high' : c.confidence >= 0.6 ? 'medium' : 'low',
          summary: text || '',
          resolved: c.status === 'RESOLVED',
          status: c.status,
          sources: (c.sources || []).map((s: any) => ({
            sourceName: s.chapter_title ? `${s.label} · ${s.chapter_title}` : s.label,
            text: s.snippet || s.value || '',
            highlightedWord: s.highlight || '',
            chapterId: s.chapter_id,
            manuscriptId: s.manuscript_id,
            start: s.start,
            end: s.end
          })),
          old_fact_version_id: c.old_fact_version_id || null,
          new_fact_version_id: c.new_fact_version_id || null,
          old_relationship_version_id: c.old_relationship_version_id || null,
          new_relationship_version_id: c.new_relationship_version_id || null
        };
      });
      set({ contradictions: mapped });
    } catch (e) {
      console.error("Could not fetch contradictions from API", e);
    }
  },

  resolveContradictionInBackend: async (
    worldId: string,
    contradictionId: string,
    preferredFactVersionId?: string | null,
    preferredRelationshipVersionId?: string | null
  ) => {
    try {
      const payload: Record<string, any> = { status: 'RESOLVED' };
      if (preferredFactVersionId) {
        payload.preferred_fact_version_id = preferredFactVersionId;
      }
      if (preferredRelationshipVersionId) {
        payload.preferred_relationship_version_id = preferredRelationshipVersionId;
      }
      await apiFetch(`/worlds/${worldId}/contradictions/${contradictionId}/resolve`, {
        method: 'POST',
        body: JSON.stringify(payload)
      });
      get().resolveContradiction(contradictionId);   // only once the backend has it
    } catch (e) {
      console.error("Could not resolve the contradiction on the API", e);
      throw e;
    }
  },
  
  addEntity: async (entityData) => {
    const activeWorldId = get().activeWorldId;
    let newId = `entity-${Date.now()}`;
    let createdEntity: Entity = {
      ...entityData,
      id: newId,
      facts: [],
      relationships: [],
      appearances: []
    };

    if (!activeWorldId) return;                      // nowhere to save it
    try {
      const res = await apiFetch<any>(`/worlds/${activeWorldId}/entities`, {
        method: 'POST',
        body: JSON.stringify({
          canonical_name: entityData.name,
          entity_type: entityData.type,
          aliases: entityData.alias ? [entityData.alias] : [],
          attributes: { description: entityData.description, subtype: entityData.subtype }
        })
      });
      createdEntity.id = res.id;
    } catch (err) {
      console.error("Failed to create entity on API; not added", err);
      return;                                        // a local-only entity would look saved but isn't
    }

    set((state) => {
      const updatedWorlds = state.worlds.map((w) => {
        if (w.id === state.activeWorldId) {
          return {
            ...w,
            entityCount: w.entityCount + 1,
            characterCount: entityData.type === 'character' ? w.characterCount + 1 : w.characterCount,
            locationCount: entityData.type === 'location' ? w.locationCount + 1 : w.locationCount,
            objectCount: entityData.type === 'object' ? w.objectCount + 1 : w.objectCount,
            eventCount: entityData.type === 'event' ? w.eventCount + 1 : w.eventCount
          };
        }
        return w;
      });

      return {
        entities: [...state.entities, createdEntity],
        worlds: updatedWorlds,
        activeEntityId: createdEntity.id,
        isEntityPanelOpen: true
      };
    });
  },
  
  updateEntity: async (id, updated) => {
    const activeWorldId = get().activeWorldId;
    if (activeWorldId) {
      try {
        const body: Record<string, any> = {};
        if (updated.name !== undefined) body.canonical_name = updated.name;
        if (updated.type !== undefined) body.entity_type = updated.type;
        if (updated.description !== undefined || updated.subtype !== undefined) {
          body.attributes = {
            description: updated.description,
            subtype: updated.subtype
          };
        }
        await apiFetch(`/worlds/${activeWorldId}/entities/${id}`, {
          method: 'PUT',
          body: JSON.stringify(body)
        });
      } catch (err) {
        console.error("Failed to update entity on API", err);
      }
    }
    set((state) => ({
      entities: state.entities.map((e) => e.id === id ? { ...e, ...updated } : e)
    }));
  },
  
  deleteEntity: async (id) => {
    const activeWorldId = get().activeWorldId;
    if (activeWorldId) {
      try {
        await apiFetch(`/worlds/${activeWorldId}/entities/${id}`, {
          method: 'DELETE'
        });
      } catch (err) {
        console.error("Failed to delete entity on API", err);
      }
    }
    set((state) => {
      const entityToDelete = state.entities.find((e) => e.id === id);
      const updatedWorlds = state.worlds.map((w) => {
        if (w.id === state.activeWorldId && entityToDelete) {
          return {
            ...w,
            entityCount: Math.max(0, w.entityCount - 1),
            characterCount: entityToDelete.type === 'character' ? Math.max(0, w.characterCount - 1) : w.characterCount,
            locationCount: entityToDelete.type === 'location' ? Math.max(0, w.locationCount - 1) : w.locationCount,
            objectCount: entityToDelete.type === 'object' ? Math.max(0, w.objectCount - 1) : w.objectCount,
            eventCount: entityToDelete.type === 'event' ? Math.max(0, w.eventCount - 1) : w.eventCount
          };
        }
        return w;
      });

      return {
        entities: state.entities.filter((e) => e.id !== id),
        worlds: updatedWorlds,
        activeEntityId: state.activeEntityId === id ? null : state.activeEntityId,
        isEntityPanelOpen: state.activeEntityId === id ? false : state.isEntityPanelOpen
      };
    });
  },

  mergeEntities: async (sourceId: string, targetId: string) => {
    const activeWorldId = get().activeWorldId;
    if (!activeWorldId) return;

    try {
      const survivor = await apiFetch<any>(`/worlds/${activeWorldId}/entities/merge`, {
        method: 'POST',
        body: JSON.stringify({ source_id: sourceId, target_id: targetId })
      });

      set((state) => {
        const sourceEntity = state.entities.find((e) => e.id === sourceId);
        const mappedSurvivor: Entity = {
          id: survivor.id,
          name: survivor.canonical_name,
          type: survivor.entity_type as any,
          description: (survivor.aliases || []).length ? `Also called: ${survivor.aliases.join(', ')}` : '',
          alias: (survivor.aliases || [])[0] || '',
          aliases: survivor.aliases || [],
          facts: (survivor.facts || []).map((f: any) => ({
            id: f.id,
            text: `${f.property_name}: ${f.current_version?.value ?? ''}`,
            source: f.current_version?.chapter_id || 'System',
            type: 'extracted',
            property_name: f.property_name,
            value: f.current_version?.value
          })),
          relationships: [],
          appearances: []
        };

        const updatedWorlds = state.worlds.map((w) => {
          if (w.id === state.activeWorldId) {
            return {
              ...w,
              entityCount: Math.max(0, w.entityCount - 1),
              characterCount: sourceEntity?.type === 'character' ? Math.max(0, w.characterCount - 1) : w.characterCount,
              locationCount: sourceEntity?.type === 'location' ? Math.max(0, w.locationCount - 1) : w.locationCount,
              objectCount: sourceEntity?.type === 'object' ? Math.max(0, w.objectCount - 1) : w.objectCount,
              eventCount: sourceEntity?.type === 'event' ? Math.max(0, w.eventCount - 1) : w.eventCount
            };
          }
          return w;
        });

        return {
          entities: state.entities
            .filter((e) => e.id !== sourceId)
            .map((e) => e.id === targetId ? mappedSurvivor : e),
          worlds: updatedWorlds,
          activeEntityId: state.activeEntityId === sourceId ? targetId : state.activeEntityId
        };
      });

      get().fetchContradictionsForWorld(activeWorldId);
    } catch (err) {
      console.error("Failed to merge entities on API", err);
      throw err;
    }
  },

  bulkDeleteEntities: async (entityIds: string[]) => {
    const activeWorldId = get().activeWorldId;
    if (!activeWorldId || !entityIds.length) return;

    try {
      await apiFetch(`/worlds/${activeWorldId}/entities/bulk-delete`, {
        method: 'POST',
        body: JSON.stringify({ entity_ids: entityIds })
      });

      set((state) => {
        const idSet = new Set(entityIds);
        const deletedEntities = state.entities.filter((e) => idSet.has(e.id));
        const updatedWorlds = state.worlds.map((w) => {
          if (w.id === state.activeWorldId) {
            let charCount = w.characterCount;
            let locCount = w.locationCount;
            let objCount = w.objectCount;
            let evCount = w.eventCount;
            for (const de of deletedEntities) {
              if (de.type === 'character') charCount = Math.max(0, charCount - 1);
              if (de.type === 'location') locCount = Math.max(0, locCount - 1);
              if (de.type === 'object') objCount = Math.max(0, objCount - 1);
              if (de.type === 'event') evCount = Math.max(0, evCount - 1);
            }
            return {
              ...w,
              entityCount: Math.max(0, w.entityCount - deletedEntities.length),
              characterCount: charCount,
              locationCount: locCount,
              objectCount: objCount,
              eventCount: evCount
            };
          }
          return w;
        });

        return {
          entities: state.entities.filter((e) => !idSet.has(e.id)),
          worlds: updatedWorlds,
          activeEntityId: idSet.has(state.activeEntityId || '') ? null : state.activeEntityId,
          isEntityPanelOpen: idSet.has(state.activeEntityId || '') ? false : state.isEntityPanelOpen
        };
      });

      get().fetchContradictionsForWorld(activeWorldId);
    } catch (err) {
      console.error("Failed to bulk delete entities on API", err);
      throw err;
    }
  },

  addAlias: async (entityId: string, alias: string) => {
    const activeWorldId = get().activeWorldId;
    if (!activeWorldId) return;

    try {
      const updated = await apiFetch<any>(`/worlds/${activeWorldId}/entities/${entityId}/aliases`, {
        method: 'POST',
        body: JSON.stringify({ alias })
      });

      set((state) => ({
        entities: state.entities.map((e) => {
          if (e.id === entityId) {
            return {
              ...e,
              alias: (updated.aliases || [])[0] || '',
              aliases: updated.aliases || [],
              description: (updated.aliases || []).length ? `Also called: ${updated.aliases.join(', ')}` : e.description
            };
          }
          return e;
        })
      }));
    } catch (err) {
      console.error("Failed to add alias on API", err);
      throw err;
    }
  },

  removeAlias: async (entityId: string, alias: string) => {
    const activeWorldId = get().activeWorldId;
    if (!activeWorldId) return;

    try {
      await apiFetch(`/worlds/${activeWorldId}/entities/${entityId}/aliases?alias=${encodeURIComponent(alias)}`, {
        method: 'DELETE'
      });

      set((state) => ({
        entities: state.entities.map((e) => {
          if (e.id === entityId) {
            const currentAliases: string[] = (e as any).aliases || (e.alias ? [e.alias] : []);
            const newAliases = currentAliases.filter((a) => a.toLowerCase() !== alias.toLowerCase());
            return {
              ...e,
              alias: newAliases[0] || '',
              aliases: newAliases,
              description: newAliases.length ? `Also called: ${newAliases.join(', ')}` : ''
            };
          }
          return e;
        })
      }));
    } catch (err) {
      console.error("Failed to remove alias on API", err);
      throw err;
    }
  },
  
  addFact: async (entityId, propertyOrText, valueOrType, source = 'Manual Entry') => {
    const activeWorldId = get().activeWorldId;
    let propName = propertyOrText.trim();
    let val: unknown = valueOrType;

    if (valueOrType === 'manual' || valueOrType === 'extracted' || valueOrType === undefined) {
      if (propertyOrText.includes(':')) {
        const parts = propertyOrText.split(':');
        propName = parts[0].trim();
        val = parts.slice(1).join(':').trim();
      } else {
        propName = 'attribute';
        val = propertyOrText.trim();
      }
    }

    let factVersionId = `fact-${Date.now()}`;
    if (activeWorldId) {
      try {
        const res = await apiFetch<any>(`/worlds/${activeWorldId}/entities/${entityId}/facts`, {
          method: 'POST',
          body: JSON.stringify({
            property_name: propName,
            value: val,
            confidence: 1.0
          })
        });
        if (res && res.id) {
          factVersionId = res.id;
        }
      } catch (err) {
        console.error("Failed to add fact on API", err);
      }
    }

    set((state) => ({
      entities: state.entities.map((e) => {
        if (e.id === entityId) {
          const newFact = {
            id: factVersionId,
            text: `${propName}: ${String(val)}`,
            source: typeof source === 'string' ? source : 'Manual Entry',
            type: 'manual' as const,
            property_name: propName,
            value: val
          };
          return {
            ...e,
            facts: [...e.facts, newFact]
          };
        }
        return e;
      })
    }));
  },
  
  deleteFact: async (entityId, factId) => {
    const activeWorldId = get().activeWorldId;
    if (activeWorldId) {
      try {
        await apiFetch(`/worlds/${activeWorldId}/entities/${entityId}/facts/${factId}`, {
          method: 'DELETE'
        });
      } catch (err) {
        console.error("Failed to delete fact on API", err);
      }
    }

    set((state) => ({
      entities: state.entities.map((e) => {
        if (e.id === entityId) {
          return {
            ...e,
            facts: e.facts.filter((f) => f.id !== factId)
          };
        }
        return e;
      })
    }));
  },
  
  resolveContradiction: (id) => set((state) => {
    const updatedContradictions = state.contradictions.map((c) => 
      c.id === id ? { ...c, resolved: true } : c
    );
    return {
      contradictions: updatedContradictions
    };
  }),
  
  updateChapterContent: (manuscriptId, chapterId, content) => set((state) => {
    const updatedManuscripts = state.manuscripts.map((m) => {
      if (m.id === manuscriptId) {
        const updatedChapters = m.chapters.map((ch) => {
          if (ch.id === chapterId) {
            const wordCount = content.trim() ? content.trim().split(/\s+/).length : 0;
            return {
              ...ch,
              content,
              wordCount
            };
          }
          return ch;
        });
        return { ...m, chapters: updatedChapters };
      }
      return m;
    });
    return { manuscripts: updatedManuscripts };
  }),

  deleteChapter: (manuscriptId, chapterId) => set((state) => {
    const updatedManuscripts = state.manuscripts
      .map(m => {
        if (m.id === manuscriptId) {
          return { ...m, chapters: m.chapters.filter(c => c.id !== chapterId) };
        }
        return m;
      })
      .filter(m => m.chapters.length > 0);

    const activeManuscriptRemoved = !updatedManuscripts.some(m => m.id === state.activeManuscriptId);

    return {
      manuscripts: updatedManuscripts,
      activeManuscriptId: activeManuscriptRemoved
        ? (updatedManuscripts[0]?.id || null)
        : state.activeManuscriptId,
      activeChapterId: state.activeChapterId === chapterId || activeManuscriptRemoved
        ? (activeManuscriptRemoved ? (updatedManuscripts[0]?.chapters[0]?.id || null) : null)
        : state.activeChapterId
    };
  }),

  deleteManuscript: (manuscriptId) => set((state) => {
    const updatedManuscripts = state.manuscripts.filter(m => m.id !== manuscriptId);
    const activeManuscriptRemoved = state.activeManuscriptId === manuscriptId;

    return {
      manuscripts: updatedManuscripts,
      activeManuscriptId: activeManuscriptRemoved
        ? (updatedManuscripts[0]?.id || null)
        : state.activeManuscriptId,
      activeChapterId: activeManuscriptRemoved
        ? (updatedManuscripts[0]?.chapters[0]?.id || null)
        : state.activeChapterId
    };
  }),

  fetchManuscriptsForWorld: async (worldId: string) => {
    try {
      const data = await apiFetch<any[]>(`/worlds/${worldId}/manuscripts`);
      const mapped: Manuscript[] = await Promise.all(
        data.map(async (m: any) => {
          let chapters: any[] = [];
          try {
            const chs = await apiFetch<any[]>(`/worlds/${worldId}/manuscripts/${m.id}/chapters`);
            chapters = chs.map(ch => ({
              id: ch.id,
              number: ch.chapter_number,
              title: ch.title,
              content: ch.content || '',
              wordCount: ch.word_count ?? (ch.content ? ch.content.trim().split(/\s+/).length : 0)
            }));
          } catch (_) {}

          return {
            id: m.id,
            title: m.title,
            chapters
          };
        })
      );
      // Filter out manuscripts that have 0 chapters so empty manuscripts are not displayed
      const validManuscripts = mapped.filter(m => m.chapters.length > 0);
      set({ manuscripts: validManuscripts });
      
      // Select the first manuscript/chapter if nothing is selected or if previously active manuscript was removed
      const currentState = get();
      if ((!currentState.activeManuscriptId || !validManuscripts.some(m => m.id === currentState.activeManuscriptId)) && validManuscripts.length > 0) {
        set({
          activeManuscriptId: validManuscripts[0].id,
          activeChapterId: validManuscripts[0].chapters.length > 0 ? validManuscripts[0].chapters[0].id : null
        });
      } else if (validManuscripts.length === 0) {
        set({
          activeManuscriptId: null,
          activeChapterId: null
        });
      }
      return validManuscripts;
    } catch (err) {
      console.warn("Failed to fetch manuscripts", err);
      return [];
    }
  }
}));
