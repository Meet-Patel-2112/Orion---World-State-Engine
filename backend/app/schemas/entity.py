from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field, field_validator

class AliasResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    alias: str
    confidence: float

class FactVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    fact_id: str
    chapter_id: Optional[str] = None
    value: Any = None
    status: str
    confidence: float
    created_at: datetime

class FactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    property_name: str
    created_at: datetime
    current_version: Optional[FactVersionResponse] = None

class FactCreate(BaseModel):
    property_name: str = Field(..., min_length=1, max_length=255)
    value: Any
    confidence: float = 1.0

    @field_validator("property_name")
    @classmethod
    def validate_prop(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("property_name cannot be empty.")
        return s

class EntityBase(BaseModel):
    entity_type: str = "character"
    canonical_name: str = Field(..., min_length=1, max_length=255)

    @field_validator("canonical_name")
    @classmethod
    def validate_canonical(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("canonical_name cannot be empty or whitespace only.")
        return s

class EntityCreate(EntityBase):
    aliases: List[str] = []
    attributes: Dict[str, Any] = {}

class EntityUpdate(BaseModel):
    canonical_name: Optional[str] = Field(None, min_length=1, max_length=255)
    entity_type: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None

    @field_validator("canonical_name")
    @classmethod
    def validate_update_canonical(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            s = v.strip()
            if not s:
                raise ValueError("canonical_name cannot be empty or whitespace only.")
            return s
        return v

class EntityResponse(EntityBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    world_id: str
    source_extraction_id: Optional[str] = None
    provenance: Optional[str] = None
    aliases: List[str] = []
    facts: List[FactResponse] = []
    created_at: datetime
    updated_at: datetime

class EntityDetailResponse(EntityResponse):
    relationships: List[Dict[str, Any]] = []
    events: List[Dict[str, Any]] = []
    appearances: List[Dict[str, Any]] = []

class MergeEntitiesRequest(BaseModel):
    source_id: str
    target_id: str

class BulkDeleteEntitiesRequest(BaseModel):
    entity_ids: List[str] = Field(..., min_length=1)

class AliasCreateRequest(BaseModel):
    alias: str = Field(..., min_length=1, max_length=255)

    @field_validator("alias")
    @classmethod
    def validate_alias(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("alias cannot be empty.")
        return s

