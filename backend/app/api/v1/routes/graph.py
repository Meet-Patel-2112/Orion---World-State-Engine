from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user_world
from app.models.world import World
from app.schemas.graph import GraphResponse
from app.services.graph_service import GraphService

# Owner: Person B (feature/graph-timeline). Contract: docs/api.md §8 and §16.
router = APIRouter()


@router.get("/{world_id}/graph", response_model=GraphResponse, status_code=status.HTTP_200_OK)
def get_world_graph(
    world_id: str,
    as_of_chapter: Optional[int] = Query(None, ge=1, description="Show state as of the end of chapter N"),
    world: World = Depends(get_current_user_world),
    db: Session = Depends(get_db),
):
    """
    Get the world knowledge graph (§8.1), optionally time-sliced as of chapter N (§16).
    """
    service = GraphService(db)
    return service.get_world_graph(world.id, as_of_chapter=as_of_chapter)
