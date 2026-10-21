from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db, get_current_user_world
from app.core.constants import FactStatus
from app.models.world import World
from app.models.entity import Entity, EntityAlias, EntityMention
from app.models.fact import Fact, FactVersion
from app.models.relationship import Relationship, RelationshipVersion
from app.models.event import Event, EventParticipant
from app.models.extraction_run import ExtractionRun
from app.models.chapter_version import ChapterVersion
from app.schemas.entity import (
    EntityCreate, EntityUpdate, EntityResponse, EntityDetailResponse,
    FactCreate, FactResponse, FactVersionResponse, MergeEntitiesRequest,
    BulkDeleteEntitiesRequest, AliasCreateRequest
)
from app.services.entity_service import EntityService
from app.services.merge_service import MergeService

router = APIRouter()

def current_version(fact):
    """The newest ACTIVE version (versions are newest first): a CONTRADICTED claim is kept but never shown as the
    current value. Newest of any status only if none is active."""
    return next((v for v in fact.versions if v.status == FactStatus.ACTIVE.value),
                fact.versions[0] if fact.versions else None)


def entity_to_response(ent) -> EntityResponse:
    aliases = [a.alias for a in ent.aliases]
    facts_out = []
    for f in ent.facts:
        active_v = current_version(f)
        v_resp = None
        if active_v:
            v_resp = FactVersionResponse(
                id=active_v.id,
                fact_id=active_v.fact_id,
                chapter_id=active_v.chapter_id,
                value=active_v.value,
                status=active_v.status,
                confidence=active_v.confidence,
                created_at=active_v.created_at
            )
        facts_out.append(FactResponse(
            id=f.id,
            property_name=f.property_name,
            created_at=f.created_at,
            current_version=v_resp
        ))
    return EntityResponse(
        id=ent.id,
        world_id=ent.world_id,
        entity_type=ent.entity_type,
        canonical_name=ent.canonical_name,
        source_extraction_id=ent.source_extraction_id,
        provenance=ent.provenance,
        aliases=aliases,
        facts=facts_out,
        created_at=ent.created_at,
        updated_at=ent.updated_at
    )


@router.get("/{world_id}/entities", response_model=List[EntityResponse])
def list_entities(
    world_id: str,
    entity_type: Optional[str] = Query(None),
    world: World = Depends(get_current_user_world),
    db: Session = Depends(get_db)
):
    service = EntityService(db)
    entities = service.list_entities(world.id, entity_type)

    results = []
    for ent in entities:
        aliases = [a.alias for a in ent.aliases]
        facts_out = []
        for f in ent.facts:
            active_v = current_version(f)
            v_resp = None
            if active_v:
                v_resp = FactVersionResponse(
                    id=active_v.id,
                    fact_id=active_v.fact_id,
                    chapter_id=active_v.chapter_id,
                    value=active_v.value,
                    status=active_v.status,
                    confidence=active_v.confidence,
                    created_at=active_v.created_at
                )
            facts_out.append(FactResponse(
                id=f.id,
                property_name=f.property_name,
                created_at=f.created_at,
                current_version=v_resp
            ))

        results.append(EntityResponse(
            id=ent.id,
            world_id=ent.world_id,
            entity_type=ent.entity_type,
            canonical_name=ent.canonical_name,
            source_extraction_id=ent.source_extraction_id,
            provenance=ent.provenance,
            aliases=aliases,
            facts=facts_out,
            created_at=ent.created_at,
            updated_at=ent.updated_at
        ))
    return results

@router.post("/{world_id}/entities", response_model=EntityResponse, status_code=status.HTTP_201_CREATED)
def create_entity(
    world_id: str,
    ent_in: EntityCreate,
    world: World = Depends(get_current_user_world),
    db: Session = Depends(get_db)
):
    service = EntityService(db)
    existing = service.entity_repo.get_by_canonical(world.id, ent_in.canonical_name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An entity with this canonical name already exists in this world."
        )

    ent = service.create_entity(
        world_id=world.id,
        canonical_name=ent_in.canonical_name,
        entity_type=ent_in.entity_type,
        aliases=ent_in.aliases,
        attributes=ent_in.attributes
    )
    return EntityResponse(
        id=ent.id,
        world_id=ent.world_id,
        entity_type=ent.entity_type,
        canonical_name=ent.canonical_name,
        aliases=[a.alias for a in ent.aliases],
        facts=[],
        created_at=ent.created_at,
        updated_at=ent.updated_at
    )

@router.post("/{world_id}/entities/merge", response_model=EntityResponse, status_code=status.HTTP_200_OK)
def merge_entities(
    world_id: str,
    req: MergeEntitiesRequest,
    world: World = Depends(get_current_user_world),
    db: Session = Depends(get_db)
):
    service = MergeService(db)
    survivor = service.merge_entities(world.id, req.source_id, req.target_id)
    return entity_to_response(survivor)

@router.post("/{world_id}/entities/bulk-delete", status_code=status.HTTP_204_NO_CONTENT)
def bulk_delete_entities(
    world_id: str,
    req: BulkDeleteEntitiesRequest,
    world: World = Depends(get_current_user_world),
    db: Session = Depends(get_db)
):
    service = EntityService(db)
    service.bulk_delete_entities(world.id, req.entity_ids)
    return None

@router.get("/{world_id}/entities/{entity_id}", response_model=EntityDetailResponse)
def get_entity(
    world_id: str,
    entity_id: str,
    world: World = Depends(get_current_user_world),
    db: Session = Depends(get_db)
):
    ent = (
        db.query(Entity)
        .options(
            joinedload(Entity.facts).joinedload(Fact.versions).joinedload(FactVersion.chapter),
            joinedload(Entity.aliases),
            joinedload(Entity.outgoing_relationships).joinedload(Relationship.versions).joinedload(RelationshipVersion.chapter),
            joinedload(Entity.outgoing_relationships).joinedload(Relationship.target_entity),
            joinedload(Entity.incoming_relationships).joinedload(Relationship.versions).joinedload(RelationshipVersion.chapter),
            joinedload(Entity.incoming_relationships).joinedload(Relationship.source_entity),
            joinedload(Entity.event_participants).joinedload(EventParticipant.event).joinedload(Event.chapter),
            joinedload(Entity.mentions).joinedload(EntityMention.extraction_run).joinedload(ExtractionRun.chapter_version).joinedload(ChapterVersion.chapter)
        )
        .filter(Entity.id == entity_id, Entity.world_id == world.id)
        .first()
    )
    if not ent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")

    aliases = [a.alias for a in ent.aliases]
    facts_out = []
    for f in ent.facts:
        active_v = current_version(f)
        v_resp = None
        if active_v:
            v_resp = FactVersionResponse(
                id=active_v.id,
                fact_id=active_v.fact_id,
                chapter_id=active_v.chapter_id,
                value=active_v.value,
                status=active_v.status,
                confidence=active_v.confidence,
                created_at=active_v.created_at
            )
        facts_out.append(FactResponse(
            id=f.id,
            property_name=f.property_name,
            created_at=f.created_at,
            current_version=v_resp
        ))

    rels_out = []
    seen_rel_ids = set()
    all_rels = list(ent.outgoing_relationships) + list(ent.incoming_relationships)
    for r in all_rels:
        if r.id in seen_rel_ids:
            continue
        seen_rel_ids.add(r.id)
        active_v = next((v for v in r.versions if v.status == "ACTIVE"), None)
        if not active_v and r.versions:
            active_v = r.versions[0]

        is_outgoing = (r.source_entity_id == ent.id)
        other_ent = r.target_entity if is_outgoing else r.source_entity
        if not other_ent:
            continue

        rel_type = active_v.relationship_type if active_v else "RELATED_TO"
        rels_out.append({
            "id": r.id,
            "targetId": other_ent.id,
            "targetName": other_ent.canonical_name,
            "targetType": other_ent.entity_type,
            "relation": rel_type,
            "direction": "outgoing" if is_outgoing else "incoming",
            "isNegative": rel_type in ("ENEMY_OF", "RIVAL_OF", "OPPOSES", "HATES", "DEAD_AT_HANDS_OF"),
            "chapter_id": active_v.chapter_id if active_v else None,
            "chapter_number": active_v.chapter.chapter_number if (active_v and active_v.chapter) else None
        })

    events_out = [
        {
            "id": ep.event.id,
            "type": ep.event.event_type,
            "role": ep.role,
            "description": ep.event.description,
            "chapter_id": ep.event.chapter_id,
            "chapter_number": ep.event.chapter.chapter_number if ep.event.chapter else None
        }
        for ep in ent.event_participants if ep.event
    ]

    appearance_chapters = {}
    for ep in ent.event_participants:
        if ep.event and ep.event.chapter:
            ch = ep.event.chapter
            appearance_chapters[ch.id] = {
                "id": ch.id,
                "chapter_number": ch.chapter_number,
                "title": ch.title or f"Chapter {ch.chapter_number}",
                "reason": f"Event: {ep.event.event_type}"
            }
    for f in ent.facts:
        for fv in f.versions:
            if fv.chapter:
                ch = fv.chapter
                if ch.id not in appearance_chapters:
                    appearance_chapters[ch.id] = {
                        "id": ch.id,
                        "chapter_number": ch.chapter_number,
                        "title": ch.title or f"Chapter {ch.chapter_number}",
                        "reason": f"Fact: {f.property_name}"
                    }
    for r in all_rels:
        for rv in r.versions:
            if rv.chapter:
                ch = rv.chapter
                if ch.id not in appearance_chapters:
                    appearance_chapters[ch.id] = {
                        "id": ch.id,
                        "chapter_number": ch.chapter_number,
                        "title": ch.title or f"Chapter {ch.chapter_number}",
                        "reason": f"Relationship: {rv.relationship_type}"
                    }
    for m in ent.mentions:
        if m.extraction_run and m.extraction_run.chapter_version and m.extraction_run.chapter_version.chapter:
            ch = m.extraction_run.chapter_version.chapter
            if ch.id not in appearance_chapters:
                appearance_chapters[ch.id] = {
                    "id": ch.id,
                    "chapter_number": ch.chapter_number,
                    "title": ch.title or f"Chapter {ch.chapter_number}",
                    "reason": f"Mentioned in text"
                }

    appearances_out = sorted(
        list(appearance_chapters.values()),
        key=lambda x: x.get("chapter_number") or 0
    )

    return EntityDetailResponse(
        id=ent.id,
        world_id=ent.world_id,
        entity_type=ent.entity_type,
        canonical_name=ent.canonical_name,
        source_extraction_id=ent.source_extraction_id,
        provenance=ent.provenance,
        aliases=aliases,
        facts=facts_out,
        created_at=ent.created_at,
        updated_at=ent.updated_at,
        relationships=rels_out,
        events=events_out,
        appearances=appearances_out
    )

@router.put("/{world_id}/entities/{entity_id}", response_model=EntityResponse)
def update_entity(
    world_id: str,
    entity_id: str,
    ent_in: EntityUpdate,
    world: World = Depends(get_current_user_world),
    db: Session = Depends(get_db)
):
    service = EntityService(db)
    ent = service.get_entity(entity_id)
    if not ent or ent.world_id != world.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")

    if ent_in.canonical_name is not None:
        existing = service.entity_repo.get_by_canonical(world.id, ent_in.canonical_name)
        if existing and existing.id != ent.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Another entity with this canonical name already exists in this world."
            )

    updated = service.update_entity(
        entity_id=entity_id,
        canonical_name=ent_in.canonical_name,
        entity_type=ent_in.entity_type,
        attributes=ent_in.attributes
    )
    return entity_to_response(updated)

@router.delete("/{world_id}/entities/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entity(
    world_id: str,
    entity_id: str,
    world: World = Depends(get_current_user_world),
    db: Session = Depends(get_db)
):
    service = EntityService(db)
    ent = service.get_entity(entity_id)
    if not ent or ent.world_id != world.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")
    service.delete_entity(entity_id)
    return None

@router.post("/{world_id}/entities/{entity_id}/aliases", response_model=EntityResponse, status_code=status.HTTP_201_CREATED)
def add_alias(
    world_id: str,
    entity_id: str,
    req: AliasCreateRequest,
    world: World = Depends(get_current_user_world),
    db: Session = Depends(get_db)
):
    service = EntityService(db)
    updated = service.add_alias(world.id, entity_id, req.alias)
    return entity_to_response(updated)

@router.delete("/{world_id}/entities/{entity_id}/aliases", status_code=status.HTTP_204_NO_CONTENT)
def remove_alias(
    world_id: str,
    entity_id: str,
    alias: str = Query(..., min_length=1),
    world: World = Depends(get_current_user_world),
    db: Session = Depends(get_db)
):
    service = EntityService(db)
    service.remove_alias(world.id, entity_id, alias)
    return None

@router.post("/{world_id}/entities/{entity_id}/facts", status_code=status.HTTP_201_CREATED)
def add_fact_to_entity(
    world_id: str,
    entity_id: str,
    fact_in: FactCreate,
    world: World = Depends(get_current_user_world),
    db: Session = Depends(get_db)
):
    service = EntityService(db)
    ent = service.get_entity(entity_id)
    if not ent or ent.world_id != world.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")
    fact_ver = service.add_fact(
        entity_id=entity_id,
        property_name=fact_in.property_name,
        value=fact_in.value,
        confidence=fact_in.confidence
    )
    return {"id": fact_ver.id, "property": fact_in.property_name, "value": fact_ver.value, "status": fact_ver.status}

@router.delete("/{world_id}/entities/{entity_id}/facts/{fact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_fact(
    world_id: str,
    entity_id: str,
    fact_id: str,
    world: World = Depends(get_current_user_world),
    db: Session = Depends(get_db)
):
    service = EntityService(db)
    ent = service.get_entity(entity_id)
    if not ent or ent.world_id != world.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")

    fact = service.fact_repo.get(fact_id)
    if not fact or fact.entity_id != entity_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fact not found")

    service.delete_fact(fact_id)
    return None
