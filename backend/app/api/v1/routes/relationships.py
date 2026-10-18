from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db, get_current_user_world
from app.core.constants import RelationshipStatus
from app.models.world import World
from app.models.entity import Entity
from app.models.chapter import Chapter
from app.models.manuscript import Manuscript
from app.models.relationship import Relationship, RelationshipVersion
from app.models.contradiction import Contradiction
from app.schemas.relationship import (
    RelationshipCreateRequest,
    RelationshipUpdateRequest,
    RelationshipResponse,
    RelationshipVersionResponse,
)
from app.services.consistency_service import ConsistencyService

router = APIRouter()


def _format_relationship(rel: Relationship) -> RelationshipResponse:
    source_name = rel.source_entity.canonical_name if rel.source_entity else "Unknown"
    target_name = rel.target_entity.canonical_name if rel.target_entity else "Unknown"

    versions_out: List[RelationshipVersionResponse] = []
    # rel.versions is ordered newest first by default in Relationship model
    for v in rel.versions:
        ch_num = v.chapter.chapter_number if v.chapter else None
        versions_out.append(RelationshipVersionResponse(
            id=v.id,
            relationship_id=v.relationship_id,
            relationship_type=v.relationship_type,
            status=v.status,
            chapter_id=v.chapter_id,
            chapter_number=ch_num,
            confidence=v.confidence,
            created_at=v.created_at,
        ))

    active_v = next((v for v in versions_out if v.status == RelationshipStatus.ACTIVE.value), None)

    return RelationshipResponse(
        id=rel.id,
        world_id=rel.world_id,
        source_entity_id=rel.source_entity_id,
        source_name=source_name,
        target_entity_id=rel.target_entity_id,
        target_name=target_name,
        created_at=rel.created_at,
        current_version=active_v,
        versions=versions_out,
    )


def _relationship_query(db: Session, world_id: str):
    return db.query(Relationship).options(
        joinedload(Relationship.versions).joinedload(RelationshipVersion.chapter),
        joinedload(Relationship.source_entity),
        joinedload(Relationship.target_entity)
    ).filter(Relationship.world_id == world_id)


def _validate_chapter(db: Session, world_id: str, chapter_id: Optional[str]):
    if not chapter_id:
        return
    chapter = db.query(Chapter).join(
        Manuscript, Chapter.manuscript_id == Manuscript.id
    ).filter(
        Chapter.id == chapter_id,
        Manuscript.world_id == world_id
    ).first()
    if not chapter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chapter not found in this world"
        )


@router.get("/{world_id}/relationships", response_model=List[RelationshipResponse])
def list_relationships(
    world_id: str,
    entity_id: Optional[str] = Query(None),
    world: World = Depends(get_current_user_world),
    db: Session = Depends(get_db)
):
    query = _relationship_query(db, world.id)
    if entity_id:
        query = query.filter(
            (Relationship.source_entity_id == entity_id) |
            (Relationship.target_entity_id == entity_id)
        )
    relationships = query.order_by(Relationship.created_at.asc()).all()
    return [_format_relationship(r) for r in relationships]


@router.get("/{world_id}/relationships/{relationship_id}", response_model=RelationshipResponse)
def get_relationship(
    world_id: str,
    relationship_id: str,
    world: World = Depends(get_current_user_world),
    db: Session = Depends(get_db)
):
    rel = _relationship_query(db, world.id).filter(Relationship.id == relationship_id).first()
    if not rel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Relationship not found"
        )
    return _format_relationship(rel)


@router.post("/{world_id}/relationships", response_model=RelationshipResponse)
def create_relationship(
    world_id: str,
    rel_in: RelationshipCreateRequest,
    response: Response,
    world: World = Depends(get_current_user_world),
    db: Session = Depends(get_db)
):
    if rel_in.source_entity_id == rel_in.target_entity_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="source_entity_id and target_entity_id cannot be the same"
        )

    source_ent = db.query(Entity).filter(
        Entity.id == rel_in.source_entity_id,
        Entity.world_id == world.id
    ).first()
    if not source_ent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source entity not found in this world"
        )

    target_ent = db.query(Entity).filter(
        Entity.id == rel_in.target_entity_id,
        Entity.world_id == world.id
    ).first()
    if not target_ent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target entity not found in this world"
        )

    _validate_chapter(db, world.id, rel_in.chapter_id)

    rel_type = rel_in.relationship_type.strip()
    if not rel_type:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="relationship_type cannot be empty"
        )

    # Check for existing directed pair
    rel = db.query(Relationship).filter(
        Relationship.world_id == world.id,
        Relationship.source_entity_id == source_ent.id,
        Relationship.target_entity_id == target_ent.id
    ).first()

    is_new_pair = False
    if rel:
        active_ver = next((v for v in rel.versions if v.status == RelationshipStatus.ACTIVE.value), None)
        if active_ver and active_ver.relationship_type.strip().upper() == rel_type.upper():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Relationship between these entities is already {rel_type}"
            )
    else:
        is_new_pair = True
        rel = Relationship(
            world_id=world.id,
            source_entity_id=source_ent.id,
            target_entity_id=target_ent.id
        )
        db.add(rel)
        db.flush()
        active_ver = None

    # Append new version
    confidence = rel_in.confidence if rel_in.confidence is not None else 1.0
    new_ver = RelationshipVersion(
        relationship_id=rel.id,
        relationship_type=rel_type,
        chapter_id=rel_in.chapter_id,
        status=RelationshipStatus.ACTIVE.value,
        confidence=confidence
    )
    db.add(new_ver)
    db.flush()

    # Consistency evaluation (P1)
    consistency_service = ConsistencyService(db)
    result = consistency_service.evaluate_relationship_version(
        world.id, rel, new_ver, source_ent, target_ent
    )
    if result.findings:
        new_ver.status = RelationshipStatus.CONTRADICTED.value
    elif active_ver and active_ver.relationship_type.strip().upper() != rel_type.upper():
        active_ver.status = RelationshipStatus.SUPERSEDED.value

    db.commit()

    rel = _relationship_query(db, world.id).filter(Relationship.id == rel.id).first()
    response.status_code = status.HTTP_201_CREATED if is_new_pair else status.HTTP_200_OK
    return _format_relationship(rel)


@router.put("/{world_id}/relationships/{relationship_id}", response_model=RelationshipResponse)
def update_relationship(
    world_id: str,
    relationship_id: str,
    rel_in: RelationshipUpdateRequest,
    world: World = Depends(get_current_user_world),
    db: Session = Depends(get_db)
):
    rel = _relationship_query(db, world.id).filter(Relationship.id == relationship_id).first()
    if not rel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Relationship not found"
        )

    _validate_chapter(db, world.id, rel_in.chapter_id)

    rel_type = rel_in.relationship_type.strip()
    if not rel_type:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="relationship_type cannot be empty"
        )

    active_ver = next((v for v in rel.versions if v.status == RelationshipStatus.ACTIVE.value), None)
    if active_ver and active_ver.relationship_type.strip().upper() == rel_type.upper():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Relationship is already {rel_type}"
        )

    confidence = rel_in.confidence if rel_in.confidence is not None else 1.0
    new_ver = RelationshipVersion(
        relationship_id=rel.id,
        relationship_type=rel_type,
        chapter_id=rel_in.chapter_id,
        status=RelationshipStatus.ACTIVE.value,
        confidence=confidence
    )
    db.add(new_ver)
    db.flush()

    # Consistency evaluation (P1)
    consistency_service = ConsistencyService(db)
    result = consistency_service.evaluate_relationship_version(
        world.id, rel, new_ver, rel.source_entity, rel.target_entity
    )
    if result.findings:
        new_ver.status = RelationshipStatus.CONTRADICTED.value
    elif active_ver and active_ver.relationship_type.strip().upper() != rel_type.upper():
        active_ver.status = RelationshipStatus.SUPERSEDED.value

    db.commit()

    rel = _relationship_query(db, world.id).filter(Relationship.id == rel.id).first()
    return _format_relationship(rel)


@router.delete("/{world_id}/relationships/{relationship_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_relationship(
    world_id: str,
    relationship_id: str,
    world: World = Depends(get_current_user_world),
    db: Session = Depends(get_db)
):
    rel = db.query(Relationship).filter(
        Relationship.id == relationship_id,
        Relationship.world_id == world.id
    ).first()
    if not rel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Relationship not found"
        )

    # Delete orphan contradictions referencing any version of this relationship
    version_ids = [v.id for v in rel.versions]
    if version_ids:
        db.query(Contradiction).filter(
            (Contradiction.old_relationship_version_id.in_(version_ids)) |
            (Contradiction.new_relationship_version_id.in_(version_ids))
        ).delete(synchronize_session=False)

    db.delete(rel)
    db.commit()
    return None
