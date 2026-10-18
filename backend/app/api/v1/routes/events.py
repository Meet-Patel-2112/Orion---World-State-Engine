from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db, get_current_user_world
from app.models.world import World
from app.models.manuscript import Manuscript
from app.models.chapter import Chapter
from app.models.entity import Entity
from app.models.event import Event, EventParticipant
from app.models.contradiction import Contradiction
from app.schemas.timeline import (
    TimelineEventResponse,
    TimelineResponse,
    TimelineParticipant,
    EventCreateRequest,
    EventUpdateRequest,
    EventReorderRequest,
)

# Step 0 stub now fully implemented. Owner: Person B (feature/graph-timeline).
# Contract: docs/api.md §15.
router = APIRouter()


def validate_chapter(db: Session, world_id: str, chapter_id: Optional[str]) -> Optional[Chapter]:
    if chapter_id is None:
        return None
    chapter = (
        db.query(Chapter)
        .join(Manuscript, Chapter.manuscript_id == Manuscript.id)
        .filter(Chapter.id == chapter_id, Manuscript.world_id == world_id)
        .first()
    )
    if not chapter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chapter not found in this world",
        )
    return chapter


def to_event_response(ev: Event) -> TimelineEventResponse:
    participants = []
    for p in ev.participants:
        ent_name = p.entity.canonical_name if p.entity else None
        participants.append(
            TimelineParticipant(
                entity_id=p.entity_id,
                entity_name=ent_name,
                role=p.role,
            )
        )
    ch_num = ev.chapter.chapter_number if ev.chapter else None
    return TimelineEventResponse(
        id=ev.id,
        world_id=ev.world_id,
        chapter_id=ev.chapter_id,
        chapter_number=ch_num,
        event_type=ev.event_type,
        description=ev.description,
        start_position=ev.start_position,
        end_position=ev.end_position,
        sequence_index=ev.sequence_index,
        confidence=ev.confidence,
        created_at=ev.created_at,
        participants=participants,
    )


@router.post(
    "/{world_id}/events",
    response_model=TimelineEventResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_event(
    world_id: str,
    payload: EventCreateRequest,
    world: World = Depends(get_current_user_world),
    db: Session = Depends(get_db),
):
    """
    Create a new event in the world (§15.1).
    """
    if not payload.description or not payload.description.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Description is required and cannot be empty",
        )

    # Validate participants for duplicates
    seen_entity_ids = set()
    for p in payload.participants:
        if p.entity_id in seen_entity_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Duplicate entity_id in participants: {p.entity_id}",
            )
        seen_entity_ids.add(p.entity_id)

    # Validate participant entities belong to this world
    if seen_entity_ids:
        existing_entities = (
            db.query(Entity)
            .filter(Entity.world_id == world.id, Entity.id.in_(seen_entity_ids))
            .all()
        )
        if len(existing_entities) != len(seen_entity_ids):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="One or more participant entities not found in this world",
            )

    # Validate chapter belongs to this world
    validate_chapter(db, world.id, payload.chapter_id)

    event = Event(
        world_id=world.id,
        description=payload.description.strip(),
        event_type=payload.event_type or "EVENT",
        chapter_id=payload.chapter_id,
        sequence_index=payload.sequence_index,
        confidence=1.0,
    )
    db.add(event)
    db.flush()

    for p in payload.participants:
        part = EventParticipant(
            event_id=event.id,
            entity_id=p.entity_id,
            role=p.role or "PARTICIPANT",
        )
        db.add(part)

    db.commit()

    reloaded = (
        db.query(Event)
        .options(
            joinedload(Event.participants).joinedload(EventParticipant.entity),
            joinedload(Event.chapter),
        )
        .filter(Event.id == event.id)
        .first()
    )
    return to_event_response(reloaded)


# NOTE: Declare /events/reorder before /events/{event_id} per docs/api.md §15.5
@router.patch(
    "/{world_id}/events/reorder",
    response_model=TimelineResponse,
    status_code=status.HTTP_200_OK,
)
def reorder_events(
    world_id: str,
    payload: EventReorderRequest,
    world: World = Depends(get_current_user_world),
    db: Session = Depends(get_db),
):
    """
    Reorder events within a chapter (or unassigned events) (§15.5).
    Sets sequence_index to 0..n-1 in the order given.
    """
    validate_chapter(db, world.id, payload.chapter_id)

    # Check for duplicates in payload
    if len(payload.event_ids) != len(set(payload.event_ids)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="event_ids contains duplicate IDs",
        )

    # Query current events for this chapter/unassigned in this world
    query = db.query(Event).filter(Event.world_id == world.id)
    if payload.chapter_id is not None:
        query = query.filter(Event.chapter_id == payload.chapter_id)
    else:
        query = query.filter(Event.chapter_id.is_(None))
    current_events = query.all()
    current_event_ids = {e.id for e in current_events}

    # Must list every event in that chapter exactly once
    if set(payload.event_ids) != current_event_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="event_ids must contain all events in the chapter with no missing or extra events",
        )

    event_map = {e.id: e for e in current_events}
    for idx, eid in enumerate(payload.event_ids):
        event_map[eid].sequence_index = idx

    db.commit()

    # Reload reordered events with relations
    updated_events = (
        db.query(Event)
        .options(
            joinedload(Event.participants).joinedload(EventParticipant.entity),
            joinedload(Event.chapter),
        )
        .filter(Event.id.in_(payload.event_ids))
        .all()
    ) if payload.event_ids else []

    updated_map = {e.id: e for e in updated_events}
    ordered_responses = [to_event_response(updated_map[eid]) for eid in payload.event_ids]
    return TimelineResponse(events=ordered_responses, total=len(ordered_responses))


@router.get(
    "/{world_id}/events/{event_id}",
    response_model=TimelineEventResponse,
    status_code=status.HTTP_200_OK,
)
def get_event(
    world_id: str,
    event_id: str,
    world: World = Depends(get_current_user_world),
    db: Session = Depends(get_db),
):
    """
    Get a single event by ID (§15.2).
    """
    event = (
        db.query(Event)
        .options(
            joinedload(Event.participants).joinedload(EventParticipant.entity),
            joinedload(Event.chapter),
        )
        .filter(Event.id == event_id, Event.world_id == world.id)
        .first()
    )
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )
    return to_event_response(event)


@router.put(
    "/{world_id}/events/{event_id}",
    response_model=TimelineEventResponse,
    status_code=status.HTTP_200_OK,
)
def update_event(
    world_id: str,
    event_id: str,
    payload: EventUpdateRequest,
    world: World = Depends(get_current_user_world),
    db: Session = Depends(get_db),
):
    """
    Update an event in place (§15.3).
    Resets sequence_index to null if chapter_id changes.
    """
    event = (
        db.query(Event)
        .filter(Event.id == event_id, Event.world_id == world.id)
        .first()
    )
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )

    # Description validation
    if payload.description is not None:
        if not payload.description.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Description cannot be empty",
            )
        event.description = payload.description.strip()

    if payload.event_type is not None:
        event.event_type = payload.event_type

    # Chapter update check
    if "chapter_id" in payload.model_fields_set:
        validate_chapter(db, world.id, payload.chapter_id)
        if event.chapter_id != payload.chapter_id:
            event.chapter_id = payload.chapter_id
            event.sequence_index = None  # Reset sequence_index when chapter changes

    # Participants update check
    if payload.participants is not None:
        seen_entity_ids = set()
        for p in payload.participants:
            if p.entity_id in seen_entity_ids:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Duplicate entity_id in participants: {p.entity_id}",
                )
            seen_entity_ids.add(p.entity_id)

        if seen_entity_ids:
            existing_entities = (
                db.query(Entity)
                .filter(Entity.world_id == world.id, Entity.id.in_(seen_entity_ids))
                .all()
            )
            if len(existing_entities) != len(seen_entity_ids):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="One or more participant entities not found in this world",
                )

        # Replace participants
        db.query(EventParticipant).filter(EventParticipant.event_id == event.id).delete()
        for p in payload.participants:
            part = EventParticipant(
                event_id=event.id,
                entity_id=p.entity_id,
                role=p.role or "PARTICIPANT",
            )
            db.add(part)

    db.commit()

    reloaded = (
        db.query(Event)
        .options(
            joinedload(Event.participants).joinedload(EventParticipant.entity),
            joinedload(Event.chapter),
        )
        .filter(Event.id == event.id)
        .first()
    )
    return to_event_response(reloaded)


@router.delete(
    "/{world_id}/events/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_event(
    world_id: str,
    event_id: str,
    world: World = Depends(get_current_user_world),
    db: Session = Depends(get_db),
):
    """
    Delete an event (§15.4).
    Participants are removed by cascade, and orphan contradictions are deleted.
    """
    event = (
        db.query(Event)
        .filter(Event.id == event_id, Event.world_id == world.id)
        .first()
    )
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )

    # Delete orphan contradictions referencing this event
    db.query(Contradiction).filter(
        (Contradiction.event_id_a == event.id) | (Contradiction.event_id_b == event.id)
    ).delete(synchronize_session=False)

    db.delete(event)
    db.commit()
    return None
