// Owner: Extraction (feature/extraction-review). Contract: docs/api.md §17.
import type { AliasCreateRequest, EntityCreateRequest, FactCreateRequest } from './entities';
import type { EventCreateRequest } from './events';
import { apiFetch } from './client';

export type ProposalChange = 'new' | 'changed' | 'known';

/** An existing entity, or the entity created by a `new` entity proposal in the same response. */
export type EntityRef = { entity_id: string } | { entity_ref: string };

interface ProposalBase {
  /** Unique within the response; other proposals point at it through `entity_ref`. */
  id: string;
  change: ProposalChange;
  summary: string;
  confidence: number;
}

export interface EntityProposal extends ProposalBase {
  kind: 'entity';
  change: 'new' | 'known';
  match_entity_id: string | null;
  proposed: EntityCreateRequest;
}

export interface AliasProposal extends ProposalBase {
  kind: 'alias';
  change: 'new' | 'known';
  entity_id: string;
  proposed: AliasCreateRequest;
}

export interface FactProposal extends ProposalBase {
  kind: 'fact';
  entity: EntityRef;
  current: { fact_version_id: string; value: unknown } | null;
  proposed: FactCreateRequest;
}

export interface RelationshipProposal extends ProposalBase {
  kind: 'relationship';
  source: EntityRef;
  target: EntityRef;
  current: { relationship_id: string; relationship_version_id: string; relationship_type: string } | null;
  proposed: { relationship_type: string; chapter_id: string | null; confidence: number };
}

export interface EventProposal extends ProposalBase {
  kind: 'event';
  change: 'new' | 'known';
  participants: { entity: EntityRef; role: string }[];
  proposed: Omit<EventCreateRequest, 'participants'>;
}

export type Proposal = EntityProposal | AliasProposal | FactProposal | RelationshipProposal | EventProposal;

export interface ProposalsResponse {
  job_id: string;
  world_id: string;
  chapter_id: string | null;
  chapter_number: number | null;
  /** `pending` comes with HTTP 202 and an empty list while the job is queued or processing. */
  status: 'pending' | 'ready';
  generated_at: string | null;
  proposals: Proposal[];
}

/** Apply order for the review modal (§17): entity refs must exist before anything points at them. */
export const PROPOSAL_APPLY_ORDER: Proposal['kind'][] = ['entity', 'alias', 'fact', 'relationship', 'event'];

/** GET /jobs/{jobId}/proposals → 200 ready, 202 pending (§17.1) */
export const getProposals = (jobId: string): Promise<ProposalsResponse> =>
  apiFetch<ProposalsResponse>(`/jobs/${jobId}/proposals`);

export interface ApplyResult {
  applied: number;
  skipped: number;
  errors: string[];
}

/**
 * Applies the accepted proposals through the manual endpoints (§17 "Applying"), in PROPOSAL_APPLY_ORDER, so each
 * accepted change is a new version like a manual edit. A rejected or failed `new` entity skips everything that points
 * at it. Alias proposals are skipped: the alias endpoint (§13.3) is not on main yet.
 */
export async function applyProposals(worldId: string, proposals: Proposal[], accepted: Set<string>): Promise<ApplyResult> {
  const created = new Map<string, string>();           // entity proposal id -> new entity id
  const result: ApplyResult = { applied: 0, skipped: 0, errors: [] };
  const resolve = (ref: EntityRef): string | null =>
    'entity_id' in ref ? ref.entity_id : created.get(ref.entity_ref) ?? null;
  const base = `/worlds/${worldId}`;
  const post = (path: string, body: unknown) => apiFetch<any>(`${base}${path}`, { method: 'POST', body: JSON.stringify(body) });

  for (const kind of PROPOSAL_APPLY_ORDER) {
    for (const p of proposals) {
      if (p.kind !== kind || p.change === 'known' || !accepted.has(p.id)) continue;
      try {
        if (p.kind === 'entity') {
          const ent = await post('/entities', p.proposed);
          created.set(p.id, ent.id);
        } else if (p.kind === 'alias') {
          result.skipped++;
          continue;
        } else if (p.kind === 'fact') {
          const id = resolve(p.entity);
          if (!id) { result.skipped++; continue; }
          await post(`/entities/${id}/facts`, p.proposed);
        } else if (p.kind === 'relationship') {
          const source = resolve(p.source), target = resolve(p.target);
          if (!source || !target) { result.skipped++; continue; }
          await post('/relationships', { source_entity_id: source, target_entity_id: target, ...p.proposed });
        } else if (p.kind === 'event') {
          const participants = p.participants
            .map((x) => ({ entity_id: resolve(x.entity), role: x.role }))
            .filter((x): x is { entity_id: string; role: string } => x.entity_id !== null);
          await post('/events', { ...p.proposed, participants });
        }
        result.applied++;
      } catch (err: any) {
        result.errors.push(`${p.summary}: ${err?.message ?? 'failed'}`);
      }
    }
  }
  return result;
}
