from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user_world
from app.models.world import World
from app.schemas.contradiction import ContradictionResponse, ContradictionResolveRequest
from app.services.consistency_service import ConsistencyService
from app.services.contradiction_sources import sources_for

router = APIRouter()

@router.get("/{world_id}/contradictions", response_model=List[ContradictionResponse])
def list_contradictions(
    world_id: str,
    status_filter: Optional[str] = Query(None, alias="status"),
    world: World = Depends(get_current_user_world),
    db: Session = Depends(get_db)
):
    service = ConsistencyService(db)
    contradictions = service.list_contradictions(world.id, status=status_filter)
    return [_with_sources(db, c) for c in contradictions]


def _with_sources(db: Session, con) -> ContradictionResponse:
    """The row plus where each side of it is in the text, so the author can jump to it."""
    return ContradictionResponse.model_validate({**ContradictionResponse.model_validate(con).model_dump(),
                                                 "sources": sources_for(db, con)})

@router.post("/{world_id}/contradictions/{contradiction_id}/resolve", response_model=ContradictionResponse)
def resolve_contradiction(
    world_id: str,
    contradiction_id: str,
    resolve_in: ContradictionResolveRequest,
    world: World = Depends(get_current_user_world),
    db: Session = Depends(get_db)
):
    service = ConsistencyService(db)
    con = service.contradiction_repo.get(contradiction_id)
    if not con or con.world_id != world.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contradiction not found")

    try:
        resolved = service.resolve_contradiction(
            contradiction_id=contradiction_id,
            status=resolve_in.status,
            preferred_fact_version_id=resolve_in.preferred_fact_version_id,
            preferred_relationship_version_id=resolve_in.preferred_relationship_version_id
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return _with_sources(db, resolved)
