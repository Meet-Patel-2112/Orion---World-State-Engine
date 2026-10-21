import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db, get_current_user
from app.core.database import Base
from app.main import app
from app.models.chapter import Chapter
from app.models.chapter_version import ChapterVersion
from app.models.contradiction import Contradiction
from app.models.entity import Entity, EntityAlias, EntityMention
from app.models.event import Event, EventParticipant
from app.models.extraction_run import ExtractionRun
from app.models.fact import Fact, FactVersion, FactMention
from app.models.processing_job import ProcessingJob
from app.models.relationship import Relationship, RelationshipVersion
from app.models.user import User
from app.models.world import World
from app.services.merge_service import MergeService
from scripts import seed_demo_world as seed_script
from scripts.seed_demo_world import sid


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()

    # Create dummy user and world
    user = User(id="user-1", email="author@example.com", password_hash="dummy")
    world = World(id="world-1", user_id=user.id, name="Test World")
    session.add(user)
    session.add(world)
    session.commit()

    yield session
    session.close()


def test_merge_rejects_self_merge(db_session):
    service = MergeService(db_session)
    with pytest.raises(HTTPException) as exc_info:
        service.merge_entities("world-1", "ent-1", "ent-1")
    assert exc_info.value.status_code == 400
    assert "itself" in exc_info.value.detail


def test_merge_rejects_cross_world_or_nonexistent(db_session):
    service = MergeService(db_session)
    e1 = Entity(id="e1", world_id="world-1", canonical_name="E1")
    db_session.add(e1)
    db_session.commit()

    # Missing target
    with pytest.raises(HTTPException) as exc_info:
        service.merge_entities("world-1", "e1", "nonexistent")
    assert exc_info.value.status_code == 404

    # Other world
    w2 = World(id="world-2", user_id="user-1", name="Other World")
    e2 = Entity(id="e2", world_id="world-2", canonical_name="E2")
    db_session.add(w2)
    db_session.add(e2)
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        service.merge_entities("world-1", "e1", "e2")
    assert exc_info.value.status_code == 404


def test_merge_rejects_while_job_is_active(db_session):
    service = MergeService(db_session)
    e1 = Entity(id="e1", world_id="world-1", canonical_name="E1")
    e2 = Entity(id="e2", world_id="world-1", canonical_name="E2")
    job = ProcessingJob(id="job-1", world_id="world-1", status="queued")
    db_session.add_all([e1, e2, job])
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        service.merge_entities("world-1", "e1", "e2")
    assert exc_info.value.status_code == 400
    assert "job is queued or processing" in exc_info.value.detail


def test_merge_rule_1_aliases_deduplicated(db_session):
    service = MergeService(db_session)
    target = Entity(id="target-1", world_id="world-1", canonical_name="Lady Seraphina")
    t_alias = EntityAlias(entity_id=target.id, alias="Sera")
    source = Entity(id="source-1", world_id="world-1", canonical_name="The Black Rose")
    s_alias1 = EntityAlias(entity_id=source.id, alias="sera")  # duplicate of target alias
    s_alias2 = EntityAlias(entity_id=source.id, alias="lady seraphina")  # matches target canonical
    s_alias3 = EntityAlias(entity_id=source.id, alias="Whisper")
    db_session.add_all([target, t_alias, source, s_alias1, s_alias2, s_alias3])
    db_session.commit()

    survivor = service.merge_entities("world-1", source.id, target.id)
    aliases = {a.alias for a in survivor.aliases}

    # Should have Sera (original), The Black Rose (source canonical), Whisper (source alias)
    # Should NOT have duplicate 'sera' or 'lady seraphina'
    assert aliases == {"Sera", "The Black Rose", "Whisper"}


def test_merge_rule_2_mentions_repointed(db_session):
    service = MergeService(db_session)
    target = Entity(id="target-2", world_id="world-1", canonical_name="Valen")
    source = Entity(id="source-2", world_id="world-1", canonical_name="Sir Valen")
    em = EntityMention(id="em-1", entity_id=source.id, surface_text="Valen")
    fm = FactMention(id="fm-1", entity_id=source.id, property_name="status", value="alive")
    db_session.add_all([target, source, em, fm])
    db_session.commit()

    service.merge_entities("world-1", source.id, target.id)

    db_session.refresh(em)
    db_session.refresh(fm)
    assert em.entity_id == target.id
    assert fm.entity_id == target.id


def test_merge_rule_3_facts_folding_and_status(db_session):
    service = MergeService(db_session)
    target = Entity(id="target-3", world_id="world-1", canonical_name="Target")
    tf_role = Fact(id="tf-1", entity_id=target.id, property_name="role")
    tf_role_v = FactVersion(id="tfv-1", fact_id=tf_role.id, value="captain", status="ACTIVE")

    source = Entity(id="source-3", world_id="world-1", canonical_name="Source")
    sf_role = Fact(id="sf-1", entity_id=source.id, property_name="role")
    sf_role_v = FactVersion(id="sfv-1", fact_id=sf_role.id, value="first mate", status="ACTIVE")
    sf_title = Fact(id="sf-2", entity_id=source.id, property_name="title")
    sf_title_v = FactVersion(id="sfv-2", fact_id=sf_title.id, value="Sir", status="ACTIVE")

    db_session.add_all([target, tf_role, tf_role_v, source, sf_role, sf_role_v, sf_title, sf_title_v])
    db_session.commit()

    survivor = service.merge_entities("world-1", source.id, target.id)

    # Check folded facts
    facts = {f.property_name: f for f in survivor.facts}
    assert "role" in facts
    assert "title" in facts

    # Title moved unchanged
    assert facts["title"].id == sf_title.id
    assert facts["title"].entity_id == target.id

    # Role folded: target role stays ACTIVE, source role becomes SUPERSEDED
    role_versions = {v.value: v.status for v in facts["role"].versions}
    assert role_versions["captain"] == "ACTIVE"
    assert role_versions["first mate"] == "SUPERSEDED"

    # Source fact sf-1 deleted
    assert db_session.get(Fact, sf_role.id) is None


def test_merge_rule_4_event_participants_deduplicated(db_session):
    service = MergeService(db_session)
    target = Entity(id="target-4", world_id="world-1", canonical_name="Target")
    source = Entity(id="source-4", world_id="world-1", canonical_name="Source")
    ev1 = Event(id="ev-1", world_id="world-1", description="Joint Battle")
    ev2 = Event(id="ev-2", world_id="world-1", description="Solo Recon")

    # Joint: both participate
    ep_t1 = EventParticipant(id="ep-1", event_id=ev1.id, entity_id=target.id, role="DEFENDER")
    ep_s1 = EventParticipant(id="ep-2", event_id=ev1.id, entity_id=source.id, role="SCOUT")

    # Solo: only source participates
    ep_s2 = EventParticipant(id="ep-3", event_id=ev2.id, entity_id=source.id, role="SCOUT")

    db_session.add_all([target, source, ev1, ev2, ep_t1, ep_s1, ep_s2])
    db_session.commit()

    service.merge_entities("world-1", source.id, target.id)

    # ev1 should only have 1 participant (target), ep_s1 was dropped
    assert db_session.get(EventParticipant, ep_s1.id) is None
    assert db_session.query(EventParticipant).filter(EventParticipant.event_id == ev1.id).count() == 1

    # ev2 should have target as participant (repointed from source)
    assert db_session.get(EventParticipant, ep_s2.id) is not None
    db_session.refresh(ep_s2)
    assert ep_s2.entity_id == target.id


def test_merge_rule_5_relationships_and_self_loops(db_session):
    service = MergeService(db_session)
    target = Entity(id="target-5", world_id="world-1", canonical_name="Target")
    source = Entity(id="source-5", world_id="world-1", canonical_name="Source")
    other = Entity(id="other-5", world_id="world-1", canonical_name="Other")

    # Self-loop: source -> target
    rel_loop = Relationship(id="rel-loop", world_id="world-1", source_entity_id=source.id, target_entity_id=target.id)
    rv_loop = RelationshipVersion(id="rv-loop", relationship_id=rel_loop.id, relationship_type="RIVAL_OF")
    # Contradiction on this loop
    c_loop = Contradiction(id="c-loop", world_id="world-1", contradiction_type="RELATIONSHIP", old_relationship_version_id=rv_loop.id, explanation="Loop conflict")

    # Target -> Other exists
    rel_t_o = Relationship(id="rel-t-o", world_id="world-1", source_entity_id=target.id, target_entity_id=other.id)
    rv_t_o = RelationshipVersion(id="rv-t-o", relationship_id=rel_t_o.id, relationship_type="ALLY_OF", status="ACTIVE")

    # Source -> Other exists (needs folding)
    rel_s_o = Relationship(id="rel-s-o", world_id="world-1", source_entity_id=source.id, target_entity_id=other.id)
    rv_s_o = RelationshipVersion(id="rv-s-o", relationship_id=rel_s_o.id, relationship_type="FRIEND_OF", status="ACTIVE")

    # Other -> Source exists (needs repointing since Other -> Target does not exist)
    rel_o_s = Relationship(id="rel-o-s", world_id="world-1", source_entity_id=other.id, target_entity_id=source.id)
    rv_o_s = RelationshipVersion(id="rv-o-s", relationship_id=rel_o_s.id, relationship_type="MENTOR_OF", status="ACTIVE")

    db_session.add_all([
        target, source, other, rel_loop, rv_loop, c_loop,
        rel_t_o, rv_t_o, rel_s_o, rv_s_o, rel_o_s, rv_o_s
    ])
    db_session.commit()

    service.merge_entities("world-1", source.id, target.id)

    # Self loop deleted
    assert db_session.get(Relationship, rel_loop.id) is None
    # Contradiction on self loop deleted
    assert db_session.get(Contradiction, c_loop.id) is None

    # rel_s_o folded into rel_t_o
    assert db_session.get(Relationship, rel_s_o.id) is None
    db_session.refresh(rel_t_o)
    db_session.refresh(rv_t_o)
    db_session.refresh(rv_s_o)
    assert rv_s_o.relationship_id == rel_t_o.id
    assert rv_t_o.status == "ACTIVE"
    assert rv_s_o.status == "SUPERSEDED"

    # rel_o_s repointed to target
    db_session.refresh(rel_o_s)
    assert rel_o_s.target_entity_id == target.id


def test_merge_rule_6_source_deleted_and_target_returned(db_session):
    service = MergeService(db_session)
    target = Entity(id="target-6", world_id="world-1", canonical_name="Target")
    source = Entity(id="source-6", world_id="world-1", canonical_name="Source")
    db_session.add_all([target, source])
    db_session.commit()

    survivor = service.merge_entities("world-1", source.id, target.id)
    assert survivor.id == target.id
    assert db_session.get(Entity, source.id) is None


def test_merge_api_endpoint(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: db_session.query(User).filter(User.id == "user-1").first()

    try:
        client = TestClient(app)
        target = Entity(id="ent-t", world_id="world-1", canonical_name="Lord Commander")
        source = Entity(id="ent-s", world_id="world-1", canonical_name="The Commander")
        db_session.add_all([target, source])
        db_session.commit()

        resp = client.post(
            "/api/v1/worlds/world-1/entities/merge",
            json={"source_id": source.id, "target_id": target.id},
            headers={"Authorization": "Bearer dummy"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == target.id
        assert data["canonical_name"] == "Lord Commander"
        assert "The Commander" in data["aliases"]
    finally:
        app.dependency_overrides.clear()


def test_merge_on_seeded_demo_world(tmp_path):
    url = f"sqlite:///{(tmp_path / 'demo_merge.db').as_posix()}"
    args = ["--database-url", url, "--storage-dir", str(tmp_path / "storage")]
    assert seed_script.main(args) == 0

    db = seed_script.make_session(url)
    captain_id = sid("entity/captain")
    ilse_id = sid("entity/ilse")
    world_id = seed_script.WORLD_ID

    service = MergeService(db)
    survivor = service.merge_entities(world_id, ilse_id, captain_id)

    assert survivor.id == captain_id
    assert db.get(Entity, ilse_id) is None

    # Check aliases: Ilse's name and alias added to captain
    alias_names = {a.alias for a in survivor.aliases}
    assert "Ilse" in alias_names or "Recruiter Ilse" in alias_names

    # Check folded facts: role has harbour captain (ACTIVE) and recruiter (SUPERSEDED)
    role_fact = next(f for f in survivor.facts if f.property_name == "role")
    statuses = {v.value: v.status for v in role_fact.versions}
    assert statuses["harbour captain"] == "ACTIVE"
    assert statuses["recruiter"] == "SUPERSEDED"

    # Check event participants: ev_sail only has 1 participant for captain
    sail = db.get(Event, sid("event/ev_sail"))
    captain_participants = [p for p in sail.participants if p.entity_id == captain_id]
    assert len(captain_participants) == 1

    # Check relationships: self loop captain-ilse is gone
    pairs = {(r.source_entity_id, r.target_entity_id) for r in db.query(Relationship).all()}
    assert (captain_id, ilse_id) not in pairs
    assert (ilse_id, captain_id) not in pairs

    db.close()


# ---------------------------------------------------------------------------
# Phase 2 Tests: Fact Versioning Fix & Contradiction Choice Support
# ---------------------------------------------------------------------------

def test_manual_fact_supersedes_previous_active(db_session):
    from app.services.entity_service import EntityService

    service = EntityService(db_session)
    entity = Entity(id="ent-fact-1", world_id="world-1", canonical_name="Arthur")
    db_session.add(entity)
    db_session.commit()

    # First version: role = "knight"
    v1 = service.add_fact(entity.id, "role", "knight")
    assert v1.status == "ACTIVE"
    assert v1.value == "knight"

    # Second version: role = "lord"
    v2 = service.add_fact(entity.id, "role", "lord")
    assert v2.status == "ACTIVE"
    assert v2.value == "lord"

    # Refresh v1 and verify it is SUPERSEDED
    db_session.refresh(v1)
    assert v1.status == "SUPERSEDED"

    # Verify exactly one ACTIVE version exists for this fact
    fact = service.fact_repo.get_or_create_fact(entity.id, "role")
    active_versions = [v for v in fact.versions if v.status == "ACTIVE"]
    assert len(active_versions) == 1
    assert active_versions[0].id == v2.id


def test_manual_fact_contradiction_detected(db_session):
    from app.services.entity_service import EntityService

    service = EntityService(db_session)
    entity = Entity(id="ent-fact-2", world_id="world-1", canonical_name="Merlin")
    db_session.add(entity)
    db_session.commit()

    # 'origin' is an IMMUTABLE_PROPERTY in vocabulary.py
    v1 = service.add_fact(entity.id, "origin", "Camelot")
    assert v1.status == "ACTIVE"

    # Attempting to add a different origin should trigger ImmutableFactRule
    v2 = service.add_fact(entity.id, "origin", "Avalon")
    assert v2.status == "CONTRADICTED"

    # Earlier version should remain ACTIVE
    db_session.refresh(v1)
    assert v1.status == "ACTIVE"

    # A contradiction record should be created in the database
    con = db_session.query(Contradiction).filter(
        Contradiction.old_fact_version_id == v1.id,
        Contradiction.new_fact_version_id == v2.id
    ).first()
    assert con is not None
    assert con.status == "DETECTED"
    assert "[IMMUTABLE_FACT]" in con.explanation


def test_delete_fact_cleans_orphan_contradictions(db_session):
    from app.services.entity_service import EntityService

    service = EntityService(db_session)
    entity = Entity(id="ent-fact-3", world_id="world-1", canonical_name="Gwen")
    db_session.add(entity)
    db_session.commit()

    v1 = service.add_fact(entity.id, "origin", "Camelot")
    v2 = service.add_fact(entity.id, "origin", "Avalon")

    fact = service.fact_repo.get_or_create_fact(entity.id, "origin")
    con = db_session.query(Contradiction).filter(
        Contradiction.old_fact_version_id == v1.id,
        Contradiction.new_fact_version_id == v2.id
    ).first()
    assert con is not None

    # Deleting the fact should delete the referencing contradiction
    success = service.delete_fact(fact.id)
    assert success is True

    db_session.expire_all()
    assert db_session.get(Contradiction, con.id) is None


def test_delete_entity_cleans_orphan_contradictions(db_session):
    from app.services.entity_service import EntityService

    service = EntityService(db_session)
    entity = Entity(id="ent-fact-4", world_id="world-1", canonical_name="Lancelot")
    db_session.add(entity)
    db_session.commit()

    v1 = service.add_fact(entity.id, "origin", "Joyous Gard")
    v2 = service.add_fact(entity.id, "origin", "Benwick")

    con = db_session.query(Contradiction).filter(
        Contradiction.old_fact_version_id == v1.id,
        Contradiction.new_fact_version_id == v2.id
    ).first()
    assert con is not None

    # Deleting the entity should clean up orphan contradictions
    deleted = service.delete_entity(entity.id)
    assert deleted is not None

    db_session.expire_all()
    assert db_session.get(Contradiction, con.id) is None


def test_resolve_contradiction_choice_keep_new(db_session):
    from app.services.entity_service import EntityService

    service = EntityService(db_session)
    entity = Entity(id="ent-res-1", world_id="world-1", canonical_name="Kay")
    db_session.add(entity)
    db_session.commit()

    v1 = service.add_fact(entity.id, "origin", "London")
    v2 = service.add_fact(entity.id, "origin", "York")

    con = db_session.query(Contradiction).filter(
        Contradiction.old_fact_version_id == v1.id,
        Contradiction.new_fact_version_id == v2.id
    ).first()
    assert con is not None

    # Test via API endpoint
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: db_session.query(User).filter(User.id == "user-1").first()

    try:
        client = TestClient(app)
        # Author picks "keep new": preferred_fact_version_id = v2.id
        resp = client.post(
            f"/api/v1/worlds/world-1/contradictions/{con.id}/resolve",
            json={"status": "RESOLVED", "preferred_fact_version_id": v2.id},
            headers={"Authorization": "Bearer dummy"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "RESOLVED"

        db_session.refresh(v1)
        db_session.refresh(v2)
        assert v2.status == "ACTIVE"
        assert v1.status == "SUPERSEDED"
    finally:
        app.dependency_overrides.clear()


def test_resolve_contradiction_choice_keep_old(db_session):
    from app.services.entity_service import EntityService

    service = EntityService(db_session)
    entity = Entity(id="ent-res-2", world_id="world-1", canonical_name="Bors")
    db_session.add(entity)
    db_session.commit()

    v1 = service.add_fact(entity.id, "origin", "Gaunnes")
    v2 = service.add_fact(entity.id, "origin", "Paris")

    con = db_session.query(Contradiction).filter(
        Contradiction.old_fact_version_id == v1.id,
        Contradiction.new_fact_version_id == v2.id
    ).first()
    assert con is not None

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: db_session.query(User).filter(User.id == "user-1").first()

    try:
        client = TestClient(app)
        # Author picks "keep old": preferred_fact_version_id = v1.id
        resp = client.post(
            f"/api/v1/worlds/world-1/contradictions/{con.id}/resolve",
            json={"status": "RESOLVED", "preferred_fact_version_id": v1.id},
            headers={"Authorization": "Bearer dummy"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "RESOLVED"

        db_session.refresh(v1)
        db_session.refresh(v2)
        assert v1.status == "ACTIVE"
        assert v2.status == "SUPERSEDED"
    finally:
        app.dependency_overrides.clear()


def test_resolve_contradiction_invalid_preferred_id(db_session):
    from app.services.entity_service import EntityService

    service = EntityService(db_session)
    entity = Entity(id="ent-res-3", world_id="world-1", canonical_name="Galahad")
    db_session.add(entity)
    db_session.commit()

    v1 = service.add_fact(entity.id, "origin", "Corbenic")
    v2 = service.add_fact(entity.id, "origin", "Sarras")

    con = db_session.query(Contradiction).filter(
        Contradiction.old_fact_version_id == v1.id,
        Contradiction.new_fact_version_id == v2.id
    ).first()
    assert con is not None

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: db_session.query(User).filter(User.id == "user-1").first()

    try:
        client = TestClient(app)
        resp = client.post(
            f"/api/v1/worlds/world-1/contradictions/{con.id}/resolve",
            json={"status": "RESOLVED", "preferred_fact_version_id": "non-existent-version-id"},
            headers={"Authorization": "Bearer dummy"}
        )
        assert resp.status_code == 400
        assert "preferred_fact_version_id must match" in resp.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_bulk_delete_entities_success(db_session):
    e1 = Entity(id="bulk-1", world_id="world-1", canonical_name="Bulk Entity 1")
    e2 = Entity(id="bulk-2", world_id="world-1", canonical_name="Bulk Entity 2")
    e3 = Entity(id="bulk-3", world_id="world-1", canonical_name="Keep Entity 3")
    a1 = EntityAlias(entity_id=e1.id, alias="B1")
    f2 = Fact(id="bf-2", entity_id=e2.id, property_name="status")
    fv2 = FactVersion(id="bfv-2", fact_id=f2.id, value="active", status="ACTIVE")
    db_session.add_all([e1, e2, e3, a1, f2, fv2])
    db_session.commit()

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: db_session.query(User).filter(User.id == "user-1").first()

    try:
        client = TestClient(app)
        resp = client.post(
            "/api/v1/worlds/world-1/entities/bulk-delete",
            json={"entity_ids": [e1.id, e2.id]},
            headers={"Authorization": "Bearer dummy"}
        )
        assert resp.status_code == 204

        assert db_session.get(Entity, e1.id) is None
        assert db_session.get(Entity, e2.id) is None
        assert db_session.get(EntityAlias, a1.id) is None
        assert db_session.get(Fact, f2.id) is None
        assert db_session.get(Entity, e3.id) is not None
    finally:
        app.dependency_overrides.clear()


def test_bulk_delete_entities_all_or_nothing(db_session):
    e1 = Entity(id="bulk-safe-1", world_id="world-1", canonical_name="Safe Entity")
    db_session.add(e1)
    db_session.commit()

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: db_session.query(User).filter(User.id == "user-1").first()

    try:
        client = TestClient(app)
        resp = client.post(
            "/api/v1/worlds/world-1/entities/bulk-delete",
            json={"entity_ids": [e1.id, "nonexistent-entity-id"]},
            headers={"Authorization": "Bearer dummy"}
        )
        assert resp.status_code == 404

        # Verify nothing was deleted
        assert db_session.get(Entity, e1.id) is not None
    finally:
        app.dependency_overrides.clear()


def test_bulk_delete_entities_empty_list(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: db_session.query(User).filter(User.id == "user-1").first()

    try:
        client = TestClient(app)
        resp = client.post(
            "/api/v1/worlds/world-1/entities/bulk-delete",
            json={"entity_ids": []},
            headers={"Authorization": "Bearer dummy"}
        )
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_add_alias_success(db_session):
    ent = Entity(id="alias-test-1", world_id="world-1", canonical_name="Lady Seraphina")
    db_session.add(ent)
    db_session.commit()

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: db_session.query(User).filter(User.id == "user-1").first()

    try:
        client = TestClient(app)
        resp = client.post(
            f"/api/v1/worlds/world-1/entities/{ent.id}/aliases",
            json={"alias": "The Shadow Blade"},
            headers={"Authorization": "Bearer dummy"}
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "The Shadow Blade" in data["aliases"]

        db_session.refresh(ent)
        assert any(a.alias == "The Shadow Blade" for a in ent.aliases)
    finally:
        app.dependency_overrides.clear()


def test_add_alias_rejects_duplicate_and_canonical(db_session):
    ent = Entity(id="alias-test-2", world_id="world-1", canonical_name="Lady Seraphina")
    a1 = EntityAlias(entity_id=ent.id, alias="Sera")
    db_session.add_all([ent, a1])
    db_session.commit()

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: db_session.query(User).filter(User.id == "user-1").first()

    try:
        client = TestClient(app)

        # Duplicate alias (case-insensitive)
        resp1 = client.post(
            f"/api/v1/worlds/world-1/entities/{ent.id}/aliases",
            json={"alias": "sera"},
            headers={"Authorization": "Bearer dummy"}
        )
        assert resp1.status_code == 400
        assert "already exists" in resp1.json()["detail"]

        # Alias equals canonical name (case-insensitive)
        resp2 = client.post(
            f"/api/v1/worlds/world-1/entities/{ent.id}/aliases",
            json={"alias": "LADY SERAPHINA"},
            headers={"Authorization": "Bearer dummy"}
        )
        assert resp2.status_code == 400
        assert "cannot match canonical name" in resp2.json()["detail"]

        # Empty/whitespace alias
        resp3 = client.post(
            f"/api/v1/worlds/world-1/entities/{ent.id}/aliases",
            json={"alias": "   "},
            headers={"Authorization": "Bearer dummy"}
        )
        assert resp3.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_remove_alias_success(db_session):
    ent = Entity(id="alias-test-3", world_id="world-1", canonical_name="Valen")
    a1 = EntityAlias(entity_id=ent.id, alias="The Shadow Blade")
    db_session.add_all([ent, a1])
    db_session.commit()

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: db_session.query(User).filter(User.id == "user-1").first()

    try:
        client = TestClient(app)
        resp = client.delete(
            f"/api/v1/worlds/world-1/entities/{ent.id}/aliases?alias=the%20shadow%20blade",
            headers={"Authorization": "Bearer dummy"}
        )
        assert resp.status_code == 204

        db_session.refresh(ent)
        assert len(ent.aliases) == 0
    finally:
        app.dependency_overrides.clear()


def test_remove_alias_nonexistent(db_session):
    ent = Entity(id="alias-test-4", world_id="world-1", canonical_name="Valen")
    db_session.add(ent)
    db_session.commit()

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: db_session.query(User).filter(User.id == "user-1").first()

    try:
        client = TestClient(app)
        resp = client.delete(
            f"/api/v1/worlds/world-1/entities/{ent.id}/aliases?alias=nonexistent",
            headers={"Authorization": "Bearer dummy"}
        )
        assert resp.status_code == 404
        assert "Alias not found" in resp.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_inline_retype_entity(db_session):
    ent = Entity(id="retype-test-1", world_id="world-1", canonical_name="Old Forest", entity_type="character")
    db_session.add(ent)
    db_session.commit()

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: db_session.query(User).filter(User.id == "user-1").first()

    try:
        client = TestClient(app)
        resp = client.put(
            f"/api/v1/worlds/world-1/entities/{ent.id}",
            json={"entity_type": "location"},
            headers={"Authorization": "Bearer dummy"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_type"] == "location"

        db_session.refresh(ent)
        assert ent.entity_type == "location"
    finally:
        app.dependency_overrides.clear()


def test_author_description_edits_preserve_history_and_can_be_cleared(db_session):
    from app.services.entity_service import EntityService

    entity = EntityService(db_session).create_entity(
        "world-1", "Arin", attributes={"description": "Original synopsis.", "subtype": "Prince"}
    )
    entity_id = entity.id
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: db_session.get(User, "user-1")
    try:
        client = TestClient(app)
        for description in ("The author's revised synopsis.", ""):
            response = client.put(
                f"/api/v1/worlds/world-1/entities/{entity_id}",
                json={"attributes": {"description": description}},
                headers={"Authorization": "Bearer dummy"},
            )
            assert response.status_code == 200
            facts = {fact["property_name"]: fact for fact in response.json()["facts"]}
            assert facts["description"]["current_version"]["value"] == description
            assert facts["description"]["current_version"]["status"] == "ACTIVE"
            assert facts["subtype"]["current_version"]["value"] == "Prince"

        versions = db_session.query(FactVersion).join(Fact).filter(
            Fact.entity_id == entity_id, Fact.property_name == "description"
        ).all()
        assert len(versions) == 3
        assert {version.value: version.status for version in versions} == {
            "Original synopsis.": "SUPERSEDED",
            "The author's revised synopsis.": "SUPERSEDED",
            "": "ACTIVE",
        }
        reloaded = client.get(f"/api/v1/worlds/world-1/entities/{entity_id}")
        assert reloaded.status_code == 200
        facts = {fact["property_name"]: fact for fact in reloaded.json()["facts"]}
        assert facts["description"]["current_version"]["value"] == ""
    finally:
        app.dependency_overrides.clear()


def test_get_entity_details_with_relationships_and_appearances(db_session):
    from app.models.manuscript import Manuscript
    from app.models.chapter import Chapter
    from app.models.event import Event, EventParticipant
    from app.models.relationship import Relationship, RelationshipVersion

    ms = Manuscript(id="ms-test-1", world_id="world-1", title="Book 1")
    db_session.add(ms)

    chap = Chapter(
        id="chap-test-1",
        manuscript_id=ms.id,
        title="The Awakening",
        chapter_number=1
    )
    db_session.add(chap)

    e1 = Entity(id="ent-detail-1", world_id="world-1", canonical_name="Arthur", entity_type="character")
    e2 = Entity(id="ent-detail-2", world_id="world-1", canonical_name="Guinevere", entity_type="character")
    db_session.add_all([e1, e2])
    db_session.commit()

    # Relationship Arthur -> Guinevere
    rel = Relationship(
        id="rel-test-1",
        world_id="world-1",
        source_entity_id=e1.id,
        target_entity_id=e2.id
    )
    db_session.add(rel)
    db_session.flush()

    rel_v = RelationshipVersion(
        id="relv-test-1",
        relationship_id=rel.id,
        chapter_id=chap.id,
        relationship_type="ALLIED_WITH",
        status="ACTIVE"
    )
    db_session.add(rel_v)

    # Event with Arthur
    ev = Event(
        id="ev-test-1",
        world_id="world-1",
        chapter_id=chap.id,
        event_type="BATTLE",
        description="The Great Battle"
    )
    db_session.add(ev)
    db_session.flush()

    ep = EventParticipant(
        id="ep-test-1",
        event_id=ev.id,
        entity_id=e1.id,
        role="COMMANDER"
    )
    db_session.add(ep)
    db_session.commit()

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: db_session.query(User).filter(User.id == "user-1").first()

    try:
        client = TestClient(app)
        resp = client.get(
            f"/api/v1/worlds/world-1/entities/{e1.id}",
            headers={"Authorization": "Bearer dummy"}
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["canonical_name"] == "Arthur"
        assert len(data["relationships"]) == 1
        rel_data = data["relationships"][0]
        assert rel_data["targetId"] == e2.id
        assert rel_data["targetName"] == "Guinevere"
        assert rel_data["relation"] == "ALLIED_WITH"
        assert rel_data["direction"] == "outgoing"
        assert rel_data["chapter_number"] == 1

        assert len(data["appearances"]) >= 1
        app_item = data["appearances"][0]
        assert app_item["id"] == chap.id
        assert app_item["chapter_number"] == 1
        assert "The Awakening" in app_item["title"]
    finally:
        app.dependency_overrides.clear()



