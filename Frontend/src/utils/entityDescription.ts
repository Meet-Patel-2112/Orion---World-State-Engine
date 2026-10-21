import type { EntityResponse } from '../api/entities';

export function getEntityDescription(entity: Pick<EntityResponse, 'facts'>): string {
  const value = entity.facts?.find(fact => fact.property_name === 'description')?.current_version?.value;
  return typeof value === 'string' ? value : '';
}
