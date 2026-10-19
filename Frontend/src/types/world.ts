export interface Entity {
  id: string;
  name: string;
  type: 'character' | 'location' | 'object' | 'event';
  subtype?: string;
  alias?: string;
  aliases?: string[];
  description: string;
  image?: string;
  traits?: string[];
  facts: {
    id: string;
    text: string;
    source: string;
    type: 'extracted' | 'manual';
    property_name?: string;
    value?: unknown;
  }[];
  relationships: {
    targetId: string;
    targetName: string;
    targetType: 'character' | 'location' | 'object' | 'event';
    relation: string;
    isNegative?: boolean;
  }[];
  appearances: string[];
}

export interface TimelineEvent {
  id: string;
  year: number;
  period: string;
  title: string;
  description: string;
  stateChanges: {
    entityId: string;
    entityName: string;
    entityType: 'character' | 'location' | 'object';
    field: string;
    before: string;
    after: string;
    isError?: boolean;
  }[];
  chapters: { id: string; name: string }[];
}

export interface Contradiction {
  id: string;
  title: string;
  category: string;
  targetEntityId: string;
  severity: 'high' | 'medium' | 'low';
  summary: string;
  sources: {
    sourceName: string;
    text: string;
    highlightedWord: string;
  }[];
  resolved: boolean;
  old_fact_version_id?: string | null;
  new_fact_version_id?: string | null;
  old_relationship_version_id?: string | null;
  new_relationship_version_id?: string | null;
}

export interface Chapter {
  id: string;
  number: number;
  title: string;
  content: string;
  wordCount: number;
}

export interface Manuscript {
  id: string;
  title: string;
  chapters: Chapter[];
}

export interface World {
  id: string;
  name: string;
  description: string;
  entityCount: number;
  manuscriptCount: number;
  characterCount: number;
  locationCount: number;
  objectCount: number;
  eventCount: number;
}
