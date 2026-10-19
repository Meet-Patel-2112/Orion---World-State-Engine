"""The extractor's gold document -> the integration's dict (app/pipeline/extractor.py)."""
from app.pipeline.extractor import to_legacy
from app.tests.test_phase2_integration import contradictions, integrate, world  # noqa: F401 (fixture)


def gold(text, spans, clusters=(), facts=(), relationships=(), events=(), temporal=()):
    """spans: (id, text, type, kind[, nth occurrence]) -> mentions with offsets found in `text`."""
    mentions = []
    for mid, s, kind_type, kind, *nth in spans:
        at = -1
        for _ in range((nth or [0])[0] + 1):
            at = text.index(s, at + 1)
        mentions.append({"mention_id": mid, "text": s, "type": kind_type, "mention_kind": kind,
                         "start": at, "end": at + len(s)})
    return {"text": text, "mentions": mentions,
            "coreference_clusters": [{"cluster_id": f"C{n}", "mentions": c} for n, c in enumerate(clusters, 1)],
            "facts": list(facts), "relationships": list(relationships), "events": list(events),
            "temporal_relations": list(temporal)}


def chapter(age):
    text = f"My name is Evelyn McKinnon. I am {age}. I told my boss about the fog. Dan waved. A woman left. Evelyn slept."
    return gold(
        text,
        [("M1", "My", "character", "pronominal"), ("M2", "Evelyn McKinnon", "character", "proper"),
         ("M3", "I", "character", "pronominal"), ("M4", "boss", "character", "nominal"),
         ("M5", "fog", "other", "nominal"), ("M6", "Dan", "character", "proper"),
         ("M7", "woman", "character", "nominal"), ("M8", "Evelyn", "character", "proper", 1),
         ("M9", "I", "character", "pronominal", 1)],
        clusters=[["M1", "M2", "M3", "M8", "M9"]],
        facts=[{"fact_id": "F1", "property": "age", "entity_mention_id": "M2", "value": age}],
        relationships=[{"relationship_id": "R1", "predicate": "WORKS_FOR", "subject_mention_id": "M2",
                        "object_mention_id": "M4"}],
        events=[{"event_id": "E1", "type": "CONVERSATION", "trigger": "told", "start": text.index("told"),
                 "end": text.index("told") + 4, "participants": [{"role": "agent", "mention_id": "M9"},
                                                                  {"role": "recipient", "mention_id": "M4"},
                                                                  {"role": "patient", "mention_id": "M5"}]},
                {"event_id": "E2", "type": "OTHER", "trigger": "waved", "start": text.index("waved"),
                 "end": text.index("waved") + 5, "participants": []},
                {"event_id": "E3", "type": "OTHER", "trigger": "slept", "start": text.index("slept"),
                 "end": text.index("slept") + 5, "participants": []}],
        temporal=[{"temporal_relation_id": "TR1", "source_event_id": "E1", "relation": "BEFORE",
                   "target_event_id": "E2"}])


def test_entities_are_named_clusters_or_what_facts_and_relationships_are_about():
    out = to_legacy(chapter("twenty four"), chapter_number=1)
    assert out["entities"] == [
        {"canonical_name": "Evelyn", "type": "character", "mention": "Evelyn", "aliases": ["Evelyn McKinnon"],
         "attributes": {"age": "twenty four"}},
        {"canonical_name": "Evelyn's boss", "type": "character", "mention": "Evelyn's boss", "aliases": [],
         "attributes": {}},                                           # a role noun alone is named after its owner
        {"canonical_name": "Dan", "type": "character", "mention": "Dan", "aliases": [], "attributes": {}},
    ]   # fog: not a character / location / organization; woman: no name and nothing is about her
    assert out["relationships"] == [{"subject": "Evelyn", "predicate": "WORKS_FOR", "object": "Evelyn's boss"}]
    assert out["events"] == [{"id": "E1", "type": "CONVERSATION", "evidence": "I told my boss about the fog.",
                              "participants": [{"name": "Evelyn", "role": "AGENT"},
                                               {"name": "Evelyn's boss", "role": "RECIPIENT"}]}]   # OTHER: left out ...
    assert out["temporal_relations"] == []                            # ... with their temporal relations


def test_an_age_in_words_that_goes_down_is_a_contradiction_across_chapters(world):
    env, w = world
    integrate(env, w["world_id"], w["runs"][1], to_legacy(chapter("twenty four"), 1))
    integrate(env, w["world_id"], w["runs"][2], to_legacy(chapter("nineteen"), 2))
    [c] = contradictions(env, w["world_id"])
    assert c["explanation"].startswith("[AGE_MONOTONIC] ")
    assert env.fact_statuses(w["world_id"], "Evelyn", "age") == [("twenty four", "ACTIVE"), ("nineteen", "CONTRADICTED")]


def test_a_chapter_naming_an_entity_by_its_alias_joins_the_stored_entity(world):
    from app.models.entity import Entity, EntityAlias
    env, w = world
    dan = lambda name, alias: {"canonical_name": name, "type": "character", "aliases": [alias], "attributes": {}}
    integrate(env, w["world_id"], w["runs"][1], {"entities": [dan("Dan", "Daniel Esperanza")]})
    integrate(env, w["world_id"], w["runs"][2], {"entities": [dan("Daniel Esperanza", "Daniel")]})   # canonical = alias
    integrate(env, w["world_id"], w["runs"][3], {"entities": [dan("Daniel", "Dan")]})                # alias = canonical
    with env.Session() as s:
        [entity] = s.query(Entity).filter_by(world_id=w["world_id"]).all()
        aliases = sorted(a.alias for a in s.query(EntityAlias).filter_by(entity_id=entity.id))
    assert entity.canonical_name == "Dan" and aliases == ["Daniel", "Daniel Esperanza"]


def test_names_keep_their_titles_and_mr_and_mrs_stay_two_people(world):
    from app.models.entity import Entity
    env, w = world
    bennet = lambda name: {"canonical_name": name, "type": "character", "aliases": [], "attributes": {}}
    integrate(env, w["world_id"], w["runs"][1], {"entities": [bennet("Mr. Bennet")]})
    integrate(env, w["world_id"], w["runs"][2], {"entities": [bennet("Mrs. Bennet")]})
    with env.Session() as s:
        names = sorted(e.canonical_name for e in s.query(Entity).filter_by(world_id=w["world_id"]))
    assert names == ["Mr. Bennet", "Mrs. Bennet"]                 # same surname, conflicting titles: not one person


def test_an_owner_qualified_role_finds_the_entity_it_was_merged_into(world):
    from app.models.entity import Entity, EntityAlias
    env, w = world
    person = lambda name: {"canonical_name": name, "type": "character", "aliases": [], "attributes": {}}
    integrate(env, w["world_id"], w["runs"][1], {"entities": [person("Mrs. Bennet")]})
    with env.Session() as s:                                     # the author merged "Mr. Bennet's wife" into her
        mrs = s.query(Entity).filter_by(world_id=w["world_id"]).one()
        s.add(EntityAlias(entity_id=mrs.id, alias="Mr. Bennet's wife"))
        s.commit()
    integrate(env, w["world_id"], w["runs"][2], {"entities": [person("Mr. Bennet's wife"), person("his wife")]})
    with env.Session() as s:
        names = sorted(e.canonical_name for e in s.query(Entity).filter_by(world_id=w["world_id"]))
    assert names == ["Mrs. Bennet", "his wife"]                   # "his wife" is still nobody in particular


def test_a_spouse_role_from_one_chapter_takes_the_name_a_later_chapter_gives(world):
    from app.models.entity import Entity
    from app.services.world_state_service import spouse_name
    env, w = world
    person = lambda name, **a: {"canonical_name": name, "type": "character", "aliases": [], "attributes": a}
    integrate(env, w["world_id"], w["runs"][1], {"entities": [person("Mr. Bennet"), person("Mr. Bennet's wife")],
                                                 "relationships": [{"subject": "Mr. Bennet", "predicate": "MARRIED_TO",
                                                                    "object": "Mr. Bennet's wife"}]})
    integrate(env, w["world_id"], w["runs"][2], {"entities": [person("Mrs. Bennet", status="nervous")]})
    with env.Session() as s:
        ents = {e.canonical_name: sorted(a.alias for a in e.aliases)
                for e in s.query(Entity).filter_by(world_id=w["world_id"])}
    assert ents == {"Mr. Bennet": [], "Mrs. Bennet": ["Mr. Bennet's wife"]}       # one woman, now named
    assert spouse_name("Mrs. Hall's husband") == "Mr. Hall" and spouse_name("Mr. Bennet's daughter") is None


def test_a_parent_relationship_takes_the_parents_gender():
    from app.pipeline.extractor import parent_predicate
    m = lambda *texts: [{"text": t} for t in texts]
    assert parent_predicate("PARENT_OF", m("Mr. Bennet", "he")) == "FATHER_OF"
    assert parent_predicate("PARENT_OF", m("his mother", "he", "he")) == "MOTHER_OF"     # the role noun decides
    assert parent_predicate("PARENT_OF", m("John's father")) == "FATHER_OF"
    assert parent_predicate("PARENT_OF", m("wife", "she", "her", "I")) == "MOTHER_OF"
    assert parent_predicate("PARENT_OF", m("Pat", "she", "he")) == "PARENT_OF"            # unclear: left as is
    assert parent_predicate("PARENT_OF", m("Pat", "she")) == "PARENT_OF"                  # one pronoun is not enough
    assert parent_predicate("SIBLING_OF", m("Mr. Bennet")) == "SIBLING_OF"


def test_a_role_already_named_after_its_owner_is_not_renamed_and_relationships_are_listed_once():
    text = "John's father loved John. John's father and John's mother left."
    at = lambda s, n=0: [i for i in range(len(text)) if text.startswith(s, i)][n]
    m = lambda mid, s, kind, n=0: {"mention_id": mid, "text": s, "type": "character", "mention_kind": kind,
                                   "start": at(s, n), "end": at(s, n) + len(s)}
    doc = {"text": text, "mentions": [m("M1", "John's father", "nominal"), m("M2", "John", "proper", 1),
                                      m("M3", "John's father", "nominal", 1)],
           "coreference_clusters": [], "facts": [], "events": [], "temporal_relations": [],
           "relationships": [{"relationship_id": "R1", "predicate": "PARENT_OF", "subject_mention_id": "M1",
                              "object_mention_id": "M2"},
                             {"relationship_id": "R2", "predicate": "PARENT_OF", "subject_mention_id": "M3",
                              "object_mention_id": "M2"}]}
    out = to_legacy(doc, 1)
    assert sorted(e["canonical_name"] for e in out["entities"]) == ["John", "John's father"]
    assert out["relationships"] == [{"subject": "John's father", "predicate": "FATHER_OF", "object": "John"}]
