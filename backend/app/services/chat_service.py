"""
World chat and character chat, answered from the current world state: the facts, relationships and events the author
has accepted (ACTIVE versions only, so superseded or rejected claims never reach the model).

- No `entity_focus`: the world assistant answers questions about the world.
- `entity_focus` = an entity id: character chat for writer's block. The model speaks as that character, grounded in
  what the world state says about them, and says when it goes beyond it.
"""
from pathlib import Path
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.config.logging import get_logger
from app.core.constants import FactStatus, RelationshipStatus
from app.models.chapter import Chapter
from app.models.entity import Entity
from app.models.event import Event, EventParticipant
from app.models.relationship import Relationship
from app.pipeline.llm_client import llm_client
from app.schemas.chat import ChatCitation, ChatMessage, ChatQueryResponse

logger = get_logger(__name__)

PROMPTS = Path(__file__).parent.parent / "pipeline" / "prompts"
MAX_EVENTS = 25            # the character's most recent events, so the context fits the local model's window
HISTORY_TURNS = 8
REPLY_LENGTH = {"short": "to one short paragraph", "medium": "short: one to three paragraphs",
                "long": "fuller: up to five paragraphs"}           # the creator's preference (profile_service)


def _prompt(name: str, fallback: str) -> str:
    path = PROMPTS / name
    return path.read_text(encoding="utf-8") if path.exists() else fallback


def _active_facts(entity: Entity) -> Dict[str, object]:
    out = {}
    for fact in entity.facts:
        active = next((v for v in fact.versions if v.status == FactStatus.ACTIVE.value), None)
        if active is not None and active.value not in (None, ""):
            out[fact.property_name] = active.value
    return out


def _active_type(rel: Relationship) -> Optional[str]:
    active = next((v for v in rel.versions if v.status == RelationshipStatus.ACTIVE.value), None)
    return active.relationship_type if active else None


def _describe(entity: Entity) -> str:
    facts = _active_facts(entity)
    aliases = [a.alias for a in entity.aliases]
    parts = [f"{entity.canonical_name} ({entity.entity_type})"]
    if aliases:
        parts.append(f"also called {', '.join(aliases)}")
    if facts:
        parts.append("; ".join(f"{k.replace('_', ' ')}: {v}" for k, v in facts.items()))
    return " — ".join(parts)


class ChatService:
    def __init__(self, db: Session):
        self.db = db

    def query(
        self,
        world_id: str,
        message: str,
        history: List[ChatMessage] = [],
        entity_focus: Optional[str] = None,
        timeline_event_focus: Optional[str] = None,
        reply_length: str = "medium"
    ) -> ChatQueryResponse:
        character = None
        if entity_focus:
            character = self.db.query(Entity).filter(Entity.world_id == world_id, Entity.id == entity_focus).first()
        if character is not None:
            system, citations = self._character_context(world_id, character, reply_length)
        else:
            system, citations = self._world_context(world_id, message)

        messages = [{"role": h.role, "content": h.content} for h in history[-HISTORY_TURNS:]
                    if h.role in ("user", "assistant") and h.content]
        messages.append({"role": "user", "content": message})
        answer = llm_client.chat(messages=messages, system_prompt=system, temperature=0.7 if character else 0.3)

        actions = ([f"Ask {character.canonical_name} how they feel about someone they know.",
                    f"Ask what {character.canonical_name} wants most right now."] if character
                   else ["Explore entity relationship connections in the Knowledge Graph."])
        return ChatQueryResponse(response=answer, citations=citations, suggested_actions=actions)

    # ---------------------------------------------------------------- character chat
    def _character_context(self, world_id: str, character: Entity, reply_length: str = "medium"):
        name = character.canonical_name
        lines = [f"CHARACTER: {_describe(character)}", "", "RELATIONSHIPS:"]
        citations = [ChatCitation(source_type="entity", source_id=character.id, title=name,
                                  snippet=_describe(character))]

        rels = self.db.query(Relationship).filter(
            Relationship.world_id == world_id,
            (Relationship.source_entity_id == character.id) | (Relationship.target_entity_id == character.id)).all()
        known = []
        for rel in rels:
            kind = _active_type(rel)
            if not kind or not rel.source_entity or not rel.target_entity:
                continue
            other = rel.target_entity if rel.source_entity_id == character.id else rel.source_entity
            phrase = kind.replace("_", " ").lower()
            lines.append(f"- {rel.source_entity.canonical_name} {phrase} {rel.target_entity.canonical_name}")
            known.append(other)
        if not known:
            lines.append("- (none recorded)")
        if known:
            lines += ["", "PEOPLE AND PLACES THEY ARE CONNECTED TO:"]
            lines += [f"- {_describe(e)}" for e in {e.id: e for e in known}.values()]

        events = (self.db.query(Event).join(EventParticipant, EventParticipant.event_id == Event.id)
                  .outerjoin(Chapter, Chapter.id == Event.chapter_id)
                  .filter(Event.world_id == world_id, EventParticipant.entity_id == character.id)
                  .order_by(Chapter.chapter_number.desc(), Event.sequence_index.desc(), Event.start_position.desc(),
                            Event.created_at.desc())
                  .limit(MAX_EVENTS).all())
        lines += ["", "WHAT HAS HAPPENED TO THEM (story order, oldest first):"]
        for ev in reversed(events):
            chapter = f"chapter {ev.chapter.chapter_number}" if ev.chapter else "no chapter"
            lines.append(f"- [{chapter}] {ev.description.strip()}")
        if not events:
            lines.append("- (no events recorded)")
        for ev in events[:3]:
            citations.append(ChatCitation(source_type="event", source_id=ev.id, title=f"Event: {ev.event_type}",
                                          snippet=ev.description[:160]))

        template = _prompt("character_prompt.txt", "You are {name}, a character in the author's story.")
        template = template.replace("{length}", REPLY_LENGTH.get(reply_length, REPLY_LENGTH["medium"]))
        return template.replace("{name}", name) + "\n\n" + "\n".join(lines), citations

    # ---------------------------------------------------------------- world assistant
    def _world_context(self, world_id: str, message: str):
        entities = self.db.query(Entity).filter(Entity.world_id == world_id).limit(40).all()
        relationships = self.db.query(Relationship).filter(Relationship.world_id == world_id).limit(40).all()
        events = self.db.query(Event).filter(Event.world_id == world_id).limit(20).all()
        lines = ["CURRENT WORLD STATE:", "", "ENTITIES AND FACTS:"]
        citations: List[ChatCitation] = []
        for ent in entities:
            lines.append(f"- {_describe(ent)}")
            if ent.canonical_name.lower() in message.lower():
                citations.append(ChatCitation(source_type="entity", source_id=ent.id, title=ent.canonical_name,
                                              snippet=_describe(ent)))
        lines += ["", "RELATIONSHIPS:"]
        for rel in relationships:
            kind = _active_type(rel)
            if kind and rel.source_entity and rel.target_entity:
                lines.append(f"- {rel.source_entity.canonical_name} {kind} {rel.target_entity.canonical_name}")
        lines += ["", "EVENTS:"]
        lines += [f"- [{ev.event_type}] {ev.description}" for ev in events]
        system = _prompt("chat_prompt.txt", "You are an assistant for the author's fictional world.")
        return system + "\n\n" + "\n".join(lines), citations
