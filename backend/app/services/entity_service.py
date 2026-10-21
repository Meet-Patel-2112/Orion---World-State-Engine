from typing import List, Optional, Dict, Any
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.constants import FactStatus
from app.models.contradiction import Contradiction
from app.models.entity import Entity, EntityAlias
from app.models.fact import Fact, FactVersion
from app.repositories.entity_repo import EntityRepository
from app.repositories.fact_repo import FactRepository

class EntityService:
    def __init__(self, db: Session):
        self.db = db
        self.entity_repo = EntityRepository(db)
        self.fact_repo = FactRepository(db)

    def list_entities(self, world_id: str, entity_type: Optional[str] = None) -> List[Entity]:
        return self.entity_repo.list_by_world(world_id, entity_type)

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        return self.entity_repo.get_entity_with_facts(entity_id)

    def create_entity(
        self,
        world_id: str,
        canonical_name: str,
        entity_type: str = "character",
        aliases: List[str] = [],
        attributes: Dict[str, Any] = {}
    ) -> Entity:
        entity = self.entity_repo.create({
            "world_id": world_id,
            "canonical_name": canonical_name.strip(),
            "entity_type": entity_type.lower()
        })

        for alias in aliases:
            if alias.strip():
                self.entity_repo.add_alias(entity.id, alias.strip())

        for prop_name, val in attributes.items():
            fact = self.fact_repo.get_or_create_fact(entity.id, prop_name)
            self.fact_repo.add_version(fact.id, value=val)

        return self.get_entity(entity.id) or entity

    def update_entity(
        self,
        entity_id: str,
        canonical_name: Optional[str] = None,
        entity_type: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None
    ) -> Optional[Entity]:
        entity = self.entity_repo.get(entity_id)
        if not entity:
            return None

        update_data = {}
        if canonical_name is not None:
            update_data["canonical_name"] = canonical_name.strip()
        if entity_type is not None:
            update_data["entity_type"] = entity_type.lower()

        if update_data:
            self.entity_repo.update(entity, update_data)

        if attributes:
            for prop_name, val in attributes.items():
                fact = self.fact_repo.get_or_create_fact(entity.id, prop_name, commit=False)
                previous_active = [version for version in fact.versions if version.status == FactStatus.ACTIVE.value]
                self.fact_repo.add_version(fact.id, value=val, commit=False)
                for version in previous_active:
                    version.status = FactStatus.SUPERSEDED.value
            self.db.commit()

        return self.get_entity(entity_id)

    def delete_entity(self, entity_id: str) -> Optional[Entity]:
        self._cleanup_orphan_contradictions_for_entity(entity_id)
        return self.entity_repo.delete(entity_id)

    def bulk_delete_entities(self, world_id: str, entity_ids: List[str]) -> None:
        """
        Bulk delete entities in one transaction. All-or-nothing: if any ID isn't in world_id,
        nothing is deleted (HTTP 404). Orphan contradictions are deleted.
        """
        deduped_ids = list(dict.fromkeys(entity_ids))
        if not deduped_ids:
            return

        entities = self.db.query(Entity).filter(
            Entity.id.in_(deduped_ids),
            Entity.world_id == world_id
        ).all()

        if len(entities) != len(deduped_ids):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="One or more entities not found in this world."
            )

        for ent in entities:
            self._cleanup_orphan_contradictions_for_entity(ent.id)
            self.db.delete(ent)

        self.db.commit()

    def add_alias(self, world_id: str, entity_id: str, alias: str) -> Entity:
        """
        Add alias to entity. Rejects if matches canonical name (case-insensitive)
        or entity already has this alias (HTTP 400). Entity must be in world_id (HTTP 404).
        """
        entity = self.get_entity(entity_id)
        if not entity or entity.world_id != world_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Entity not found."
            )

        alias_clean = alias.strip()
        if not alias_clean:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Alias cannot be empty."
            )

        if alias_clean.lower() == entity.canonical_name.strip().lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Alias cannot match canonical name."
            )

        for a in entity.aliases:
            if a.alias.strip().lower() == alias_clean.lower():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Alias already exists for this entity."
                )

        new_alias = EntityAlias(
            entity_id=entity.id,
            alias=alias_clean,
            confidence=1.0
        )
        self.db.add(new_alias)
        self.db.commit()
        return self.get_entity(entity_id)

    def remove_alias(self, world_id: str, entity_id: str, alias: str) -> None:
        """
        Remove alias from entity. Matching is case-insensitive after trimming.
        Raises HTTP 404 if entity not found or alias not found.
        """
        entity = self.get_entity(entity_id)
        if not entity or entity.world_id != world_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Entity not found."
            )

        alias_clean = alias.strip().lower()
        match = next((a for a in entity.aliases if a.alias.strip().lower() == alias_clean), None)
        if not match:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Alias not found for this entity."
            )

        self.db.delete(match)
        self.db.commit()

    def add_fact(
        self,
        entity_id: str,
        property_name: str,
        value: Any,
        confidence: float = 1.0
    ) -> FactVersion:
        fact = self.fact_repo.get_or_create_fact(entity_id, property_name)

        # Retrieve any current ACTIVE version before adding the new version
        previous_active = self.fact_repo.get_active_version(fact.id)

        # Add the new version (status ACTIVE initially)
        new_version = self.fact_repo.add_version(
            fact_id=fact.id,
            value=value,
            confidence=confidence,
            status=FactStatus.ACTIVE.value,
            commit=False
        )
        self.db.flush()

        # Phase 2: call consistency check on manual fact addition.
        # If a contradiction is detected:
        # - mark the new version CONTRADICTED
        # - retain the previous active version as ACTIVE
        # If no contradiction is detected:
        # - retire previous active version to SUPERSEDED
        entity = self.entity_repo.get(entity_id)
        if entity:
            try:
                from app.services.consistency_service import ConsistencyService
                consistency = ConsistencyService(self.db)
                result = consistency.evaluate_fact_version(entity, fact, new_version)
                if result.findings:
                    new_version.status = FactStatus.CONTRADICTED.value
                    # previous_active stays ACTIVE
                else:
                    if previous_active and previous_active.id != new_version.id:
                        previous_active.status = FactStatus.SUPERSEDED.value
            except Exception:
                if previous_active and previous_active.id != new_version.id:
                    previous_active.status = FactStatus.SUPERSEDED.value
        else:
            if previous_active and previous_active.id != new_version.id:
                previous_active.status = FactStatus.SUPERSEDED.value

        self.db.commit()
        self.db.refresh(new_version)
        return new_version

    def delete_fact(self, fact_id: str) -> bool:
        fact = self.fact_repo.get(fact_id)
        if fact:
            self._cleanup_orphan_contradictions_for_fact(fact)
            self.db.delete(fact)
            self.db.commit()
            return True
        return False

    def _cleanup_orphan_contradictions_for_fact(self, fact: Fact) -> None:
        """Delete contradictions that reference any version of this fact, since they will become orphans."""
        version_ids = [v.id for v in fact.versions]
        if not version_ids:
            return
        contradictions = self.db.query(Contradiction).filter(
            (Contradiction.old_fact_version_id.in_(version_ids)) |
            (Contradiction.new_fact_version_id.in_(version_ids))
        ).all()
        for c in contradictions:
            self.db.delete(c)

    def _cleanup_orphan_contradictions_for_entity(self, entity_id: str) -> None:
        """Delete contradictions that reference any fact version or relationship version of this entity,
        since cascade-deleting the entity will set the contradiction FKs to NULL, leaving orphan rows."""
        entity = self.entity_repo.get_entity_with_facts(entity_id)
        if not entity:
            return

        # Gather all fact version IDs
        fact_version_ids = [v.id for f in entity.facts for v in f.versions]

        # Gather all relationship version IDs (both outgoing and incoming)
        rel_version_ids = []
        for rel in entity.outgoing_relationships:
            rel_version_ids.extend(v.id for v in rel.versions)
        for rel in entity.incoming_relationships:
            rel_version_ids.extend(v.id for v in rel.versions)

        conditions = []
        if fact_version_ids:
            conditions.append(Contradiction.old_fact_version_id.in_(fact_version_ids))
            conditions.append(Contradiction.new_fact_version_id.in_(fact_version_ids))
        if rel_version_ids:
            conditions.append(Contradiction.old_relationship_version_id.in_(rel_version_ids))
            conditions.append(Contradiction.new_relationship_version_id.in_(rel_version_ids))

        if conditions:
            from sqlalchemy import or_
            contradictions = self.db.query(Contradiction).filter(or_(*conditions)).all()
            for c in contradictions:
                self.db.delete(c)


