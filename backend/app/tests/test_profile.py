"""Creator profile: pen name, stats, preferences (stored per user as JSON) and password change."""
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_db
from app.config.settings import settings
from app.core.security import get_password_hash, verify_password
from app.main import app
from app.models.entity import Entity
from app.models.user import User
from app.models.world import World
from app.services.chat_service import ChatService
from app.pipeline.llm_client import llm_client


@pytest.fixture
def client(phase1_env):
    env = phase1_env
    with env.Session() as s:
        user = User(id="u-profile", email="author@example.com", password_hash=get_password_hash("old-password"))
        world = World(id="w-profile", name="Profile World", user_id=user.id)
        s.add_all([user, world, Entity(world_id="w-profile", canonical_name="Mara", entity_type="character")])
        s.commit()

    def override_db():
        db = env.Session()
        try:
            yield db
        finally:
            db.close()

    def override_user():
        with env.Session() as s:
            u = s.get(User, "u-profile")
            s.expunge(u)
            return u

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    yield env, TestClient(app)
    app.dependency_overrides.clear()


def test_profile_has_stats_and_defaults_then_keeps_what_the_author_sets(client):
    env, c = client
    got = c.get("/api/v1/auth/profile").json()
    assert got["email"] == "author@example.com" and got["display_name"] == ""
    assert got["stats"] == {"worlds": 1, "manuscripts": 0, "chapters": 0, "entities": 1}
    assert got["preferences"] == {"chat_reply_length": "medium", "review_preselect_new": True}

    put = c.put("/api/v1/auth/profile", json={"display_name": " Het ", "preferences": {"chat_reply_length": "long",
                                                                                      "unknown": 1}})
    assert put.status_code == 200 and put.json()["display_name"] == "Het"
    assert c.get("/api/v1/auth/profile").json()["preferences"] == {"chat_reply_length": "long",
                                                                    "review_preselect_new": True}
    assert c.put("/api/v1/auth/profile", json={"preferences": {"chat_reply_length": "epic"}}).status_code == 422


def test_password_change_needs_the_current_password(client):
    env, c = client
    assert c.post("/api/v1/auth/password", json={"current_password": "nope", "new_password": "new-password"}
                  ).status_code == 400
    assert c.post("/api/v1/auth/password", json={"current_password": "old-password", "new_password": "short"}
                  ).status_code == 422
    assert c.post("/api/v1/auth/password", json={"current_password": "old-password", "new_password": "new-password"}
                  ).status_code == 200
    with env.Session() as s:
        assert verify_password("new-password", s.get(User, "u-profile").password_hash)


def test_the_reply_length_preference_reaches_the_character_prompt(client, monkeypatch):
    env, c = client
    seen = {}
    monkeypatch.setattr(llm_client, "chat", lambda messages, system_prompt=None, temperature=0.7:
                        seen.update(system=system_prompt) or "ok")
    with env.Session() as s:
        mara = s.query(Entity).filter_by(world_id="w-profile").one()
        ChatService(s).query("w-profile", "hi", entity_focus=mara.id, reply_length="long")
    assert "Keep answers fuller: up to five paragraphs." in seen["system"]
    assert settings.STORAGE_DIR                      # profiles are written under the test's tmp storage
