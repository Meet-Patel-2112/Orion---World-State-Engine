from datetime import datetime
from typing import List, Any
from sqlalchemy.orm import Session

from app.models.event import Event
from app.repositories.event_repo import EventRepository
from app.schemas.timeline import TimelineEventResponse, TimelineResponse, TimelineParticipant


def event_sort_key(ev: Any):
    """
    Ordering rule per docs/api.md §15:
    by chapter_number, then sequence_index, then start_position, then created_at.
    Events with no chapter come first, and a null in any of these fields sorts after non-null values.
    """
    if hasattr(ev, "chapter_number") and getattr(ev, "chapter_number") is not None:
        ch_num = ev.chapter_number
    elif hasattr(ev, "chapter") and ev.chapter is not None:
        ch_num = ev.chapter.chapter_number
    elif isinstance(ev, dict):
        ch_num = ev.get("chapter_number")
    else:
        ch_num = None

    seq_idx = getattr(ev, "sequence_index", None) if not isinstance(ev, dict) else ev.get("sequence_index")
    start_pos = getattr(ev, "start_position", None) if not isinstance(ev, dict) else ev.get("start_position")
    created_at = getattr(ev, "created_at", None) if not isinstance(ev, dict) else ev.get("created_at")
    ev_id = getattr(ev, "id", "") if not isinstance(ev, dict) else ev.get("id", "")

    ch_key = (0, 0) if ch_num is None else (1, ch_num)
    seq_key = (1, 0) if seq_idx is None else (0, seq_idx)
    pos_key = (1, 0) if start_pos is None else (0, start_pos)
    created_key = created_at if created_at is not None else datetime.min

    return (ch_key, seq_key, pos_key, created_key, ev_id)


class TimelineService:
    def __init__(self, db: Session):
        self.db = db
        self.event_repo = EventRepository(db)

    def get_world_timeline(self, world_id: str) -> TimelineResponse:
        events = self.event_repo.list_by_world(world_id)
        sorted_events = sorted(events, key=event_sort_key)

        responses: List[TimelineEventResponse] = []
        for ev in sorted_events:
            participants = []
            for p in ev.participants:
                ent_name = p.entity.canonical_name if p.entity else None
                participants.append(TimelineParticipant(
                    entity_id=p.entity_id,
                    entity_name=ent_name,
                    role=p.role
                ))

            ch_num = ev.chapter.chapter_number if ev.chapter else None

            responses.append(TimelineEventResponse(
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
                participants=participants
            ))

        return TimelineResponse(events=responses, total=len(responses))

