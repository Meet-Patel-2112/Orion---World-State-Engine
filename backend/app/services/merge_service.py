from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.constants import FactStatus
from app.models.contradiction import Contradiction
from app.models.entity import Entity, EntityAlias, EntityMention
from app.models.event import EventParticipant
from app.models.fact import Fact, FactVersion, FactMention
from app.models.processing_job import ProcessingJob
from app.models.relationship import Relationship, RelationshipVersion


class MergeService:
    def __init__(self, db: Session):
        self.db = db

    def merge_entities(self, world_id: str, source_id: str, target_id: str) -> Entity:
        """
        Merges source_id into target_id in one database transaction according to §13.1 and RULES.md 3.4.
        The target survives; the source is deleted.
        """
        # Precondition 1: source != target
        if source_id == target_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot merge an entity into itself."
            )

        # Precondition 2: both entities exist and belong to world_id
        source = self.db.query(Entity).filter(Entity.id == source_id, Entity.world_id == world_id).first()
        target = self.db.query(Entity).filter(Entity.id == target_id, Entity.world_id == world_id).first()
        if not source or not target:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Entity not found in this world."
            )

        # Precondition 3: no processing job is queued or processing
        active_job = self.db.query(ProcessingJob).filter(
            ProcessingJob.world_id == world_id,
            ProcessingJob.status.in_(["queued", "processing"])
        ).first()
        if active_job:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot merge entities while a job is queued or processing."
            )

        try:
            # Rule 1: Move source's canonical name and aliases onto target, deduplicated case-insensitively,
            # skipping any that equal target's canonical name.
            target_canon_lower = target.canonical_name.strip().lower()
            existing_target_aliases_lower = {a.alias.strip().lower() for a in target.aliases}

            candidates = [source.canonical_name] + [a.alias for a in source.aliases]
            for cand in candidates:
                c_clean = cand.strip()
                if not c_clean:
                    continue
                c_lower = c_clean.lower()
                if c_lower != target_canon_lower and c_lower not in existing_target_aliases_lower:
                    new_alias = EntityAlias(
                        entity_id=target.id,
                        alias=c_clean,
                        confidence=1.0
                    )
                    target.aliases.append(new_alias)
                    existing_target_aliases_lower.add(c_lower)

            # Rule 2: Repoint mentions to target
            for m in list(source.mentions):
                source.mentions.remove(m)
                target.mentions.append(m)
                m.entity = target
                m.entity_id = target.id

            self.db.query(FactMention).filter(
                FactMention.entity_id == source.id
            ).update({FactMention.entity_id: target.id}, synchronize_session=False)

            # Rule 3: Fold facts with the same property_name
            target_facts = {f.property_name.strip().lower(): f for f in target.facts}
            for source_fact in list(source.facts):
                prop_key = source_fact.property_name.strip().lower()
                source.facts.remove(source_fact)
                if prop_key in target_facts:
                    target_fact = target_facts[prop_key]
                    target_active = next((v for v in target_fact.versions if v.status == FactStatus.ACTIVE.value), None)
                    source_active = next((v for v in source_fact.versions if v.status == FactStatus.ACTIVE.value), None)

                    if target_active and source_active:
                        source_active.status = FactStatus.SUPERSEDED.value

                    for v in list(source_fact.versions):
                        source_fact.versions.remove(v)
                        target_fact.versions.append(v)
                        v.fact = target_fact
                        v.fact_id = target_fact.id

                    self.db.delete(source_fact)
                else:
                    target.facts.append(source_fact)
                    source_fact.entity = target
                    source_fact.entity_id = target.id
                    target_facts[prop_key] = source_fact

            # Rule 4: Event participations
            for ep in list(source.event_participants):
                existing_p = self.db.query(EventParticipant).filter(
                    EventParticipant.event_id == ep.event_id,
                    EventParticipant.entity_id == target.id
                ).first()
                source.event_participants.remove(ep)
                if existing_p:
                    self.db.delete(ep)
                else:
                    target.event_participants.append(ep)
                    ep.entity = target
                    ep.entity_id = target.id

            # Rule 5: Relationships & self-loops
            # 5a. Prune self-loops (source <-> target, target <-> source, source <-> source, target <-> target)
            self_loops = self.db.query(Relationship).filter(
                ((Relationship.source_entity_id == source.id) & (Relationship.target_entity_id == target.id)) |
                ((Relationship.source_entity_id == target.id) & (Relationship.target_entity_id == source.id)) |
                ((Relationship.source_entity_id == source.id) & (Relationship.target_entity_id == source.id)) |
                ((Relationship.source_entity_id == target.id) & (Relationship.target_entity_id == target.id))
            ).all()

            for rel in self_loops:
                rv_ids = [v.id for v in rel.versions]
                if rv_ids:
                    loop_contradictions = self.db.query(Contradiction).filter(
                        (Contradiction.old_relationship_version_id.in_(rv_ids)) |
                        (Contradiction.new_relationship_version_id.in_(rv_ids))
                    ).all()
                    for c in loop_contradictions:
                        self.db.delete(c)
                if rel in source.outgoing_relationships:
                    source.outgoing_relationships.remove(rel)
                if rel in source.incoming_relationships:
                    source.incoming_relationships.remove(rel)
                if rel in target.outgoing_relationships:
                    target.outgoing_relationships.remove(rel)
                if rel in target.incoming_relationships:
                    target.incoming_relationships.remove(rel)
                self.db.delete(rel)

            # 5b. Outgoing relationships from source
            for rel in list(source.outgoing_relationships):
                existing_rel = self.db.query(Relationship).filter(
                    Relationship.source_entity_id == target.id,
                    Relationship.target_entity_id == rel.target_entity_id
                ).first()
                source.outgoing_relationships.remove(rel)
                if existing_rel:
                    target_active_v = next((v for v in existing_rel.versions if v.status == "ACTIVE"), None)
                    for rv in list(rel.versions):
                        rel.versions.remove(rv)
                        if rv.status == "ACTIVE" and target_active_v:
                            rv.status = "SUPERSEDED"
                        existing_rel.versions.append(rv)
                        rv.relationship = existing_rel
                        rv.relationship_id = existing_rel.id
                    self.db.delete(rel)
                else:
                    target.outgoing_relationships.append(rel)
                    rel.source_entity = target
                    rel.source_entity_id = target.id

            # 5c. Incoming relationships to source
            for rel in list(source.incoming_relationships):
                existing_rel = self.db.query(Relationship).filter(
                    Relationship.source_entity_id == rel.source_entity_id,
                    Relationship.target_entity_id == target.id
                ).first()
                source.incoming_relationships.remove(rel)
                if existing_rel:
                    target_active_v = next((v for v in existing_rel.versions if v.status == "ACTIVE"), None)
                    for rv in list(rel.versions):
                        rel.versions.remove(rv)
                        if rv.status == "ACTIVE" and target_active_v:
                            rv.status = "SUPERSEDED"
                        existing_rel.versions.append(rv)
                        rv.relationship = existing_rel
                        rv.relationship_id = existing_rel.id
                    self.db.delete(rel)
                else:
                    target.incoming_relationships.append(rel)
                    rel.target_entity = target
                    rel.target_entity_id = target.id

            # Rule 6: Delete source entity & purge orphan contradictions
            self.db.delete(source)

            orphan_contradictions = self.db.query(Contradiction).filter(
                Contradiction.world_id == world_id,
                Contradiction.old_fact_version_id.is_(None),
                Contradiction.new_fact_version_id.is_(None),
                Contradiction.old_relationship_version_id.is_(None),
                Contradiction.new_relationship_version_id.is_(None),
                Contradiction.event_id_a.is_(None),
                Contradiction.event_id_b.is_(None)
            ).all()
            for oc in orphan_contradictions:
                self.db.delete(oc)

            self.db.commit()
            self.db.expire_all()

            # Refresh and return target entity
            return self.db.query(Entity).filter(Entity.id == target.id).first()
        except HTTPException:
            self.db.rollback()
            raise
        except Exception:
            self.db.rollback()
            raise

