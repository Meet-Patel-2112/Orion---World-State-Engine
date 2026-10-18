"""
The creator's profile and preferences. The users table holds only email and password (no schema change on a feature
branch, SPLIT.md Rule S.1), so the pen name and preferences live in a JSON file per user, like the proposals.
"""
import json
from pathlib import Path
from typing import Any, Dict

from sqlalchemy.orm import Session

from app.config.settings import settings
from app.models.chapter import Chapter
from app.models.entity import Entity
from app.models.manuscript import Manuscript
from app.models.user import User
from app.models.world import World

DEFAULT_PREFERENCES = {
    "chat_reply_length": "medium",     # short | medium | long: how much a character says per reply
    "review_preselect_new": True,      # re-extraction review: start new items ticked
}
REPLY_LENGTHS = {"short", "medium", "long"}


def _path(user_id: str) -> Path:
    return Path(settings.STORAGE_DIR) / "profiles" / f"{user_id}.json"


def load_profile(user_id: str) -> Dict[str, Any]:
    path = _path(user_id)
    stored = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return {"display_name": stored.get("display_name", ""),
            "preferences": {**DEFAULT_PREFERENCES, **stored.get("preferences", {})}}


def save_profile(user_id: str, display_name: Any = None, preferences: Any = None) -> Dict[str, Any]:
    profile = load_profile(user_id)
    if display_name is not None:
        profile["display_name"] = str(display_name).strip()[:120]
    if preferences:
        known = {k: v for k, v in preferences.items() if k in DEFAULT_PREFERENCES}
        if known.get("chat_reply_length") not in (None, *REPLY_LENGTHS):
            raise ValueError("chat_reply_length must be short, medium or long")
        if "review_preselect_new" in known:
            known["review_preselect_new"] = bool(known["review_preselect_new"])
        profile["preferences"].update(known)
    path = _path(user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
    return profile


def profile_with_stats(db: Session, user: User) -> Dict[str, Any]:
    worlds = db.query(World.id).filter(World.user_id == user.id)
    manuscripts = db.query(Manuscript.id).filter(Manuscript.world_id.in_(worlds))
    stats = {"worlds": worlds.count(), "manuscripts": manuscripts.count(),
             "chapters": db.query(Chapter).filter(Chapter.manuscript_id.in_(manuscripts)).count(),
             "entities": db.query(Entity).filter(Entity.world_id.in_(worlds)).count()}
    return {"id": user.id, "email": user.email, "created_at": user.created_at, **load_profile(user.id),
            "stats": stats}
