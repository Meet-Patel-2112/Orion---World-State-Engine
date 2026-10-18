from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict

class ContradictionSource(BaseModel):
    """One side of a contradiction, located in its chapter's current text (app/services/contradiction_sources.py)."""
    side: str                       # old / new (facts, relationships) or a / b (events)
    label: str                      # "Chapter 3 · line 12", or "Added manually"
    value: str
    chapter_id: Optional[str] = None
    chapter_number: Optional[int] = None
    chapter_title: Optional[str] = None
    manuscript_id: Optional[str] = None
    line: Optional[int] = None
    start: Optional[int] = None     # span to highlight, offsets in the chapter's current text
    end: Optional[int] = None
    snippet: Optional[str] = None   # the sentence
    highlight: Optional[str] = None


class ContradictionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    world_id: str
    contradiction_type: str
    explanation: str
    confidence: float
    status: str
    old_fact_version_id: Optional[str] = None
    new_fact_version_id: Optional[str] = None
    old_relationship_version_id: Optional[str] = None
    new_relationship_version_id: Optional[str] = None
    event_id_a: Optional[str] = None
    event_id_b: Optional[str] = None
    created_at: datetime
    sources: List[ContradictionSource] = []
    # No `metadata` field: on a SQLAlchemy model that name is the table registry (Base.metadata), not a column,
    # so from_attributes read MetaData() and every list with a contradiction failed validation (HTTP 500).

class ContradictionResolveRequest(BaseModel):
    status: str = "RESOLVED"
    resolution_notes: Optional[str] = None
    preferred_fact_version_id: Optional[str] = None
    preferred_relationship_version_id: Optional[str] = None
