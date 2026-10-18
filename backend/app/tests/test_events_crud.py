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
from app.models.event import Event, EventParticipant
from app.models.contradiction import Contradiction


@pytest.fixture
def event_test_env():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
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


def test_create_event_success_201(event_test_env):
    client = event_test_env["client"]
    resp = client.post(
        "/api/v1/worlds/w1/events",
        json={
            "description": "Valen leads the defense of the fortress.",
            "event_type": "BATTLE",
            "chapter_id": "ch-1",
            "sequence_index": None,
            "participants": [
                {"entity_id": "ent-1", "role": "commander"},
                {"entity_id": "ent-2", "role": "diplomat"},
            ],
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["id"] is not None
    assert data["world_id"] == "w1"
    assert data["chapter_id"] == "ch-1"
    assert data["chapter_number"] == 1
    assert data["event_type"] == "BATTLE"
    assert data["description"] == "Valen leads the defense of the fortress."
    assert len(data["participants"]) == 2
    part_map = {p["entity_id"]: p for p in data["participants"]}
    assert part_map["ent-1"]["entity_name"] == "Valen Thorne"
    assert part_map["ent-1"]["role"] == "commander"
    assert part_map["ent-2"]["entity_name"] == "Lady Seraphina"
    assert part_map["ent-2"]["role"] == "diplomat"


def test_create_event_duplicate_participant_rejected_400(event_test_env):
    client = event_test_env["client"]
    resp = client.post(
        "/api/v1/worlds/w1/events",
        json={
            "description": "Valen talks to Valen",
            "participants": [
                {"entity_id": "ent-1", "role": "speaker"},
                {"entity_id": "ent-1", "role": "listener"},
            ],
        },
    )
    assert resp.status_code == 400
    assert "Duplicate entity_id" in resp.json()["detail"]


def test_create_event_foreign_participant_or_chapter_404(event_test_env):
    client = event_test_env["client"]
    # Foreign participant entity from world 2
    resp = client.post(
        "/api/v1/worlds/w1/events",
        json={
            "description": "Invasion",
            "participants": [{"entity_id": "ent-other", "role": "invader"}],
        },
    )
    assert resp.status_code == 404

    # Foreign chapter
    resp = client.post(
        "/api/v1/worlds/w1/events",
        json={
            "description": "Invasion",
            "chapter_id": "ch-non-existent",
        },
    )
    assert resp.status_code == 404


def test_create_event_empty_description_422(event_test_env):
    client = event_test_env["client"]
    resp = client.post(
        "/api/v1/worlds/w1/events",
        json={"description": "   "},
    )
    assert resp.status_code == 422


def test_get_event_by_id_200_and_404(event_test_env):
    client = event_test_env["client"]
    create_resp = client.post(
        "/api/v1/worlds/w1/events",
        json={"description": "Event A", "chapter_id": "ch-1"},
    )
    ev_id = create_resp.json()["id"]

    # 200 OK
    get_resp = client.get(f"/api/v1/worlds/w1/events/{ev_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == ev_id
    assert get_resp.json()["description"] == "Event A"

    # 404 Not Found
    get_404 = client.get("/api/v1/worlds/w1/events/unknown-ev")
    assert get_404.status_code == 404


def test_reorder_events_within_chapter_200(event_test_env):
    client = event_test_env["client"]
    ev1 = client.post("/api/v1/worlds/w1/events", json={"description": "First", "chapter_id": "ch-1"}).json()["id"]
    ev2 = client.post("/api/v1/worlds/w1/events", json={"description": "Second", "chapter_id": "ch-1"}).json()["id"]
    ev3 = client.post("/api/v1/worlds/w1/events", json={"description": "Third", "chapter_id": "ch-1"}).json()["id"]

    # Reorder to ev3, ev1, ev2
    reorder_resp = client.patch(
        "/api/v1/worlds/w1/events/reorder",
        json={
            "chapter_id": "ch-1",
            "event_ids": [ev3, ev1, ev2],
        },
    )
    assert reorder_resp.status_code == 200
    data = reorder_resp.json()
    assert data["total"] == 3
    assert [e["id"] for e in data["events"]] == [ev3, ev1, ev2]
    assert [e["sequence_index"] for e in data["events"]] == [0, 1, 2]

    # Verify timeline reflects this
    tl_resp = client.get("/api/v1/worlds/w1/timeline")
    assert tl_resp.status_code == 200
    tl_events = [e["id"] for e in tl_resp.json()["events"]]
    assert tl_events == [ev3, ev1, ev2]


def test_reorder_events_missing_or_duplicate_or_foreign_rejected_400(event_test_env):
    client = event_test_env["client"]
    ev1 = client.post("/api/v1/worlds/w1/events", json={"description": "Event 1", "chapter_id": "ch-1"}).json()["id"]
    ev2 = client.post("/api/v1/worlds/w1/events", json={"description": "Event 2", "chapter_id": "ch-1"}).json()["id"]

    # Duplicate in event_ids
    resp_dup = client.patch(
        "/api/v1/worlds/w1/events/reorder",
        json={"chapter_id": "ch-1", "event_ids": [ev1, ev1]},
    )
    assert resp_dup.status_code == 400

    # Missing event from chapter
    resp_miss = client.patch(
        "/api/v1/worlds/w1/events/reorder",
        json={"chapter_id": "ch-1", "event_ids": [ev1]},
    )
    assert resp_miss.status_code == 400

    # Event from another chapter
    ev_ch2 = client.post("/api/v1/worlds/w1/events", json={"description": "Event Ch2", "chapter_id": "ch-2"}).json()["id"]
    resp_foreign = client.patch(
        "/api/v1/worlds/w1/events/reorder",
        json={"chapter_id": "ch-1", "event_ids": [ev1, ev2, ev_ch2]},
    )
    assert resp_foreign.status_code == 400


def test_reorder_events_no_chapter_events_200(event_test_env):
    client = event_test_env["client"]
    ev1 = client.post("/api/v1/worlds/w1/events", json={"description": "Unassigned 1"}).json()["id"]
    ev2 = client.post("/api/v1/worlds/w1/events", json={"description": "Unassigned 2"}).json()["id"]

    reorder_resp = client.patch(
        "/api/v1/worlds/w1/events/reorder",
        json={
            "chapter_id": None,
            "event_ids": [ev2, ev1],
        },
    )
    assert reorder_resp.status_code == 200
    data = reorder_resp.json()
    assert [e["id"] for e in data["events"]] == [ev2, ev1]
    assert [e["sequence_index"] for e in data["events"]] == [0, 1]


def test_update_event_in_place_200(event_test_env):
    client = event_test_env["client"]
    create_resp = client.post(
        "/api/v1/worlds/w1/events",
        json={
            "description": "Initial text",
            "event_type": "MEETING",
            "chapter_id": "ch-1",
            "participants": [{"entity_id": "ent-1", "role": "participant"}],
        },
    )
    ev_id = create_resp.json()["id"]

    # In-place update
    upd_resp = client.put(
        f"/api/v1/worlds/w1/events/{ev_id}",
        json={
            "description": "Updated text",
            "event_type": "CONFERENCE",
            "participants": [
                {"entity_id": "ent-2", "role": "chairperson"},
                {"entity_id": "ent-3", "role": "secretary"},
            ],
        },
    )
    assert upd_resp.status_code == 200
    data = upd_resp.json()
    assert data["id"] == ev_id
    assert data["description"] == "Updated text"
    assert data["event_type"] == "CONFERENCE"
    assert len(data["participants"]) == 2
    part_names = {p["entity_name"] for p in data["participants"]}
    assert part_names == {"Lady Seraphina", "Tomas Hale"}


def test_update_event_chapter_change_resets_sequence_index(event_test_env):
    client = event_test_env["client"]
    ev1 = client.post(
        "/api/v1/worlds/w1/events",
        json={"description": "Seq Event", "chapter_id": "ch-1", "sequence_index": 5},
    ).json()["id"]

    # Update to ch-2
    upd_resp = client.put(
        f"/api/v1/worlds/w1/events/{ev1}",
        json={"chapter_id": "ch-2"},
    )
    assert upd_resp.status_code == 200
    data = upd_resp.json()
    assert data["chapter_id"] == "ch-2"
    assert data["chapter_number"] == 2
    assert data["sequence_index"] is None


def test_delete_event_cleans_orphan_contradictions_204(event_test_env):
    client = event_test_env["client"]
    session_factory = event_test_env["session_factory"]

    ev1 = client.post("/api/v1/worlds/w1/events", json={"description": "Event 1"}).json()["id"]
    ev2 = client.post("/api/v1/worlds/w1/events", json={"description": "Event 2"}).json()["id"]

    # Seed contradiction referencing ev1
    db = session_factory()
    contra = Contradiction(
        id="c-1",
        world_id="w1",
        contradiction_type="EVENT_TIMELINE",
        event_id_a=ev1,
        event_id_b=ev2,
        explanation="Timeline paradox",
        confidence=0.9,
    )
    db.add(contra)
    db.commit()
    db.close()

    # Delete ev1
    del_resp = client.delete(f"/api/v1/worlds/w1/events/{ev1}")
    assert del_resp.status_code == 204

    # Verify ev1 deleted
    assert client.get(f"/api/v1/worlds/w1/events/{ev1}").status_code == 404

    # Verify contradiction c-1 deleted
    db = session_factory()
    assert db.query(Contradiction).filter(Contradiction.id == "c-1").first() is None
    db.close()


def test_event_tenant_isolation_404(event_test_env):
    client = event_test_env["client"]
    ev1 = client.post("/api/v1/worlds/w1/events", json={"description": "World 1 event"}).json()["id"]

    # Switch user to user2 (world2 owner)
    event_test_env["set_user_id"]("user-2")

    # User 2 cannot access user 1's event or world
    assert client.get(f"/api/v1/worlds/w1/events/{ev1}").status_code == 404
    assert client.put(f"/api/v1/worlds/w1/events/{ev1}", json={"description": "Hacked"}).status_code == 404
    assert client.delete(f"/api/v1/worlds/w1/events/{ev1}").status_code == 404
    assert (
        client.patch(
            "/api/v1/worlds/w1/events/reorder",
            json={"chapter_id": None, "event_ids": [ev1]},
        ).status_code
        == 404
    )
