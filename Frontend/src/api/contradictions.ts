// Contradiction status changes beyond resolve-with-a-choice: reject (DISMISSED) and restore (DETECTED).
import { apiFetch } from './client';

export type ContradictionStatus = 'DETECTED' | 'RESOLVED' | 'DISMISSED';

/** POST /worlds/{id}/contradictions/{cid}/resolve with only a status: no version is changed. */
export const setContradictionStatus = (worldId: string, contradictionId: string, status: ContradictionStatus) =>
  apiFetch(`/worlds/${worldId}/contradictions/${contradictionId}/resolve`, {
    method: 'POST',
    body: JSON.stringify({ status }),
  });
