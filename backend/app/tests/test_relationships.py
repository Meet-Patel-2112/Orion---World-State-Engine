import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from app.main import app
from app.api.deps import get_db, get_current_user
from app.core.database import Base
from app.models.user import User
from app.models.world import World
from app.models.entity import Entity
from app.models.manuscript import Manuscript
from app.models.chapter import Chapter
from app.models.relationship import Relationship, RelationshipVersion
from app.models.contradiction import Contradiction


@pytest.fixture
def relationship_test_env():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    session = TestingSession()
    user1 = User(id="user-1", email="author1@example.com", password_hash="dummy")
    user2 = User(id="user-2", email="author2@example.com", password_hash="dummy")
    world1 = World(id="w1", user_id="user-1", name="World 1")
    world2 = World(id="w2", user_id="user-2", name="World 2")
    ent1 = Entity(id="ent-1", world_id="w1", canonical_name="Valen Thorne", entity_type="character")
    ent2 = Entity(id="ent-2", world_id="w1", canonical_name="Lady Seraphina", entity_type="character")
    ent3 = Entity(id="ent-3", world_id="w1", canonical_name="Tomas Hale", entity_type="character")
    ent_other = Entity(id="ent-other", world_id="w2", canonical_name="Other Realm Entity", entity_type="character")
    
    ms1 = Manuscript(id="ms-1", world_id="w1", title="Chronicle")
    ch1 = Chapter(id="ch-1", manuscript_id="ms-1", chapter_number=1, title="Chapter 1")
    ch2 = Chapter(id="ch-2", manuscript_id="ms-1", chapter_number=2, title="Chapter 2")

    session.add_all([user1, user2, world1, world2, ent1, ent2, ent3, ent_other, ms1, ch1, ch2])
    session.commit()
    session.close()

    active_user_id = {"id": "user-1"}

    def override_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    def override_user(db: Session = Depends(override_db)):
        return db.query(User).filter(User.id == active_user_id["id"]).first()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user

    client = TestClient(app)
    try:
        yield {
            "client": client,
            "session_factory": TestingSession,
            "set_user_id": lambda uid: active_user_id.update({"id": uid}),
            "user1": user1,
            "user2": user2,
            "world1": world1,
            "world2": world2,
            "ent1": ent1,
            "ent2": ent2,
            "ent3": ent3,
            "ch1": ch1,
            "ch2": ch2,
        }
    finally:
        app.dependency_overrides.clear()


def test_list_relationships_empty(relationship_test_env):
    client = relationship_test_env["client"]
    resp = client.get("/api/v1/worlds/w1/relationships")
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_relationship_new_pair_returns_201(relationship_test_env):
    client = relationship_test_env["client"]
    resp = client.post("/api/v1/worlds/w1/relationships", json={
        "source_entity_id": "ent-1",
        "target_entity_id": "ent-2",
        "relationship_type": "ALLY_OF",
        "chapter_id": "ch-1",
        "confidence": 0.95
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["source_entity_id"] == "ent-1"
    assert data["source_name"] == "Valen Thorne"
    assert data["target_entity_id"] == "ent-2"
    assert data["target_name"] == "Lady Seraphina"
    assert data["current_version"]["relationship_type"] == "ALLY_OF"
    assert data["current_version"]["status"] == "ACTIVE"
    assert data["current_version"]["chapter_id"] == "ch-1"
    assert data["current_version"]["chapter_number"] == 1
    assert data["current_version"]["confidence"] == 0.95
    assert len(data["versions"]) == 1


def test_create_relationship_existing_pair_appends_version_and_returns_200(relationship_test_env):
    client = relationship_test_env["client"]
    # 1. Create first version
    r1 = client.post("/api/v1/worlds/w1/relationships", json={
        "source_entity_id": "ent-1",
        "target_entity_id": "ent-2",
        "relationship_type": "ALLY_OF",
        "chapter_id": "ch-1"
    })
    assert r1.status_code == 201
    rel_id = r1.json()["id"]

    # 2. Add second version for same pair
    r2 = client.post("/api/v1/worlds/w1/relationships", json={
        "source_entity_id": "ent-1",
        "target_entity_id": "ent-2",
        "relationship_type": "KNOWS",
        "chapter_id": "ch-2"
    })
    assert r2.status_code == 200
    data = r2.json()
    assert data["id"] == rel_id
    assert data["current_version"]["relationship_type"] == "KNOWS"
    assert data["current_version"]["status"] == "ACTIVE"
    assert data["current_version"]["chapter_number"] == 2
    assert len(data["versions"]) == 2
    assert data["versions"][0]["relationship_type"] == "KNOWS"
    assert data["versions"][0]["status"] == "ACTIVE"
    assert data["versions"][1]["relationship_type"] == "ALLY_OF"
    assert data["versions"][1]["status"] == "SUPERSEDED"


def test_create_relationship_same_active_type_rejected_400(relationship_test_env):
    client = relationship_test_env["client"]
    client.post("/api/v1/worlds/w1/relationships", json={
        "source_entity_id": "ent-1",
        "target_entity_id": "ent-2",
        "relationship_type": "ALLY_OF"
    })
    # Duplicate active type
    dup = client.post("/api/v1/worlds/w1/relationships", json={
        "source_entity_id": "ent-1",
        "target_entity_id": "ent-2",
        "relationship_type": "ALLY_OF"
    })
    assert dup.status_code == 400
    assert "already" in dup.json()["detail"].lower()


def test_create_relationship_self_loop_rejected_400(relationship_test_env):
    client = relationship_test_env["client"]
    resp = client.post("/api/v1/worlds/w1/relationships", json={
        "source_entity_id": "ent-1",
        "target_entity_id": "ent-1",
        "relationship_type": "ALLY_OF"
    })
    assert resp.status_code == 400
    assert "cannot be the same" in resp.json()["detail"]


def test_create_relationship_missing_entities_or_chapter_404(relationship_test_env):
    client = relationship_test_env["client"]
    # Missing source entity
    r1 = client.post("/api/v1/worlds/w1/relationships", json={
        "source_entity_id": "nonexistent",
        "target_entity_id": "ent-2",
        "relationship_type": "ALLY_OF"
    })
    assert r1.status_code == 404

    # Missing target entity
    r2 = client.post("/api/v1/worlds/w1/relationships", json={
        "source_entity_id": "ent-1",
        "target_entity_id": "nonexistent",
        "relationship_type": "ALLY_OF"
    })
    assert r2.status_code == 404

    # Entity from another world
    r3 = client.post("/api/v1/worlds/w1/relationships", json={
        "source_entity_id": "ent-1",
        "target_entity_id": "ent-other",
        "relationship_type": "ALLY_OF"
    })
    assert r3.status_code == 404

    # Nonexistent chapter
    r4 = client.post("/api/v1/worlds/w1/relationships", json={
        "source_entity_id": "ent-1",
        "target_entity_id": "ent-2",
        "relationship_type": "ALLY_OF",
        "chapter_id": "nonexistent-ch"
    })
    assert r4.status_code == 404


def test_list_and_filter_relationships(relationship_test_env):
    client = relationship_test_env["client"]
    client.post("/api/v1/worlds/w1/relationships", json={
        "source_entity_id": "ent-1",
        "target_entity_id": "ent-2",
        "relationship_type": "ALLY_OF"
    })
    client.post("/api/v1/worlds/w1/relationships", json={
        "source_entity_id": "ent-2",
        "target_entity_id": "ent-3",
        "relationship_type": "MENTOR_OF"
    })

    # List all
    all_rels = client.get("/api/v1/worlds/w1/relationships").json()
    assert len(all_rels) == 2

    # Filter by ent-1 (source in 1 rel, target in 0)
    filter1 = client.get("/api/v1/worlds/w1/relationships?entity_id=ent-1").json()
    assert len(filter1) == 1
    assert filter1[0]["source_entity_id"] == "ent-1"

    # Filter by ent-2 (target in rel 1, source in rel 2)
    filter2 = client.get("/api/v1/worlds/w1/relationships?entity_id=ent-2").json()
    assert len(filter2) == 2


def test_get_relationship_by_id(relationship_test_env):
    client = relationship_test_env["client"]
    created = client.post("/api/v1/worlds/w1/relationships", json={
        "source_entity_id": "ent-1",
        "target_entity_id": "ent-2",
        "relationship_type": "ALLY_OF"
    }).json()

    get_resp = client.get(f"/api/v1/worlds/w1/relationships/{created['id']}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == created["id"]

    not_found = client.get("/api/v1/worlds/w1/relationships/missing-rel-id")
    assert not_found.status_code == 404


def test_update_relationship_put(relationship_test_env):
    client = relationship_test_env["client"]
    created = client.post("/api/v1/worlds/w1/relationships", json={
        "source_entity_id": "ent-1",
        "target_entity_id": "ent-2",
        "relationship_type": "ALLY_OF",
        "chapter_id": "ch-1"
    }).json()

    # Update to new type
    put_resp = client.put(f"/api/v1/worlds/w1/relationships/{created['id']}", json={
        "relationship_type": "ENEMY_OF",
        "chapter_id": "ch-2"
    })
    # Note: FRIEND_OF -> ENEMY_OF triggers inconsistency in vocabulary, but ALLY_OF -> ENEMY_OF is allowed evolution
    assert put_resp.status_code == 200
    updated = put_resp.json()
    assert updated["current_version"]["relationship_type"] == "ENEMY_OF"
    assert updated["current_version"]["status"] == "ACTIVE"
    assert updated["versions"][1]["status"] == "SUPERSEDED"

    # PUT with identical type rejected
    dup_put = client.put(f"/api/v1/worlds/w1/relationships/{created['id']}", json={
        "relationship_type": "ENEMY_OF"
    })
    assert dup_put.status_code == 400


def test_contradiction_detection_on_manual_relationship(relationship_test_env):
    client = relationship_test_env["client"]
    # In vocabulary.py: FRIEND_OF is mutually incompatible with ENEMY_OF
    # 1. Establish FRIEND_OF
    r1 = client.post("/api/v1/worlds/w1/relationships", json={
        "source_entity_id": "ent-1",
        "target_entity_id": "ent-2",
        "relationship_type": "FRIEND_OF",
        "chapter_id": "ch-1"
    })
    assert r1.status_code == 201

    # 2. Add conflicting ENEMY_OF on same chapter
    r2 = client.post("/api/v1/worlds/w1/relationships", json={
        "source_entity_id": "ent-1",
        "target_entity_id": "ent-2",
        "relationship_type": "ENEMY_OF",
        "chapter_id": "ch-1"
    })
    assert r2.status_code == 200
    data = r2.json()

    # Conflicting version must be stored as CONTRADICTED, while old stays ACTIVE
    assert data["current_version"]["relationship_type"] == "FRIEND_OF"
    assert data["current_version"]["status"] == "ACTIVE"
    assert data["versions"][0]["relationship_type"] == "ENEMY_OF"
    assert data["versions"][0]["status"] == "CONTRADICTED"

    # Verify a Contradiction record was generated
    session = relationship_test_env["session_factory"]()
    try:
        cons = session.query(Contradiction).filter(Contradiction.world_id == "w1").all()
        assert len(cons) == 1
        assert "RELATIONSHIP" in cons[0].contradiction_type.upper()
    finally:
        session.close()


def test_delete_relationship_removes_orphan_contradictions(relationship_test_env):
    client = relationship_test_env["client"]
    # Create relationship with a contradiction
    client.post("/api/v1/worlds/w1/relationships", json={
        "source_entity_id": "ent-1",
        "target_entity_id": "ent-2",
        "relationship_type": "FRIEND_OF",
        "chapter_id": "ch-1"
    })
    r2 = client.post("/api/v1/worlds/w1/relationships", json={
        "source_entity_id": "ent-1",
        "target_entity_id": "ent-2",
        "relationship_type": "ENEMY_OF",
        "chapter_id": "ch-1"
    })
    rel_id = r2.json()["id"]

    session = relationship_test_env["session_factory"]()
    assert session.query(Contradiction).filter(Contradiction.world_id == "w1").count() == 1
    session.close()

    # Delete the relationship
    del_resp = client.delete(f"/api/v1/worlds/w1/relationships/{rel_id}")
    assert del_resp.status_code == 204

    # Verify relationship and orphan contradictions are deleted
    session = relationship_test_env["session_factory"]()
    try:
        assert session.query(Relationship).filter(Relationship.id == rel_id).first() is None
        assert session.query(RelationshipVersion).filter(RelationshipVersion.relationship_id == rel_id).count() == 0
        assert session.query(Contradiction).filter(Contradiction.world_id == "w1").count() == 0
    finally:
        session.close()


def test_tenant_isolation(relationship_test_env):
    client = relationship_test_env["client"]
    # User 1 creates relationship in w1
    r = client.post("/api/v1/worlds/w1/relationships", json={
        "source_entity_id": "ent-1",
        "target_entity_id": "ent-2",
        "relationship_type": "ALLY_OF"
    }).json()
    rel_id = r["id"]

    # Switch to User 2
    relationship_test_env["set_user_id"]("user-2")

    # User 2 attempts to access w1 -> 404
    assert client.get("/api/v1/worlds/w1/relationships").status_code == 404
    assert client.get(f"/api/v1/worlds/w1/relationships/{rel_id}").status_code == 404
    assert client.post("/api/v1/worlds/w1/relationships", json={
        "source_entity_id": "ent-1", "target_entity_id": "ent-2", "relationship_type": "ENEMY_OF"
    }).status_code == 404
    assert client.put(f"/api/v1/worlds/w1/relationships/{rel_id}", json={
        "relationship_type": "ENEMY_OF"
    }).status_code == 404
    assert client.delete(f"/api/v1/worlds/w1/relationships/{rel_id}").status_code == 404
