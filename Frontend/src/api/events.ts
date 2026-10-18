// Owner: Person B (feature/graph-timeline). Contract: docs/api.md §9 and §15.
import { apiFetch } from './client';

export interface EventParticipantResponse {
  entity_id: string;
  entity_name: string | null;
  role: string;
}

/** Same shape as a timeline event (TimelineEventResponse). */
export interface EventResponse {
  id: string;
  world_id: string;
  chapter_id: string | null;
  chapter_number: number | null;
  event_type: string;
  description: string;
  start_position: number | null;
  end_position: number | null;
  sequence_index: number | null;
  confidence: number;
  created_at: string;
  participants: EventParticipantResponse[];
}

export interface TimelineResponse {
  events: EventResponse[];
  total: number;
}

export interface EventParticipantInput {
  entity_id: string;
  role?: string;
}

/** §15.1 */
export interface EventCreateRequest {
  description: string;
  event_type?: string;
  chapter_id?: string | null;
  sequence_index?: number | null;
  participants?: EventParticipantInput[];
}

/** §15.3: any subset; `participants` replaces the whole list. */
export interface EventUpdateRequest {
  description?: string;
  event_type?: string;
  chapter_id?: string | null;
  participants?: EventParticipantInput[];
}

/** §15.5: every event in the chapter, exactly once, in the new order. */
export interface EventReorderRequest {
  chapter_id: string | null;
  event_ids: string[];
}

/** GET /worlds/{worldId}/timeline → 200 (§9.1) */
export async function getTimeline(worldId: string): Promise<TimelineResponse> {
  return apiFetch<TimelineResponse>(`/worlds/${worldId}/timeline`);
}

/** GET /worlds/{worldId}/events/{eventId} → 200 (§15.2) */
export async function getEvent(worldId: string, eventId: string): Promise<EventResponse> {
  return apiFetch<EventResponse>(`/worlds/${worldId}/events/${eventId}`);
}

/** POST /worlds/{worldId}/events → 201 (§15.1) */
export async function createEvent(
  worldId: string,
  body: EventCreateRequest,
): Promise<EventResponse> {
  return apiFetch<EventResponse>(`/worlds/${worldId}/events`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

/** PUT /worlds/{worldId}/events/{eventId} → 200 (§15.3) */
export async function updateEvent(
  worldId: string,
  eventId: string,
  body: EventUpdateRequest,
): Promise<EventResponse> {
  return apiFetch<EventResponse>(`/worlds/${worldId}/events/${eventId}`, {
    method: 'PUT',
    body: JSON.stringify(body),
  });
}

/** DELETE /worlds/{worldId}/events/{eventId} → 204 (§15.4) */
export async function deleteEvent(worldId: string, eventId: string): Promise<void> {
  await apiFetch<void>(`/worlds/${worldId}/events/${eventId}`, {
    method: 'DELETE',
  });
}

/** PATCH /worlds/{worldId}/events/reorder → 200, that chapter's events in the new order (§15.5) */
export async function reorderEvents(
  worldId: string,
  body: EventReorderRequest,
): Promise<TimelineResponse> {
  return apiFetch<TimelineResponse>(`/worlds/${worldId}/events/reorder`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}
