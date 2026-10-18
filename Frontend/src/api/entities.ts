// Owner: Person A (feature/manual-entities). Contract: docs/api.md §7 and §13.
import { apiFetch } from './client';

export type VersionStatus = 'ACTIVE' | 'SUPERSEDED' | 'CONTRADICTED';

export interface FactVersionResponse {
  id: string;
  fact_id: string;
  chapter_id: string | null;
  value: unknown;
  status: VersionStatus;
  confidence: number;
  created_at: string;
}

export interface FactResponse {
  id: string;
  property_name: string;
  created_at: string;
  current_version: FactVersionResponse | null;
}

export interface EntityResponse {
  id: string;
  world_id: string;
  entity_type: string;
  canonical_name: string;
  source_extraction_id: string | null;
  provenance: string | null;
  aliases: string[];
  facts: FactResponse[];
  created_at: string;
  updated_at: string;
}

/** §7.2 */
export interface EntityCreateRequest {
  canonical_name: string;
  entity_type?: string;
  aliases?: string[];
  attributes?: Record<string, unknown>;
}

/** §7.4 */
export interface EntityUpdateRequest {
  canonical_name?: string;
  entity_type?: string;
  attributes?: Record<string, unknown>;
}

/** §7.6 */
export interface FactCreateRequest {
  property_name: string;
  value: unknown;
  confidence?: number;
}

/** §7.6 response */
export interface FactCreateResponse {
  id: string;
  property: string;
  value: unknown;
  status: VersionStatus;
}

/** §13.1 */
export interface MergeEntitiesRequest {
  source_id: string;
  target_id: string;
}

/** §13.2 */
export interface BulkDeleteEntitiesRequest {
  entity_ids: string[];
}

/** §13.3 */
export interface AliasCreateRequest {
  alias: string;
}

/** POST /worlds/{worldId}/entities → 201 (§7.2) */
export async function createEntity(worldId: string, body: EntityCreateRequest): Promise<EntityResponse> {
  return apiFetch<EntityResponse>(`/worlds/${worldId}/entities`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

/** PUT /worlds/{worldId}/entities/{entityId} → 200 (§7.4) */
export async function updateEntity(worldId: string, entityId: string, body: EntityUpdateRequest): Promise<EntityResponse> {
  return apiFetch<EntityResponse>(`/worlds/${worldId}/entities/${entityId}`, {
    method: 'PUT',
    body: JSON.stringify(body),
  });
}

/** DELETE /worlds/{worldId}/entities/{entityId} → 204 (§7.5) */
export async function deleteEntity(worldId: string, entityId: string): Promise<void> {
  await apiFetch<void>(`/worlds/${worldId}/entities/${entityId}`, {
    method: 'DELETE',
  });
}

/** POST /worlds/{worldId}/entities/{entityId}/facts → 201 (§7.6) */
export async function addFact(worldId: string, entityId: string, body: FactCreateRequest): Promise<FactCreateResponse> {
  return apiFetch<FactCreateResponse>(`/worlds/${worldId}/entities/${entityId}/facts`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

/** DELETE /worlds/{worldId}/entities/{entityId}/facts/{factId} → 204 (§7.7) */
export async function deleteFact(worldId: string, entityId: string, factId: string): Promise<void> {
  await apiFetch<void>(`/worlds/${worldId}/entities/${entityId}/facts/${factId}`, {
    method: 'DELETE',
  });
}

/** POST /worlds/{worldId}/entities/merge → 200, the surviving target (§13.1) */
export async function mergeEntities(worldId: string, body: MergeEntitiesRequest): Promise<EntityResponse> {
  return apiFetch<EntityResponse>(`/worlds/${worldId}/entities/merge`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

/** POST /worlds/{worldId}/entities/bulk-delete → 204 (§13.2) */
export async function bulkDeleteEntities(worldId: string, body: BulkDeleteEntitiesRequest): Promise<void> {
  await apiFetch<void>(`/worlds/${worldId}/entities/bulk-delete`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

/** POST /worlds/{worldId}/entities/{entityId}/aliases → 201 (§13.3) */
export async function addAlias(worldId: string, entityId: string, body: AliasCreateRequest): Promise<EntityResponse> {
  return apiFetch<EntityResponse>(`/worlds/${worldId}/entities/${entityId}/aliases`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

/** DELETE /worlds/{worldId}/entities/{entityId}/aliases?alias=... → 204 (§13.4) */
export async function removeAlias(worldId: string, entityId: string, alias: string): Promise<void> {
  await apiFetch<void>(`/worlds/${worldId}/entities/${entityId}/aliases?alias=${encodeURIComponent(alias)}`, {
    method: 'DELETE',
  });
}
