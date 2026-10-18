from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict

class TimelineParticipant(BaseModel):
    entity_id: str
    entity_name: Optional[str] = None
    role: str

class TimelineEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    world_id: str
    chapter_id: Optional[str] = None
    chapter_number: Optional[int] = None
    event_type: str
    description: str
    start_position: Optional[int] = None
    end_position: Optional[int] = None
    sequence_index: Optional[int] = None
    confidence: float
    created_at: datetime
    participants: List[TimelineParticipant] = []

class TimelineResponse(BaseModel):
    events: List[TimelineEventResponse] = []
    total: int = 0

class EventParticipantInput(BaseModel):
    entity_id: str
    role: str = "PARTICIPANT"

class EventCreateRequest(BaseModel):
    description: str
    event_type: str = "EVENT"
    chapter_id: Optional[str] = None
    sequence_index: Optional[int] = None
    participants: List[EventParticipantInput] = []

class EventUpdateRequest(BaseModel):
    description: Optional[str] = None
    event_type: Optional[str] = None
    chapter_id: Optional[str] = None
    participants: Optional[List[EventParticipantInput]] = None

class EventReorderRequest(BaseModel):
    chapter_id: Optional[str] = None
    event_ids: List[str]

EventResponse = TimelineEventResponse

