"""The oracle harness's gold injection (experiments/oracle.py) and claim diagnosis (experiments/claims.py)."""
import json

from experiments.claims import diagnose, map_predicates, summarize
from experiments.oracle import CachedLLM, drop_added_in_region, gold_clusters, hybrid_mentions

TEXT = "Anna met Ben. She smiled. Later, far away, Anna wrote to Ben."
END = TEXT.index("Later")
OK = {"origin": "claude_draft", "status": "accepted"}


def gm(mid, s, e, key, kind="proper"):
    return {"mention_id": mid, "text": TEXT[s:e], "type": "character", "mention_kind": kind, "entity_key": key,
            "start": s, "end": e, "review": OK}


def gold():
    return {"doc_id": "w/ch01", "text": TEXT,
            "annotation": {"status": "reviewed", "layers": {
                "mentions": {"coverage": "exhaustive", "region": {"start": 0, "end": END}},
                "facts": {"coverage": "exhaustive"}, "relationships": {"coverage": "exhaustive"},
                "quotes": {"coverage": "exhaustive"}}},
            "entities": [{"entity_key": k, "name": n, "type": "character", "review": OK}
                         for k, n in (("anna", "Anna"), ("ben", "Ben"))],
            "mentions": [gm("G1", 0, 4, "anna"), gm("G2", 9, 12, "ben"), gm("G3", 14, 17, "anna", "pronominal")],
            "quotes": [], "facts": [],
            "relationships": [{"relationship_id": "R1", "subject_entity_key": "anna", "predicate": "FATHER_OF",
                               "object_entity_key": "ben", "evidence": {"start": 0, "end": 13},
                               "assertion": "asserted", "review": OK}]}


def pm(mid, surface, nth=0):
    s = -1
    for _ in range(nth + 1):
        s = TEXT.index(surface, s + 1)
    return {"mention_id": mid, "text": surface, "type": "character", "mention_kind": "proper", "start": s,
            "end": s + len(surface)}


def test_hybrid_mentions_take_gold_inside_the_region_and_predictions_after_it():
    predicted = [pm("X1", "Anna"), pm("X2", "Anna", 1), pm("X3", "Ben", 1), pm("X4", "met")]
    ms, gold_id = hybrid_mentions(gold(), predicted)
    assert [(m["mention_id"], m["text"]) for m in ms] == [("M1", "Anna"), ("M2", "Ben"), ("M3", "She"),
                                                         ("M4", "Anna"), ("M5", "Ben")]
    assert gold_id == {"M1": "G1", "M2": "G2", "M3": "G3"}       # "met" (X4) is inside the region: dropped


def test_mentions_coref_adds_inside_the_region_are_removed():
    ms, gold_id = hybrid_mentions(gold(), [pm("X2", "Anna", 1)])
    doc = {"mentions": ms + [{"mention_id": "M5", "text": "Ben", "start": 9, "end": 12}],    # an extra in-region span
           "coreference_clusters": [{"cluster_id": "C1", "mentions": ["M1", "M5", "M4"]}]}
    assert drop_added_in_region(doc, gold_id, END) == 1
    assert doc["coreference_clusters"] == [{"cluster_id": "C1", "mentions": ["M1", "M4"]}]


def test_gold_clusters_group_by_key_and_attach_later_mentions_by_vote():
    ms, gold_id = hybrid_mentions(gold(), [pm("X2", "Anna", 1), pm("X3", "Ben", 1)])
    doc = {"mentions": ms, "coreference_clusters": [{"cluster_id": "C1", "mentions": ["M1", "M2", "M4"]},  # tie
                                                    {"cluster_id": "C2", "mentions": ["M3", "M5"]}]}
    stats = gold_clusters(doc, gold_id, gold())
    clusters = sorted(sorted(c["mentions"]) for c in doc["coreference_clusters"])
    # Anna = M1, M3 (gold); "Ben" after the region (M5) voted into Anna's cluster by C2 (M3 is Anna);
    # M4 stays alone (C1 votes tie between anna and ben), so it is in no cluster
    assert clusters == [["M1", "M3", "M5"]]
    assert stats == {"after_region_kept_predicted_cluster": 1, "after_region_joined_gold_entity": 1}


def test_llm_cache_replays_identical_requests(tmp_path, monkeypatch):
    calls = []
    import extractor.llm as llm
    monkeypatch.setattr(llm, "generate", lambda system, user, schema, num_predict=1024, model="m":
                        calls.append(user) or {"answer": user})
    cache = CachedLLM(tmp_path / "c.json")
    assert cache("s", "u1", "json") == {"answer": "u1"} and cache("s", "u1", "json", 1024) == {"answer": "u1"}
    assert (cache.hits, cache.misses, calls) == (1, 1, ["u1"])
    assert CachedLLM(tmp_path / "c.json")("s", "u1", "json") == {"answer": "u1"} and calls == ["u1"]


def test_diagnosis_classifies_lenient_only_and_missing_entities():
    pred = {"text": TEXT, "mentions": [pm("P1", "Anna"), pm("P2", "Ben")], "coreference_clusters": [],
            "facts": [], "relationships": [{"subject_mention_id": "P1", "predicate": "PARENT_OF",
                                            "object_mention_id": "P2"}]}
    d = diagnose(pred, gold())
    assert [r["class"] for r in d["pred_relationships"]] == ["lenient_only"]
    assert d["gold_relationships"][0]["class"] == "found_lenient_only"
    assert d["gold_relationships"][0]["unexpressible"] == ["parent_gender"]
    assert summarize([d])["gold_relationships"] == {"found_lenient_only": 1}
    empty = diagnose({"text": TEXT, "mentions": [pm("P1", "Anna")]}, gold())
    assert empty["gold_relationships"][0]["class"] == "missed_entity_not_predicted"      # Ben never predicted


def test_predicate_mapping_swaps_child_of_and_leaves_parent_of():
    pred = {"relationships": [{"subject_mention_id": "a", "predicate": "CHILD_OF", "object_mention_id": "b"},
                              {"subject_mention_id": "c", "predicate": "PARENT_OF", "object_mention_id": "d"}]}
    out, log = map_predicates(pred)
    assert out["relationships"][0] == {"subject_mention_id": "b", "predicate": "PARENT_OF", "object_mention_id": "a"}
    assert out["relationships"][1]["predicate"] == "PARENT_OF" and pred["relationships"][0]["predicate"] == "CHILD_OF"
    assert json.dumps(dict(log))
