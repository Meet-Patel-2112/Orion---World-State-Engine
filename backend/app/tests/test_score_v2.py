"""The gold v2 scorer (`app.evaluation.score_v2`) on a small fixture, plus a perfect prediction of every gold chapter."""
import copy
import json
from pathlib import Path

import pytest

from app.evaluation.score_v2 import format_table_v2, gold_as_prediction, micro_average_v2, score_document_v2

TEXT = 'Anna met Ben. She is his sister. Ben said, "I own the farm." Their father Dan is dead. Far off lives Carl.'
GOLD_DIR = Path(__file__).resolve().parents[3] / "gold" / "v2"
OK = {"origin": "claude_draft", "status": "accepted"}
PENDING = {"origin": "claude_draft", "status": "pending"}


def span(surface, nth=0):
    start = -1
    for _ in range(nth + 1):
        start = TEXT.index(surface, start + 1)
    return {"start": start, "end": start + len(surface)}


def mention(mid, surface, key, nth=0, kind="proper", review=OK):
    return {"mention_id": mid, "text": surface, "type": "character", "mention_kind": kind, "entity_key": key,
            **span(surface, nth), "review": review}


def gold():
    return {
        "doc_id": "w/ch01", "text": TEXT,
        "annotation": {"status": "reviewed", "layers": {
            "mentions": {"coverage": "exhaustive", "region": {"start": 0, "end": TEXT.index("Far off")}},
            "quotes": {"coverage": "exhaustive"}, "facts": {"coverage": "exhaustive"},
            "relationships": {"coverage": "exhaustive"}}},
        "entities": [{"entity_key": k, "name": n, "type": "character", "review": OK}
                     for k, n in [("anna", "Anna"), ("ben", "Ben"), ("dan", "Dan"), ("carl", "Carl")]],
        "mentions": [mention("M1", "Anna", "anna"), mention("M2", "Ben", "ben"),
                     mention("M3", "She", "anna", kind="pronominal"), mention("M4", "his", "ben", kind="pronominal"),
                     mention("M5", "Ben", "ben", nth=1), mention("M6", "I", "ben", kind="pronominal"),
                     mention("M7", "Their", None, kind="pronominal"), mention("M8", "Dan", "dan")],
        "quotes": [{"quote_id": "Q1", "spans": [span("I own the farm.")], "speaker_entity_key": "ben",
                    "addressee_entity_keys": [], "review": OK}],
        "facts": [{"fact_id": "F1", "entity_key": "dan", "property": "status", "value": "dead",
                   "status_value": "DEAD", "evidence": span("Their father Dan is dead."), "assertion": "asserted",
                   "review": OK},
                  {"fact_id": "F2", "entity_key": "carl", "property": "location", "value": "far off",
                   "evidence": span("Far off lives Carl."), "assertion": "asserted", "review": PENDING}],
        "relationships": [{"relationship_id": "R1", "subject_entity_key": "anna", "predicate": "SIBLING_OF",
                           "object_entity_key": "ben", "evidence": span("She is his sister."),
                           "assertion": "asserted", "review": OK},
                          {"relationship_id": "R2", "subject_entity_key": "dan", "predicate": "FATHER_OF",
                           "object_entity_key": "anna", "evidence": span("Their father Dan is dead."),
                           "assertion": "asserted", "review": OK}],
    }


def pmention(mid, surface, nth=0):
    return {"mention_id": mid, "text": surface, **span(surface, nth), "type": "character"}


def prediction(**lists):
    return {"text": TEXT, "mentions": [], "coreference_clusters": [], "facts": [], "relationships": [], **lists}


def test_perfect_prediction_scores_one_and_pending_items_are_ignored():
    g = gold()
    s = score_document_v2(gold_as_prediction(g), g)
    assert s["provisional"] is False
    for m in ("mentions_exact", "mentions_typed", "facts", "relationships", "quotes_overlap", "coreference_b3"):
        assert s[m]["f1"] == 1.0, m
    assert s["facts"]["fp"] == 0                          # Carl's pending fact was predicted: ignored, not wrong
    assert s["gold_ignored_pending"]["facts"] == 1 and s["gold_counted"]["facts"] == 1
    assert s["claim_attribution"]["accuracy"] == 1.0 and s["quote_speaker"]["accuracy"] == 1.0


def test_include_pending_counts_drafts_and_is_marked_provisional():
    g = gold()
    s = score_document_v2(prediction(), g, include_pending=True)
    assert s["provisional"] is True and s["facts"]["fn"] == 2
    assert format_table_v2(micro_average_v2([s])).startswith("PROVISIONAL")
    assert score_document_v2(prediction(), g)["facts"]["fn"] == 1    # default: the pending fact is not gold


def test_mention_region_and_partial_coverage():
    g = gold()
    outside = pmention("P1", "Carl")                      # after the region: neither right nor wrong
    s = score_document_v2(prediction(mentions=[pmention("P0", "Anna"), outside, pmention("P2", "met")]), g)
    assert (s["mentions_exact"]["tp"], s["mentions_exact"]["fp"], s["mentions_exact"]["fn"]) == (1, 1, 7)
    g["annotation"]["layers"]["mentions"]["coverage"] = "partial"
    s = score_document_v2(prediction(mentions=[pmention("P0", "Anna"), pmention("P2", "met")]), g)
    assert s["mentions_exact"]["fp"] == 0 and s["mentions_exact"]["fn"] == 7


def test_entities_resolve_through_clusters_and_names():
    g = gold()
    pred = prediction(
        mentions=[pmention("P1", "Anna"), pmention("P2", "She"), pmention("P3", "Ben"),
                  {"mention_id": "P4", "text": "Dan"}],      # no offsets: named by its text
        coreference_clusters=[{"cluster_id": "C1", "mentions": ["P1", "P2"]}],
        facts=[{"entity_mention_id": "P4", "property": "status", "value": "dead"}],
        relationships=[{"subject_mention_id": "P3", "predicate": "SIBLING_OF", "object_mention_id": "P2"}])
    s = score_document_v2(pred, g)
    assert s["facts"]["tp"] == 1 and s["relationships"]["tp"] == 1     # Ben-Anna reversed still matches
    assert s["pred_unanchored"] == 1 and s["mention_linking"] == {"correct": 3, "total": 3, "accuracy": 1.0}


def test_relationship_and_fact_normalization():
    g = gold()
    pred = prediction(mentions=[pmention("P1", "Anna"), pmention("P2", "Dan")],
                      relationships=[{"subject_mention_id": "P1", "predicate": "CHILD_OF", "object_mention_id": "P2"}])
    s = score_document_v2(pred, g)
    assert s["relationships"]["tp"] == 0 and s["relationships_lenient"]["tp"] == 1   # PARENT_OF vs FATHER_OF
    g["facts"][0].update(property="age", value="one-and-twenty", age_years=21)
    del g["facts"][0]["status_value"]
    s = score_document_v2(prediction(mentions=[pmention("P2", "Dan")],
                                     facts=[{"entity_mention_id": "P2", "property": "age", "value": " 21 "}]), g)
    assert s["facts"]["tp"] == 1


def test_attribution_and_assertion_are_scored_on_matched_claims():
    g = gold()
    g["relationships"][0].update(claimed_by="ben", assertion="negated")
    pred = prediction(mentions=[pmention("P1", "Anna"), pmention("P2", "Ben")],
                      relationships=[{"subject_mention_id": "P1", "predicate": "SIBLING_OF", "object_mention_id": "P2"}])
    s = score_document_v2(pred, g)
    assert s["relationships"]["tp"] == 1
    assert s["claim_attribution"] == {"correct": 0, "total": 1, "accuracy": 0.0}    # narration, gold says Ben
    assert s["claim_assertion"]["accuracy"] == 0.0
    pred["relationships"][0].update(claimed_by_mention_id="P2", assertion="negated")
    s = score_document_v2(pred, g)
    assert s["claim_attribution"]["accuracy"] == 1.0 and s["claim_assertion"]["accuracy"] == 1.0


def test_coreference_b3_penalizes_merging_entities():
    g = gold()
    good = gold_as_prediction(g)
    merged = copy.deepcopy(good)
    merged["coreference_clusters"] = [{"cluster_id": "C1", "mentions": [m["mention_id"] for m in merged["mentions"]]}]
    assert score_document_v2(good, g)["coreference_b3"]["f1"] == 1.0
    s = score_document_v2(merged, g)["coreference_b3"]
    assert s["recall"] == 1.0 and s["precision"] < 0.5


def test_text_mismatch_is_rejected():
    with pytest.raises(ValueError):
        score_document_v2({"text": "other"}, gold())


@pytest.mark.skipif(not GOLD_DIR.exists(), reason="gold v2 not present")
def test_every_gold_chapter_scores_one_against_itself():
    per_doc = []
    for path in sorted(GOLD_DIR.rglob("ch*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        per_doc.append(score_document_v2(gold_as_prediction(doc), doc, include_pending=True))
    total = micro_average_v2(per_doc)
    for m in ("mentions_exact", "mentions_overlap", "mentions_typed", "facts", "relationships", "quotes_overlap",
              "coreference_b3", "coreference_b3_linked"):
        assert total[m]["f1"] == 1.0, m
    for m in ("mention_linking", "claim_attribution", "claim_assertion", "quote_speaker"):
        assert total[m]["accuracy"] == 1.0, m
