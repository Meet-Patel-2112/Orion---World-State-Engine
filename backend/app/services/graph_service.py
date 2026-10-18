from collections import defaultdict
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session, joinedload

from app.models.entity import Entity, EntityMention
from app.models.fact import Fact, FactVersion
from app.models.relationship import Relationship, RelationshipVersion
from app.models.contradiction import Contradiction
from app.models.extraction_run import ExtractionRun
from app.models.chapter_version import ChapterVersion
from app.models.chapter import Chapter
from app.models.event import EventParticipant, Event
from app.repositories.entity_repo import EntityRepository
from app.repositories.relationship_repo import RelationshipRepository
from app.schemas.graph import GraphNode, GraphEdge, GraphResponse

# Owner: Person B (feature/graph-timeline). Contract: docs/api.md §8 and §16.


class GraphService:
    def __init__(self, db: Session):
        self.db = db
        self.entity_repo = EntityRepository(db)
        self.relationship_repo = RelationshipRepository(db)

    def get_world_graph(self, world_id: str, as_of_chapter: Optional[int] = None) -> GraphResponse:
        """
        Generate knowledge graph (§8.1), optionally time-sliced as of chapter N (§16).
        """
        if as_of_chapter is None:
            return self._get_latest_graph(world_id)
        return self._get_timeslice_graph(world_id, as_of_chapter)

    def _get_latest_graph(self, world_id: str) -> GraphResponse:
        entities = (
            self.db.query(Entity)
            .options(joinedload(Entity.facts).joinedload(Fact.versions))
            .filter(Entity.world_id == world_id)
            .order_by(Entity.canonical_name.asc())
            .all()
        )
        relationships = self.relationship_repo.list_by_world(world_id)

        node_degrees = defaultdict(int)
        edges: List[GraphEdge] = []

        for rel in relationships:
            active_ver = self.relationship_repo.get_active_version(rel.id)
            rel_type = active_ver.relationship_type if active_ver else "RELATED_TO"
            conf = active_ver.confidence if active_ver else 1.0
            status = active_ver.status if active_ver else "ACTIVE"
            ch_id = active_ver.chapter_id if active_ver else None

            node_degrees[rel.source_entity_id] += 1
            node_degrees[rel.target_entity_id] += 1

            edges.append(
                GraphEdge(
                    id=rel.id,
                    source=rel.source_entity_id,
                    target=rel.target_entity_id,
                    type=rel_type,
                    confidence=conf,
                    status=status,
                    chapter_id=ch_id,
                )
            )

        nodes: List[GraphNode] = []
        for ent in entities:
            properties = {}
            for fact in ent.facts:
                latest_ver = fact.versions[0] if fact.versions else None
                if latest_ver and latest_ver.status == "ACTIVE":
                    properties[fact.property_name] = latest_ver.value

            nodes.append(
                GraphNode(
                    id=ent.id,
                    label=ent.canonical_name,
                    type=ent.entity_type,
                    properties=properties,
                    degree=node_degrees[ent.id],
                )
            )

        return GraphResponse(nodes=nodes, edges=edges)

    def _get_timeslice_graph(self, world_id: str, as_of_chapter: int) -> GraphResponse:
        N = as_of_chapter

        # 1. Contradictions query to determine excluded versions
        detected_contradictions = (
            self.db.query(Contradiction)
            .filter(Contradiction.world_id == world_id, Contradiction.status == "DETECTED")
            .all()
        )
        detected_rel_ver_ids = set()
        detected_fact_ver_ids = set()
        for c in detected_contradictions:
            if c.old_relationship_version_id:
                detected_rel_ver_ids.add(c.old_relationship_version_id)
            if c.new_relationship_version_id:
                detected_rel_ver_ids.add(c.new_relationship_version_id)
            if c.old_fact_version_id:
                detected_fact_ver_ids.add(c.old_fact_version_id)
            if c.new_fact_version_id:
                detected_fact_ver_ids.add(c.new_fact_version_id)

        # Resolved contradictions: exclude author rejected versions
        # (the new-side version of a RESOLVED contradiction that ended up SUPERSEDED)
        resolved_contradictions = (
            self.db.query(Contradiction)
            .filter(Contradiction.world_id == world_id, Contradiction.status == "RESOLVED")
            .all()
        )
        rejected_new_rel_ver_ids = {
            c.new_relationship_version_id for c in resolved_contradictions if c.new_relationship_version_id
        }
        rejected_new_fact_ver_ids = {
            c.new_fact_version_id for c in resolved_contradictions if c.new_fact_version_id
        }

        # 2. Query all relationships with versions and chapters
        relationships = (
            self.db.query(Relationship)
            .options(joinedload(Relationship.versions).joinedload(RelationshipVersion.chapter))
            .filter(Relationship.world_id == world_id)
            .all()
        )

        edges: List[GraphEdge] = []
        node_degrees = defaultdict(int)
        entities_with_edges = set()

        for rel in relationships:
            qualifying_versions = []
            for v in rel.versions:
                ch_num = v.chapter.chapter_number if v.chapter else None
                # Must be <= N (or no chapter)
                if ch_num is not None and ch_num > N:
                    continue
                # Exclude CONTRADICTED in unresolved contradiction
                if v.status == "CONTRADICTED" and v.id in detected_rel_ver_ids:
                    continue
                # Exclude rejected new-side version of resolved contradiction
                if v.status == "SUPERSEDED" and v.id in rejected_new_rel_ver_ids:
                    continue
                qualifying_versions.append(v)

            if not qualifying_versions:
                continue

            # Latest qualifying version wins: sort by (ch_num or 0, created_at)
            winning_version = max(
                qualifying_versions,
                key=lambda ver: (ver.chapter.chapter_number if ver.chapter else 0, ver.created_at)
            )

            node_degrees[rel.source_entity_id] += 1
            node_degrees[rel.target_entity_id] += 1
            entities_with_edges.add(rel.source_entity_id)
            entities_with_edges.add(rel.target_entity_id)

            edges.append(
                GraphEdge(
                    id=rel.id,
                    source=rel.source_entity_id,
                    target=rel.target_entity_id,
                    type=winning_version.relationship_type,
                    confidence=winning_version.confidence,
                    status=winning_version.status,
                    chapter_id=winning_version.chapter_id,
                )
            )

        # 3. Query entities with facts, mentions, and event participations
        entities = (
            self.db.query(Entity)
            .options(
                joinedload(Entity.facts).joinedload(Fact.versions).joinedload(FactVersion.chapter),
                joinedload(Entity.mentions)
                .joinedload(EntityMention.extraction_run)
                .joinedload(ExtractionRun.chapter_version)
                .joinedload(ChapterVersion.chapter),
                joinedload(Entity.event_participants).joinedload(EventParticipant.event),
            )
            .filter(Entity.world_id == world_id)
            .order_by(Entity.canonical_name.asc())
            .all()
        )

        # Also collect all relationship versions touching each entity to check if entity has chapter-tagged data
        rel_chapters_by_entity = defaultdict(set)
        for rel in relationships:
            for v in rel.versions:
                if v.chapter_id is not None:
                    rel_chapters_by_entity[rel.source_entity_id].add(v.chapter_id)
                    rel_chapters_by_entity[rel.target_entity_id].add(v.chapter_id)

        nodes: List[GraphNode] = []
        for ent in entities:
            # Fact properties as of chapter N
            properties = {}
            for fact in ent.facts:
                qualifying_fvers = []
                for fv in fact.versions:
                    ch_num = fv.chapter.chapter_number if fv.chapter else None
                    if ch_num is not None and ch_num > N:
                        continue
                    if fv.status == "CONTRADICTED" and fv.id in detected_fact_ver_ids:
                        continue
                    if fv.status == "SUPERSEDED" and fv.id in rejected_new_fact_ver_ids:
                        continue
                    qualifying_fvers.append(fv)

                if qualifying_fvers:
                    winning_fv = max(
                        qualifying_fvers,
                        key=lambda ver: (ver.chapter.chapter_number if ver.chapter else 0, ver.created_at)
                    )
                    properties[fact.property_name] = winning_fv.value

            # Check node inclusion criteria (§16):
            # 1. Has as-of edge
            has_as_of_edge = ent.id in entities_with_edges

            # 2. Has as-of fact
            has_as_of_fact = len(properties) > 0

            # 3. Has mention in chapter <= N
            has_mention_in_n = False
            for m in ent.mentions:
                if (
                    m.extraction_run
                    and m.extraction_run.chapter_version
                    and m.extraction_run.chapter_version.chapter
                ):
                    if m.extraction_run.chapter_version.chapter.chapter_number <= N:
                        has_mention_in_n = True
                        break

            # 4. No chapter-tagged data at all (manually created entity)
            has_any_chapter_data = False
            if rel_chapters_by_entity[ent.id]:
                has_any_chapter_data = True
            if not has_any_chapter_data:
                for f in ent.facts:
                    if any(fv.chapter_id is not None for fv in f.versions):
                        has_any_chapter_data = True
                        break
            if not has_any_chapter_data:
                for m in ent.mentions:
                    if m.extraction_run and m.extraction_run.chapter_version_id:
                        has_any_chapter_data = True
                        break
            if not has_any_chapter_data:
                for ep in ent.event_participants:
                    if ep.event and ep.event.chapter_id is not None:
                        has_any_chapter_data = True
                        break

            is_manual_untagged = not has_any_chapter_data

            if has_as_of_edge or has_as_of_fact or has_mention_in_n or is_manual_untagged:
                nodes.append(
                    GraphNode(
                        id=ent.id,
                        label=ent.canonical_name,
                        type=ent.entity_type,
                        properties=properties,
                        degree=node_degrees[ent.id],
                    )
                )

        return GraphResponse(nodes=nodes, edges=edges)
