// Owner: Person B (feature/graph-timeline). Contract: docs/api.md §14.
import type { VersionStatus } from './entities';
import { apiFetch } from './client';

export interface RelationshipVersionResponse {
  id: string;
  relationship_id: string;
  relationship_type: string;
  status: VersionStatus;
  chapter_id: string | null;
  chapter_number: number | null;
  confidence: number;
  created_at: string;
}

export interface RelationshipResponse {
  id: string;
  world_id: string;
  source_entity_id: string;
  source_name: string;
  target_entity_id: string;
  target_name: string;
  created_at: string;
  /** Latest ACTIVE version, or null if none is active. */
  current_version: RelationshipVersionResponse | null;
  /** Every version, newest first. */
  versions: RelationshipVersionResponse[];
}

/** §14.3 */
export interface RelationshipCreateRequest {
  source_entity_id: string;
  target_entity_id: string;
  relationship_type: string;
  chapter_id?: string | null;
  confidence?: number;
}

/** §14.4 */
export interface RelationshipUpdateRequest {
  relationship_type: string;
  chapter_id?: string | null;
  confidence?: number;
}

export interface ListRelationshipsParams {
  entity_id?: string;
}

/** GET /worlds/{worldId}/relationships → 200 (§14.1) */
export async function listRelationships(
  worldId: string,
  params?: ListRelationshipsParams,
): Promise<RelationshipResponse[]> {
  const query = params?.entity_id ? `?entity_id=${encodeURIComponent(params.entity_id)}` : '';
  return apiFetch<RelationshipResponse[]>(`/worlds/${worldId}/relationships${query}`);
}

/** GET /worlds/{worldId}/relationships/{relationshipId} → 200 (§14.2) */
export async function getRelationship(
  worldId: string,
  relationshipId: string,
): Promise<RelationshipResponse> {
  return apiFetch<RelationshipResponse>(`/worlds/${worldId}/relationships/${relationshipId}`);
}

/** POST /worlds/{worldId}/relationships → 201 new pair, 200 new version on an existing pair (§14.3) */
export async function createRelationship(
  worldId: string,
  body: RelationshipCreateRequest,
): Promise<RelationshipResponse> {
  return apiFetch<RelationshipResponse>(`/worlds/${worldId}/relationships`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

/** PUT /worlds/{worldId}/relationships/{relationshipId} → 200 (§14.4) */
export async function updateRelationship(
  worldId: string,
  relationshipId: string,
  body: RelationshipUpdateRequest,
): Promise<RelationshipResponse> {
  return apiFetch<RelationshipResponse>(`/worlds/${worldId}/relationships/${relationshipId}`, {
    method: 'PUT',
    body: JSON.stringify(body),
  });
}

/** DELETE /worlds/{worldId}/relationships/{relationshipId} → 204 (§14.5) */
export async function deleteRelationship(
  worldId: string,
  relationshipId: string,
): Promise<void> {
  await apiFetch<void>(`/worlds/${worldId}/relationships/${relationshipId}`, {
    method: 'DELETE',
  });
}

