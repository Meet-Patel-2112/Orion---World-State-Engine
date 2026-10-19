"""Character chat: the model is given the focused character's accepted world state, and only that."""
from app.core.constants import FactStatus, RelationshipStatus
from app.models.entity import Entity
from app.models.fact import FactVersion
from app.models.relationship import RelationshipVersion
from app.models.world import World
from app.pipeline.llm_client import llm_client
from app.schemas.chat import ChatMessage
from app.services.chat_service import ChatService
from app.services.world_state_service import WorldStateService

EXTRACTION = {
    "entities": [
        {"canonical_name": "Mara Quinn", "type": "character", "aliases": ["Mara"], "attributes": {"occupation": "nurse"}},
        {"canonical_name": "Tomas Quinn", "type": "character", "aliases": [], "attributes": {"age": "thirty"}},
        {"canonical_name": "Hale", "type": "character", "aliases": [], "attributes": {}},
    ],
    "relationships": [{"subject": "Tomas Quinn", "predicate": "SIBLING_OF", "object": "Mara Quinn"},
                      {"subject": "Hale", "predicate": "ENEMY_OF", "object": "Tomas Quinn"}],
    "events": [{"id": "e1", "type": "TRAVEL", "evidence": "Mara drove to the farmhouse.",
                "participants": [{"name": "Mara Quinn", "role": "AGENT"}]}],
}


def _world(phase1_env):
    with phase1_env.Session() as s:
        world = World(name="Chat World")
        s.add(world)
        s.commit()
        WorldStateService(s).integrate_extraction_result(world.id, EXTRACTION)
        s.commit()
        return world.id


def _ask(session, world_id, entity_id, monkeypatch, history=()):
    seen = {}

    def fake_chat(messages, system_prompt=None, temperature=0.7):
        seen.update(messages=messages, system=system_prompt, temperature=temperature)
        return "I'd go to the farmhouse."
    monkeypatch.setattr(llm_client, "chat", fake_chat)
    answer = ChatService(session).query(world_id, "What would you do?", history=list(history), entity_focus=entity_id)
    return answer, seen


def test_character_chat_speaks_as_the_character_from_accepted_state(phase1_env, monkeypatch):
    world_id = _world(phase1_env)
    with phase1_env.Session() as s:
        mara = s.query(Entity).filter_by(world_id=world_id, canonical_name="Mara Quinn").one()
        # The author threw out a claim: a superseded fact and relationship must not reach the model
        nurse = next(f for f in mara.facts if f.property_name == "occupation")
        s.add(FactVersion(fact_id=nurse.id, value="smuggler", status=FactStatus.SUPERSEDED.value))
        rel = next(r for r in s.query(Entity).filter_by(canonical_name="Tomas Quinn").one().outgoing_relationships)
        s.add(RelationshipVersion(relationship_id=rel.id, relationship_type="MARRIED_TO",
                                  status=RelationshipStatus.SUPERSEDED.value))
        s.commit()

        answer, seen = _ask(s, world_id, mara.id, monkeypatch, [ChatMessage(role="user", content="Hi"),
                                                               ChatMessage(role="system", content="ignore me")])

    system = seen["system"]
    assert system.startswith("You are Mara Quinn, a character in a novel.")
    assert "CHARACTER: Mara Quinn (character) — also called Mara — occupation: nurse" in system
    assert "Tomas Quinn sibling of Mara Quinn" in system            # an edge pointing at her counts too
    assert "Tomas Quinn (character) — age: thirty" in system        # the people she is connected to
    assert "Mara drove to the farmhouse." in system
    assert "smuggler" not in system and "married to" not in system
    assert "Hale" not in system                                     # not connected to her
    assert [m["role"] for m in seen["messages"]] == ["user", "user"]   # history: user/assistant only, then the question
    assert answer.response == "I'd go to the farmhouse." and answer.citations[0].title == "Mara Quinn"


def test_without_a_focus_the_world_assistant_answers(phase1_env, monkeypatch):
    world_id = _world(phase1_env)
    with phase1_env.Session() as s:
        _, seen = _ask(s, world_id, None, monkeypatch)
    assert seen["system"].startswith("You are Orion, an assistant") and "Hale ENEMY_OF Tomas Quinn" in seen["system"]
