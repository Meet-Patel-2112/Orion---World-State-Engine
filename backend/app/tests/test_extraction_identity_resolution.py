"""Production identity regression tests; no inference or historical candidate installation."""
import copy

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base
from app.models.entity import Entity, EntityAlias
from app.models.fact import Fact, FactVersion
from app.models.event import EventParticipant
from app.models.relationship import Relationship
from app.models.world import World
from app.pipeline.extractor import to_legacy
from app.services.world_state_service import WorldStateService
from app.tests.test_extractor import gold


@pytest.fixture
def db():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as session:
        yield session
    engine.dispose()


def seed(db, name, aliases=(), world_id=None):
    if world_id is None:
        world = World(name="identity test")
        db.add(world)
        db.flush()
        world_id = world.id
    e = Entity(world_id=world_id, canonical_name=name, entity_type="character")
    db.add(e)
    db.flush()
    for alias in aliases:
        db.add(EntityAlias(entity_id=e.id, alias=alias))
    db.flush()
    return e


@pytest.mark.parametrize("person,alias,titled,evidence", [
    ("Alfred", "Alfred Inglethorp", "Mrs. Inglethorp", {"Alfred": None}),
    ("John", "John Cavendish", "Mrs. Cavendish", {"John": "m"}),
])
def test_shared_surname_is_not_identity_evidence(db, person, alias, titled, evidence):
    e = seed(db, person, [alias])
    assert WorldStateService(db).find_entity(e.world_id, [titled], "character", identity_evidence=evidence) is None


@pytest.mark.parametrize("name,aliases,titled", [
    ("Evie", ["Evelyn", "Evelyn Howard"], "Miss Howard"),
    ("Cynthia", ["Cynthia Murdoch"], "Miss Murdoch"),
])
def test_compatible_source_evidence_preserves_legitimate_join(db, name, aliases, titled):
    e = seed(db, name, aliases)
    assert WorldStateService(db).find_entity(
        e.world_id, [titled], "character", identity_evidence={name: "f"}) is e


@pytest.mark.parametrize("evidence,aliases", [
    ({}, ["Evelyn Howard"]),
    ({"Evie": None}, ["Evelyn Howard"]),
    ({"Evie": "m"}, ["Evelyn Howard"]),
    ({"Evie": "f", "Miss Howard": "m"}, ["Evelyn Howard"]),
    ({"Evie": "f"}, ["Evelyn Howard", "Mr. Howard"]),
])
def test_unknown_or_conflicting_evidence_abstains(db, evidence, aliases):
    e = seed(db, "Evie", aliases)
    assert WorldStateService(db).find_entity(
        e.world_id, ["Miss Howard"], "character", identity_evidence=evidence) is None


@pytest.mark.parametrize("unknown", [None, "conflict"])
def test_explicitly_unresolved_source_is_not_overridden_by_a_title(db, unknown):
    e = seed(db, "Mrs. Howard")
    assert WorldStateService(db).find_entity(e.world_id, ["Miss Howard"], "character",
        identity_evidence={"Mrs. Howard": unknown}) is None


def test_ordinary_exact_and_unambiguous_untitled_names_still_work(db):
    e = seed(db, "Dan", ["Daniel Esperanza"])
    service = WorldStateService(db)
    for names in (["Dan"], ["Daniel Esperanza"], ["Daniel"], ["Esperanza"]):
        assert service.find_entity(e.world_id, names, "character") is e


def test_compatible_evidence_does_not_choose_between_two_candidates(db):
    a = seed(db, "Evelyn Howard")
    seed(db, "Alice Howard", world_id=a.world_id)
    assert WorldStateService(db).find_entity(a.world_id, ["Miss Howard"], "character",
        identity_evidence={"Evelyn Howard": "f", "Alice Howard": "f"}) is None


def test_evidence_cannot_filter_an_ambiguous_family_down_to_one_person(db):
    a = seed(db, "John", ["John Cavendish"])
    seed(db, "Mary", ["Mary Cavendish"], world_id=a.world_id)
    assert WorldStateService(db).find_entity(a.world_id, ["Mr. Cavendish"], "character",
        identity_evidence={"John": "m", "Mary": "f"}) is None


def test_full_name_does_not_collapse_into_a_titled_surname(db):
    e = seed(db, "Mrs. Cavendish", ["Cavendish"])
    # Female evidence cannot prove that Mary is the same woman as this Mrs. Cavendish.
    assert WorldStateService(db).find_entity(e.world_id, ["Mary", "Mary Cavendish"], "character",
        identity_evidence={"Mrs. Cavendish": "f", "Mary": "f"}) is None


def test_untyped_normalized_endpoint_fallback_is_not_a_new_entity_merge(db):
    e = seed(db, "Mrs. Long")
    assert WorldStateService(db).find_entity(e.world_id, ["Long"]) is e


def test_evidence_and_world_lookup_do_not_cross_tenants(db):
    other = seed(db, "Evie", ["Evelyn Howard"])
    local = seed(db, "John", ["John Cavendish"])
    assert WorldStateService(db).find_entity(local.world_id, ["Miss Howard"], "character",
        identity_evidence={"Evie": "f"}) is None
    assert other.world_id != local.world_id


def test_adapter_supplies_nonfact_evidence_without_changing_predictions():
    doc = gold("Evie said she saw her. Miss Howard left.", [
        ("M1", "Evie", "character", "proper"), ("M2", "she", "character", "pronominal"),
        ("M3", "her", "character", "pronominal"), ("M4", "Miss Howard", "character", "proper")],
        clusters=[["M1", "M2", "M3"]])
    original = copy.deepcopy(doc)
    data = to_legacy(doc, 1)
    assert data["identity_evidence"] == {"evie": "f", "miss howard": "f"}
    assert all(e["attributes"] == {} for e in data["entities"])
    assert doc == original


def test_adapter_does_not_choose_evidence_from_conflicting_same_name_groups():
    doc = gold("Pat saw her and she left. Pat saw him and he left.", [
        ("M1", "Pat", "character", "proper"), ("M2", "her", "character", "pronominal"),
        ("M3", "she", "character", "pronominal"), ("M4", "Pat", "character", "proper", 1),
        ("M5", "him", "character", "pronominal"), ("M6", "he", "character", "pronominal")],
        clusters=[["M1", "M2", "M3"], ["M4", "M5", "M6"]])
    assert to_legacy(doc, 1)["identity_evidence"] == {"pat": None}


def test_explicit_alias_still_works_without_source_evidence(db):
    e = seed(db, "Evie", ["Miss Howard"])
    assert WorldStateService(db).find_entity(e.world_id, ["Miss Howard"], "character") is e


def test_correct_ages_and_event_agents_survive_integration(db):
    w = World(name="downstream identity")
    db.add(w)
    db.flush()
    entity = lambda n, aliases=(), **attrs: {
        "canonical_name": n, "type": "character", "aliases": list(aliases), "attributes": attrs}
    # Keep the real saved aliases, including the line-break form used in the manuscript.
    data = {"entities": [entity("John", ["John Cavendish"], age="forty-five"),
        entity("Mrs. Cavendish", ["Cavendish"], age="seventy"),
        entity("Alfred", ["Alfred Inglethorp"]),
        entity("Mrs. Inglethorp", ["Mrs.\nInglethorp"], hair_color="white"), entity("Witness")],
        "identity_evidence": {"john": "m", "mrs. cavendish": "f", "alfred": None, "mrs. inglethorp": "f"},
        "relationships": [{"subject": "Mrs. Inglethorp", "predicate": "KNOWS", "object": "Witness"}],
        "events": [{"type": "MEETING", "participants": [{"name": "Mrs. Inglethorp", "role": "AGENT"}]}]}
    original = copy.deepcopy(data)
    service = WorldStateService(db)
    service.integrate_extraction_result(w.id, data)
    db.commit()
    names = {e.id: e.canonical_name for e in db.query(Entity).filter_by(world_id=w.id)}
    facts = {(names[f.entity_id], f.property_name, v.value, v.status)
        for f in db.query(Fact) for v in db.query(FactVersion).filter_by(fact_id=f.id)}
    assert ("John", "age", "forty-five", "ACTIVE") in facts
    assert ("Mrs. Cavendish", "age", "seventy", "ACTIVE") in facts
    assert ("Mrs. Inglethorp", "hair_color", "white", "ACTIVE") in facts
    assert not any(n == "Alfred" for n, _, _, _ in facts)
    assert [(names[r.source_entity_id], names[r.target_entity_id]) for r in db.query(Relationship)] == [
        ("Mrs. Inglethorp", "Witness")]
    assert [(names[p.entity_id], p.role) for p in db.query(EventParticipant)] == [("Mrs. Inglethorp", "AGENT")]
    assert data == original


def test_new_identity_writes_rollback_with_the_callers_transaction(db):
    e = seed(db, "John", ["John Cavendish"])
    wid = e.world_id
    db.commit()
    WorldStateService(db).integrate_extraction_result(wid, {"entities": [
        {"canonical_name": "Mrs. Cavendish", "type": "character", "attributes": {"age": "seventy"}}]})
    db.rollback()
    assert [x.canonical_name for x in db.query(Entity).filter_by(world_id=wid)] == ["John"]
    assert db.query(FactVersion).count() == 0
