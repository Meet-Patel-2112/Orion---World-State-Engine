from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict


class RelationshipVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    relationship_id: str
    relationship_type: str
    status: str
    chapter_id: Optional[str] = None
    chapter_number: Optional[int] = None
    confidence: float = 1.0
    created_at: datetime


class RelationshipResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    world_id: str
    source_entity_id: str
    source_name: str
    target_entity_id: str
    target_name: str
    created_at: datetime
    current_version: Optional[RelationshipVersionResponse] = None
    versions: List[RelationshipVersionResponse] = []


class RelationshipCreateRequest(BaseModel):
    source_entity_id: str
    target_entity_id: str
    relationship_type: str
    chapter_id: Optional[str] = None
    confidence: Optional[float] = 1.0


class RelationshipUpdateRequest(BaseModel):
    relationship_type: str
    chapter_id: Optional[str] = None
    confidence: Optional[float] = 1.0
