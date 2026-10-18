import pytest
from datetime import datetime, timedelta
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
from app.models.entity import Entity, EntityMention
from app.models.manuscript import Manuscript
from app.models.chapter import Chapter
from app.models.chapter_version import ChapterVersion
from app.models.extraction_run import ExtractionRun
from app.models.fact import Fact, FactVersion
from app.models.relationship import Relationship, RelationshipVersion
from app.models.contradiction import Contradiction


@pytest.fixture
def graph_test_env():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    session = TestingSession()
    t0 = datetime(2026, 1, 1, 10, 0, 0)

    user1 = User(id="user-1", email="author1@example.com", password_hash="dummy")
    user2 = User(id="user-2", email="author2@example.com", password_hash="dummy")
    world1 = World(id="w1", user_id="user-1", name="World 1")
    world2 = World(id="w2", user_id="user-2", name="World 2")

    ms1 = Manuscript(id="ms-1", world_id="w1", title="Chronicle")
    ch1 = Chapter(id="ch-1", manuscript_id="ms-1", chapter_number=1, title="Chapter 1")
    ch2 = Chapter(id="ch-2", manuscript_id="ms-1", chapter_number=2, title="Chapter 2")
    cv1 = ChapterVersion(id="cv-1", chapter_id="ch-1", version_number=1)
    cv2 = ChapterVersion(id="cv-2", chapter_id="ch-2", version_number=1)
    ex1 = ExtractionRun(id="ex-1", chapter_version_id="cv-1", status="done")
    ex2 = ExtractionRun(id="ex-2", chapter_version_id="cv-2", status="done")

    # Entities
    # ent1: present in ch1 and ch2
    ent1 = Entity(id="ent-1", world_id="w1", canonical_name="Valen Thorne", entity_type="character")
    # ent2: present in ch1 and ch2
    ent2 = Entity(id="ent-2", world_id="w1", canonical_name="Lady Seraphina", entity_type="character")
    # ent3: introduced ONLY in Chapter 2 via mention
    ent3 = Entity(id="ent-3", world_id="w1", canonical_name="Tomas Hale", entity_type="character")
    # ent_manual: manually created with no chapter-tagged data anywhere
    ent_manual = Entity(id="ent-man", world_id="w1", canonical_name="Ancient Lorekeeper", entity_type="character")
    # ent_other: belongs to world2
    ent_other = Entity(id="ent-other", world_id="w2", canonical_name="Other World Guy", entity_type="character")

    # Mention for ent3 only in chapter 2
    m_ent3 = EntityMention(
        id="m-3",
        entity_id="ent-3",
        extraction_run_id="ex-2",
        surface_text="Tomas Hale",
    )

    # Fact on ent1 that changes between chapters
    f1 = Fact(id="f-1", entity_id="ent-1", property_name="status", created_at=t0)
    fv1_ch1 = FactVersion(
        id="fv-101",
        fact_id="f-1",
        chapter_id="ch-1",
        value="alive",
        status="SUPERSEDED",
        created_at=t0 + timedelta(minutes=10),
    )
    fv1_ch2 = FactVersion(
        id="fv-102",
        fact_id="f-1",
        chapter_id="ch-2",
        value="deceased",
        status="ACTIVE",
        created_at=t0 + timedelta(minutes=20),
    )

    # Relationship between ent1 and ent2 that changes between chapters
    # Ch1: ALLY_OF, Ch2: ENEMY_OF
    rel1 = Relationship(id="rel-1", world_id="w1", source_entity_id="ent-1", target_entity_id="ent-2", created_at=t0)
    rv1_ch1 = RelationshipVersion(
        id="rv-101",
        relationship_id="rel-1",
        relationship_type="ALLY_OF",
        status="SUPERSEDED",
        chapter_id="ch-1",
        created_at=t0 + timedelta(minutes=10),
    )
    rv1_ch2 = RelationshipVersion(
        id="rv-102",
        relationship_id="rel-1",
        relationship_type="ENEMY_OF",
        status="ACTIVE",
        chapter_id="ch-2",
        created_at=t0 + timedelta(minutes=20),
    )

    # Relationship only appearing in chapter 2 between ent2 and ent3
    rel2 = Relationship(id="rel-2", world_id="w1", source_entity_id="ent-2", target_entity_id="ent-3", created_at=t0)
    rv2_ch2 = RelationshipVersion(
        id="rv-201",
        relationship_id="rel-2",
        relationship_type="KNOWS",
        status="ACTIVE",
        chapter_id="ch-2",
        created_at=t0 + timedelta(minutes=20),
    )

    session.add_all([
        user1, user2, world1, world2,
        ms1, ch1, ch2, cv1, cv2, ex1, ex2,
        ent1, ent2, ent3, ent_manual, ent_other,
        m_ent3,
        f1, fv1_ch1, fv1_ch2,
        rel1, rv1_ch1, rv1_ch2,
        rel2, rv2_ch2,
    ])
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
            "t0": t0,
        }
    finally:
        app.dependency_overrides.clear()


def test_get_graph_latest_default_200(graph_test_env):
    client = graph_test_env["client"]
    resp = client.get("/api/v1/worlds/w1/graph")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["nodes"]) >= 3
    assert len(data["edges"]) == 2

    # Latest rel1 is ENEMY_OF (ACTIVE)
    rel1_edge = next(e for e in data["edges"] if e["id"] == "rel-1")
    assert rel1_edge["type"] == "ENEMY_OF"
    assert rel1_edge["status"] == "ACTIVE"

    # Latest ent1 property status is deceased
    ent1_node = next(n for n in data["nodes"] if n["id"] == "ent-1")
    assert ent1_node["properties"]["status"] == "deceased"


def test_get_graph_as_of_chapter_validation_422(graph_test_env):
    client = graph_test_env["client"]
    assert client.get("/api/v1/worlds/w1/graph?as_of_chapter=0").status_code == 422
    assert client.get("/api/v1/worlds/w1/graph?as_of_chapter=-1").status_code == 422


def test_get_graph_as_of_chapter_1_vs_chapter_2(graph_test_env):
    client = graph_test_env["client"]

    # As of chapter 1:
    resp1 = client.get("/api/v1/worlds/w1/graph?as_of_chapter=1")
    assert resp1.status_code == 200
    data1 = resp1.json()

    # In chapter 1:
    # rel1 should be ALLY_OF (ch1 version)
    edges1 = {e["id"]: e for e in data1["edges"]}
    assert "rel-1" in edges1
    assert edges1["rel-1"]["type"] == "ALLY_OF"
    # rel2 should NOT exist in chapter 1 (introduced in chapter 2)
    assert "rel-2" not in edges1

    # In chapter 1, ent1 status should be alive
    nodes1 = {n["id"]: n for n in data1["nodes"]}
    assert "ent-1" in nodes1
    assert nodes1["ent-1"]["properties"]["status"] == "alive"

    # ent3 was only introduced in Chapter 2, so it should NOT be in nodes1
    assert "ent-3" not in nodes1

    # ent_manual has no chapter data anywhere, so it MUST be in nodes1
    assert "ent-man" in nodes1

    # As of chapter 2:
    resp2 = client.get("/api/v1/worlds/w1/graph?as_of_chapter=2")
    assert resp2.status_code == 200
    data2 = resp2.json()

    edges2 = {e["id"]: e for e in data2["edges"]}
    assert edges2["rel-1"]["type"] == "ENEMY_OF"
    assert "rel-2" in edges2

    nodes2 = {n["id"]: n for n in data2["nodes"]}
    assert nodes2["ent-1"]["properties"]["status"] == "deceased"
    # ent3 introduced in chapter 2 IS in nodes2
    assert "ent-3" in nodes2
    assert "ent-man" in nodes2


def test_get_graph_as_of_chapter_excludes_detected_contradictions(graph_test_env):
    client = graph_test_env["client"]
    session_factory = graph_test_env["session_factory"]
    t0 = graph_test_env["t0"]

    # Seed an entity with a fact in ch1 that has a DETECTED contradiction
    db = session_factory()
    f_disputed = Fact(id="f-disp", entity_id="ent-1", property_name="allegiance", created_at=t0)
    fv_disp = FactVersion(
        id="fv-disp-1",
        fact_id="f-disp",
        chapter_id="ch-1",
        value="Rebellion",
        status="CONTRADICTED",
        created_at=t0 + timedelta(minutes=5),
    )
    contra = Contradiction(
        id="c-disp",
        world_id="w1",
        contradiction_type="DIRECT_FACT",
        old_fact_version_id="fv-disp-1",
        explanation="Contradicted allegiance",
        confidence=1.0,
        status="DETECTED",
    )
    db.add_all([f_disputed, fv_disp, contra])
    db.commit()
    db.close()

    resp = client.get("/api/v1/worlds/w1/graph?as_of_chapter=1")
    assert resp.status_code == 200
    data = resp.json()
    ent1_node = next(n for n in data["nodes"] if n["id"] == "ent-1")
    # "allegiance" must be excluded because it is CONTRADICTED in a DETECTED contradiction
    assert "allegiance" not in ent1_node["properties"]


def test_get_graph_as_of_chapter_excludes_author_rejected_versions(graph_test_env):
    client = graph_test_env["client"]
    session_factory = graph_test_env["session_factory"]
    t0 = graph_test_env["t0"]

    # In Chapter 2, an extractor proposed Mara Venn ENEMY_OF Valen Thorne (rv-rej).
    # Author rejected it during contradiction resolution in favor of Chapter 1 version,
    # so rv-rej became SUPERSEDED in a RESOLVED contradiction.
    db = session_factory()
    rel_rej = Relationship(id="rel-rej", world_id="w1", source_entity_id="ent-1", target_entity_id="ent-3", created_at=t0)
    rv_old = RelationshipVersion(
        id="rv-rej-old",
        relationship_id="rel-rej",
        relationship_type="NEUTRAL",
        status="ACTIVE",
        chapter_id="ch-1",
        created_at=t0 + timedelta(minutes=5),
    )
    rv_new_rejected = RelationshipVersion(
        id="rv-rej-new",
        relationship_id="rel-rej",
        relationship_type="ENEMY_OF",
        status="SUPERSEDED",
        chapter_id="ch-2",
        created_at=t0 + timedelta(minutes=15),
    )
    contra_res = Contradiction(
        id="c-res",
        world_id="w1",
        contradiction_type="RELATIONSHIP_CONFLICT",
        old_relationship_version_id="rv-rej-old",
        new_relationship_version_id="rv-rej-new",
        explanation="Author rejected enemy relationship",
        confidence=0.9,
        status="RESOLVED",
    )
    db.add_all([rel_rej, rv_old, rv_new_rejected, contra_res])
    db.commit()
    db.close()

    # At as_of_chapter=2, rv_new_rejected must NOT be shown!
    resp = client.get("/api/v1/worlds/w1/graph?as_of_chapter=2")
    assert resp.status_code == 200
    data = resp.json()
    rej_edge = next((e for e in data["edges"] if e["id"] == "rel-rej"), None)
    assert rej_edge is not None
    # Must be NEUTRAL (from chapter 1), NOT the rejected ENEMY_OF version
    assert rej_edge["type"] == "NEUTRAL"


def test_get_graph_beyond_last_chapter_returns_full_state(graph_test_env):
    client = graph_test_env["client"]
    resp = client.get("/api/v1/worlds/w1/graph?as_of_chapter=999")
    assert resp.status_code == 200
    data = resp.json()
    # Returns all state up through chapter 2
    edge_ids = {e["id"] for e in data["edges"]}
    assert "rel-1" in edge_ids
    assert "rel-2" in edge_ids


def test_get_graph_tenant_isolation_404(graph_test_env):
    client = graph_test_env["client"]
    graph_test_env["set_user_id"]("user-2")
    # User 2 cannot access user 1's graph
    assert client.get("/api/v1/worlds/w1/graph").status_code == 404
    assert client.get("/api/v1/worlds/w1/graph?as_of_chapter=1").status_code == 404
