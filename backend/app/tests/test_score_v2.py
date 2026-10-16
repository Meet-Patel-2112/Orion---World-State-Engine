"""The gold v2 scorer (`app.evaluation.score_v2`): entity mapping, mutations of a perfect prediction, coverage and
review status, edge cases, and a perfect prediction of every gold chapter."""
import copy
import json
from pathlib import Path

import pytest

from app.evaluation.__main__ import main
from app.evaluation.score_v2 import (ACCURACIES, B3, COUNTS, format_table_v2, gold_as_prediction, micro_average_v2,
                                     score_document_v2)

TEXT = ('Anna met Ben. She is his sister. Ben said, "I own the farm." Their father Dan is dead. Mr. B left. '
        'Far off lives Carl.')
REGION_END = TEXT.index("Far off")
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


def gold(status="reviewed"):
    return {
        "doc_id": "w/ch01", "text": TEXT,
        "annotation": {"status": status, "layers": {
            "mentions": {"coverage": "exhaustive", "region": {"start": 0, "end": REGION_END}},
            "quotes": {"coverage": "exhaustive"}, "facts": {"coverage": "exhaustive"},
            "relationships": {"coverage": "exhaustive"}}},
        "entities": [{"entity_key": "anna", "name": "Anna", "type": "character", "review": OK},
                     {"entity_key": "ben", "name": "Ben", "aliases": ["Mr. B"], "type": "character", "review": OK},
                     {"entity_key": "dan", "name": "Dan", "aliases": ["Mr. B"], "type": "character", "review": OK},
                     {"entity_key": "carl", "name": "Carl", "type": "character", "review": OK}],
        "mentions": [mention("M1", "Anna", "anna"), mention("M2", "Ben", "ben"),
                     mention("M3", "She", "anna", kind="pronominal"), mention("M4", "his sister", "anna", kind="nominal"),
                     mention("M5", "his", "ben", kind="pronominal"), mention("M6", "Ben", "ben", nth=1),
                     mention("M7", "I", "ben", kind="pronominal"), mention("M8", "Their", None, kind="pronominal"),
                     mention("M9", "Dan", "dan"), mention("M10", "Mr. B", "dan"),
                     mention("M11", "Carl", "carl")],                       # outside the mention region
        "quotes": [{"quote_id": "Q1", "spans": [span("I own the farm.")], "speaker_entity_key": "ben",
                    "addressee_entity_keys": [], "review": OK}],
        "facts": [{"fact_id": "F1", "entity_key": "dan", "property": "status", "value": "dead",
                   "status_value": "DEAD", "evidence": span("Their father Dan is dead."), "assertion": "asserted",
                   "review": OK},
                  {"fact_id": "F2", "entity_key": "carl", "property": "location", "value": "far off",
                   "evidence": span("Far off lives Carl."), "assertion": "asserted", "review": OK},
                  {"fact_id": "F3", "entity_key": "anna", "property": "occupation", "value": "farmer",
                   "evidence": span("She is his sister."), "assertion": "asserted", "review": PENDING}],
        "relationships": [{"relationship_id": "R1", "subject_entity_key": "anna", "predicate": "SIBLING_OF",
                           "object_entity_key": "ben", "evidence": span("She is his sister."),
                           "assertion": "asserted", "claimed_by": "ben", "review": OK},
                          {"relationship_id": "R2", "subject_entity_key": "dan", "predicate": "FATHER_OF",
                           "object_entity_key": "anna", "evidence": span("Their father Dan is dead."),
                           "assertion": "asserted", "review": OK},
                          {"relationship_id": "R3", "subject_entity_key": "ben", "predicate": "KNOWS",
                           "object_entity_key": "dan", "evidence": span("Mr. B left."), "assertion": "asserted",
                           "review": PENDING}],
    }


def pm(mid, surface, nth=0, **extra):
    return {"mention_id": mid, "text": surface, **span(surface, nth), "type": "character", **extra}


def prediction(**lists):
    return {"text": TEXT, "mentions": [], "coreference_clusters": [], "facts": [], "relationships": [], **lists}


def fingerprint(s):
    out = {m: (s[m]["tp"], s[m]["fp"], s[m]["fn"]) for m in COUNTS}
    out.update({m: (s[m]["precision"], s[m]["recall"]) for m in B3})
    out.update({m: (s[m]["correct"], s[m]["total"]) for m in ACCURACIES})
    return out


# ---------------------------------------------------------------------------------------------------- perfect
def test_perfect_prediction_scores_one():
    s = score_document_v2(gold_as_prediction(gold()), gold())
    assert s["provisional"] is False
    for m in COUNTS + B3:
        assert s[m]["f1"] == 1.0, m
    for m in ACCURACIES:
        assert s[m]["accuracy"] == 1.0, m
    assert (s["mentions_exact"]["tp"], s["facts"]["tp"], s["relationships"]["tp"]) == (10, 2, 2)


# ---------------------------------------------------------------------------------------------------- mutations
def _by_id(pred, mid):
    return next(m for m in pred["mentions"] if m["mention_id"] == mid)


def _cluster(pred, mid):
    return next(c for c in pred["coreference_clusters"] if mid in c["mentions"])


def drop_she(p):
    p["mentions"].remove(_by_id(p, "M3"))
    _cluster(p, "M3")["mentions"].remove("M3")


def extra_mention(p):
    p["mentions"].append(pm("X1", "met"))


def wrong_type(p):
    _by_id(p, "M1")["type"] = "location"


def wrong_link(p):                        # the second 'Ben' put in Anna's cluster
    _cluster(p, "M6")["mentions"].remove("M6")
    _cluster(p, "M1")["mentions"].append("M6")


def split_cluster(p):
    ben = _cluster(p, "M2")
    ben["mentions"] = ["M2", "M5"]
    p["coreference_clusters"].append({"cluster_id": "CX", "mentions": ["M6", "M7"]})


def merge_clusters(p):
    anna, ben = _cluster(p, "M1"), _cluster(p, "M2")
    anna["mentions"] += ben["mentions"]
    p["coreference_clusters"].remove(ben)


def wrong_fact_value(p):
    next(f for f in p["facts"] if f["fact_id"] == "F1")["status_value"] = "ALIVE"


def wrong_predicate(p):
    next(r for r in p["relationships"] if r["relationship_id"] == "R2")["predicate"] = "MOTHER_OF"


def wrong_claimant(p):
    next(r for r in p["relationships"] if r["relationship_id"] == "R1")["claimed_by_mention_id"] = "M1"


def wrong_assertion(p):
    next(r for r in p["relationships"] if r["relationship_id"] == "R2")["assertion"] = "negated"


def wrong_quote_span(p):
    p["quotes"][0].update(span("Anna met"))


def wrong_quote_speaker(p):
    p["quotes"][0]["speaker_mention_id"] = "M1"


MENTION_COUNTS = {"mentions_exact", "mentions_overlap", "mentions_typed"}
CLAIM_ACC = {"claim_attribution", "claim_assertion"}
MUTATIONS = [
    (drop_she, MENTION_COUNTS | {"coreference_b3", "mention_linking"}),
    (extra_mention, MENTION_COUNTS | {"coreference_b3"}),
    (wrong_type, {"mentions_typed"}),
    (wrong_link, {"mention_linking", "coreference_b3", "coreference_b3_linked"}),
    (split_cluster, {"coreference_b3", "coreference_b3_linked"}),
    # Anna's mentions then vote with Ben's: R1 becomes Ben-Ben and R2 Dan-Ben, so both relationships fail, and the
    # prediction of Anna's pending fact now names Ben: it no longer matches the ignored item, so it is a false positive
    (merge_clusters, {"coreference_b3", "coreference_b3_linked", "mention_linking", "relationships",
                      "relationships_lenient", "facts"} | CLAIM_ACC),
    (wrong_fact_value, {"facts"} | CLAIM_ACC),
    (wrong_predicate, {"relationships"} | CLAIM_ACC),
    (wrong_claimant, {"claim_attribution"}),
    (wrong_assertion, {"claim_assertion"}),
    (wrong_quote_span, {"quotes_overlap", "quote_speaker"}),
    (wrong_quote_speaker, {"quote_speaker"}),
]


@pytest.mark.parametrize("mutate,expected", MUTATIONS, ids=[m.__name__ for m, _ in MUTATIONS])
def test_each_mutation_changes_exactly_its_metrics(mutate, expected):
    base = fingerprint(score_document_v2(gold_as_prediction(gold()), gold()))
    pred = gold_as_prediction(gold())
    mutate(pred)
    s = score_document_v2(pred, gold())
    got = fingerprint(s)
    assert {m for m in base if got[m] != base[m]} == expected
    for m in expected & set(COUNTS + B3):
        assert s[m]["f1"] < 1.0, m
    for m in expected & set(ACCURACIES):
        assert s[m]["accuracy"] is None or s[m]["accuracy"] < 1.0 or s[m]["total"] < base[m][1], m


def test_mutation_counts_are_the_expected_ones():
    def run(mutate):
        p = gold_as_prediction(gold())
        mutate(p)
        return score_document_v2(p, gold())
    s = run(drop_she)
    assert (s["mentions_exact"]["tp"], s["mentions_exact"]["fp"], s["mentions_exact"]["fn"]) == (9, 0, 1)
    assert s["coreference_b3"]["precision"] == 1.0 and s["coreference_b3"]["recall"] < 1.0
    s = run(extra_mention)
    assert (s["mentions_exact"]["fp"], s["mentions_exact"]["fn"]) == (1, 0)
    s = run(wrong_type)
    assert (s["mentions_typed"]["tp"], s["mentions_typed"]["fp"], s["mentions_typed"]["fn"]) == (9, 1, 1)
    s = run(wrong_link)
    assert s["mention_linking"] == {"correct": 8, "total": 9, "accuracy": 0.8889}   # 'Their' has no entity
    s = run(split_cluster)
    assert s["coreference_b3"]["precision"] == 1.0 and s["coreference_b3"]["recall"] < 1.0
    s = run(merge_clusters)
    assert s["coreference_b3"]["recall"] == 1.0 and s["coreference_b3"]["precision"] < 1.0
    s = run(wrong_fact_value)
    assert (s["facts"]["tp"], s["facts"]["fp"], s["facts"]["fn"]) == (1, 1, 1)
    s = run(wrong_predicate)
    assert (s["relationships"]["tp"], s["relationships"]["fp"], s["relationships"]["fn"]) == (1, 1, 1)
    assert s["relationships_lenient"]["f1"] == 1.0
    s = run(wrong_claimant)
    assert s["claim_attribution"] == {"correct": 3, "total": 4, "accuracy": 0.75}
    s = run(wrong_assertion)
    assert s["claim_assertion"] == {"correct": 3, "total": 4, "accuracy": 0.75}
    s = run(wrong_quote_span)
    assert (s["quotes_overlap"]["tp"], s["quotes_overlap"]["fp"], s["quotes_overlap"]["fn"]) == (0, 1, 1)
    assert s["quote_speaker"]["accuracy"] is None
    s = run(wrong_quote_speaker)
    assert s["quote_speaker"] == {"correct": 0, "total": 1, "accuracy": 0.0}


# ---------------------------------------------------------------------------------------------------- entity mapping
def test_entities_resolve_through_alignment_clusters_and_names():
    pred = prediction(
        mentions=[pm("P1", "Anna"), pm("P2", "She"), pm("P3", "Ben"), {"mention_id": "P4", "text": "Dan"}],
        coreference_clusters=[{"cluster_id": "C1", "mentions": ["P1", "P2"]}],
        facts=[{"entity_mention_id": "P4", "property": "status", "value": "dead"}],
        relationships=[{"subject_mention_id": "P3", "predicate": "SIBLING_OF", "object_mention_id": "P2"}])
    s = score_document_v2(pred, gold())
    assert s["relationships"]["tp"] == 1 and s["relationships"]["tp_fallback"] == 0   # Ben-Anna reversed matches
    assert s["facts"]["tp"] == 1 and s["facts"]["tp_fallback"] == 1                   # Dan named by text only
    d = s["diagnostics"]
    assert d["mention_sources"]["exact"] == 3 and d["mention_sources"]["name"] == 1
    assert d["fallback_mappings"] == [{"mention_id": "P4", "text": "Dan", "entity_key": "dan", "source": "name"}]


def test_ambiguous_alias_names_nothing_and_is_reported():
    pred = prediction(mentions=[{"mention_id": "P1", "text": "Mr. B"}],
                      facts=[{"entity_mention_id": "P1", "property": "status", "value": "dead"}])
    s = score_document_v2(pred, gold())
    assert (s["facts"]["tp"], s["facts"]["fp"], s["facts"]["unresolved"]) == (0, 1, 1)
    assert s["diagnostics"]["uncertain_mappings"][0]["source"] == "ambiguous_name"
    anchored = prediction(mentions=[pm("P1", "Mr. B")],                       # aligned: the gold mention decides
                          facts=[{"entity_mention_id": "P1", "property": "status", "value": "dead"}])
    assert score_document_v2(anchored, gold())["facts"]["tp"] == 1


def test_cluster_tie_names_nothing():
    pred = prediction(mentions=[pm("P1", "Anna"), pm("P2", "Ben"), pm("P3", "Their")],
                      coreference_clusters=[{"cluster_id": "C1", "mentions": ["P1", "P2", "P3"]}],
                      relationships=[{"subject_mention_id": "P1", "predicate": "SIBLING_OF",
                                      "object_mention_id": "P2"}])
    s = score_document_v2(pred, gold())
    assert s["relationships"]["unresolved"] == 1 and s["relationships"]["tp"] == 0
    assert {m["source"] for m in s["diagnostics"]["uncertain_mappings"]} == {"cluster_tie"}
    assert s["mention_linking"]["correct"] == 0


def test_cluster_backed_only_by_names_is_a_fallback():
    pred = prediction(mentions=[{"mention_id": "P1", "text": "Dan"}, pm("P2", "dead")],   # 'dead': no gold mention
                      coreference_clusters=[{"cluster_id": "C1", "mentions": ["P1", "P2"]}],
                      facts=[{"entity_mention_id": "P2", "property": "status", "value": "dead"}])
    s = score_document_v2(pred, gold())
    assert s["facts"]["tp"] == 1 and s["facts"]["tp_fallback"] == 1
    assert {(m["mention_id"], m["source"]) for m in s["diagnostics"]["fallback_mappings"]} == {
        ("P1", "name"), ("P2", "cluster_name")}


def test_repeated_names_align_by_position_and_nested_mentions_by_span():
    s = score_document_v2(prediction(mentions=[pm("P1", "Ben", nth=1), pm("P2", "his sister")]), gold())
    assert (s["mentions_exact"]["tp"], s["mentions_exact"]["fn"]) == (2, 8)      # M6 and M4, not M2 or M5
    assert s["mention_linking"] == {"correct": 2, "total": 2, "accuracy": 1.0}   # 'his sister' is Anna, not Ben
    s = score_document_v2(prediction(mentions=[pm("P1", "his")]), gold())
    assert s["mention_linking"]["correct"] == 1                                   # the nested 'his' is Ben


def test_entity_mentioned_only_outside_the_region():
    pred = prediction(mentions=[pm("P1", "Carl")],
                      facts=[{"entity_mention_id": "P1", "property": "location", "value": "Far  off"}])
    s = score_document_v2(pred, gold())
    assert s["facts"]["tp"] == 1 and s["facts"]["tp_fallback"] == 0               # aligned to the outside mention
    assert s["mentions_exact"]["fp"] == 0 and s["mentions_exact"]["tp"] == 0      # and not scored as a mention


def test_unresolved_endpoints_are_false_positives():
    pred = prediction(mentions=[pm("P1", "met")],
                      facts=[{"entity_mention_id": "P1", "property": "status", "value": "dead"},
                             {"entity_mention_id": "NOPE", "property": "status", "value": "dead"}])
    s = score_document_v2(pred, gold())
    assert (s["facts"]["tp"], s["facts"]["fp"], s["facts"]["unresolved"]) == (0, 2, 2)


# ---------------------------------------------------------------------------------------------------- coverage, review
def test_pending_items_are_ignored_by_default():
    g = gold()
    s = score_document_v2(gold_as_prediction(g), g)                       # F3 and R3 predicted: ignored
    assert (s["facts"]["tp"], s["facts"]["fp"]) == (2, 0) and (s["relationships"]["tp"], s["relationships"]["fp"]) \
        == (2, 0)
    s = score_document_v2(prediction(), g)                                # not predicted: not missed either
    assert s["facts"]["fn"] == 2 and s["relationships"]["fn"] == 2
    assert s["gold_ignored_pending"] == {"mentions": 0, "facts": 1, "relationships": 1, "quotes": 0}
    g["mentions"][0]["review"] = PENDING                                  # a pending mention: neither tp nor fp
    s = score_document_v2(prediction(mentions=[pm("P1", "Anna")]), g)
    assert (s["mentions_exact"]["tp"], s["mentions_exact"]["fp"], s["mentions_exact"]["fn"]) == (0, 0, 9)


def test_include_pending_counts_drafts_and_is_marked_provisional():
    s = score_document_v2(prediction(), gold(), include_pending=True)
    assert s["provisional"] is True and s["facts"]["fn"] == 3
    assert format_table_v2(micro_average_v2([s])).startswith("PROVISIONAL")
    assert not format_table_v2(score_document_v2(prediction(), gold())).startswith("PROVISIONAL")


def test_partial_coverage_is_recall_only():
    g = gold()
    g["annotation"]["layers"]["mentions"]["coverage"] = "partial"
    s = score_document_v2(prediction(mentions=[pm("P0", "Anna"), pm("P2", "met")]), g)
    m = s["mentions_exact"]
    assert (m["tp"], m["fp"], m["fn"], m["precision"], m["f1"], m["recall"]) == (1, 0, 9, None, None, 0.1)


def test_region_limits_mentions_and_none_coverage_is_excluded():
    s = score_document_v2(prediction(mentions=[pm("P0", "Anna"), pm("P1", "Carl"), pm("P2", "met")]), gold())
    assert (s["mentions_exact"]["tp"], s["mentions_exact"]["fp"], s["mentions_exact"]["fn"]) == (1, 1, 9)
    g = gold()
    g["annotation"]["layers"]["facts"] = {"coverage": "none"}
    s_none = score_document_v2(gold_as_prediction(g), g)
    assert s_none["facts"]["coverage"] == "none" and s_none["facts"]["f1"] is None
    total = micro_average_v2([s_none, score_document_v2(gold_as_prediction(gold()), gold())])
    assert (total["facts"]["tp"], total["facts"]["coverage"], total["facts"]["f1"]) == (2, "exhaustive", 1.0)


def test_cli_scores_only_reviewed_and_adjudicated_chapters(tmp_path, capsys):
    for n, status in [(1, "reviewed"), (2, "adjudicated"), (3, "draft"), (4, "in_review")]:
        g = gold(status)
        g["doc_id"] = f"w/ch{n:02d}"
        (tmp_path / "gold" / "w").mkdir(parents=True, exist_ok=True)
        (tmp_path / "gold" / "w" / f"ch{n:02d}.json").write_text(json.dumps(g), encoding="utf-8")
    pred = gold_as_prediction(gold())
    (tmp_path / "pred" / "w").mkdir(parents=True)
    (tmp_path / "pred" / "w" / "ch01.json").write_text(json.dumps(pred), encoding="utf-8")
    out = tmp_path / "out.json"
    assert main(["score-v2", str(tmp_path / "gold"), "--pred-dir", str(tmp_path / "pred"), "--json", str(out)]) == 0
    result = json.loads(out.read_text(encoding="utf-8"))
    assert [c["doc_id"] for c in result["chapters"]] == ["w/ch01", "w/ch02"] and not result["micro"]["provisional"]
    assert result["chapters"][0]["facts"]["f1"] == 1.0 and result["chapters"][1]["facts"]["recall"] == 0.0
    assert "not reviewed, not scored (2): w/ch03, w/ch04" in capsys.readouterr().out


# ---------------------------------------------------------------------------------------------------- edge cases
def test_zero_denominators():
    empty = gold()
    for k in ("mentions", "quotes", "facts", "relationships"):
        empty[k] = []
    s = score_document_v2(prediction(), empty)
    for m in COUNTS:
        assert (s[m]["precision"], s[m]["recall"], s[m]["f1"]) == (None, None, None), m
    for m in ACCURACIES:
        assert s[m]["accuracy"] is None, m
    assert s["coreference_b3"]["f1"] is None
    s = score_document_v2(prediction(), gold())                                  # gold, nothing predicted
    assert (s["facts"]["precision"], s["facts"]["recall"], s["facts"]["f1"]) == (None, 0.0, 0.0)
    s = score_document_v2(gold_as_prediction(gold()), empty)                     # predictions, no gold
    assert (s["facts"]["precision"], s["facts"]["recall"], s["facts"]["f1"]) == (0.0, None, 0.0)


def test_duplicate_predictions():
    s = score_document_v2(prediction(mentions=[pm("P1", "Anna"), pm("P2", "Anna")]), gold())
    for m in ("mentions_exact", "mentions_overlap", "mentions_typed"):
        assert (s[m]["tp"], s[m]["fp"]) == (1, 1), m                            # a repeated span is wrong
    fact = {"entity_mention_id": "P1", "property": "status", "value": "dead"}
    s = score_document_v2(prediction(mentions=[pm("P1", "Dan")], facts=[fact, dict(fact)]), gold())
    assert (s["facts"]["tp"], s["facts"]["fp"]) == (1, 0)                        # a repeated fact counts once


def test_text_mismatch_is_rejected():
    with pytest.raises(ValueError):
        score_document_v2({"text": "other"}, gold())


# ---------------------------------------------------------------------------------------------------- real gold
@pytest.mark.skipif(not GOLD_DIR.exists(), reason="gold v2 not present")
def test_every_gold_chapter_scores_one_against_itself_and_mutations_fail():
    per_doc, docs = [], []
    for path in sorted(GOLD_DIR.rglob("ch*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        docs.append(doc)
        per_doc.append(score_document_v2(gold_as_prediction(doc), doc, include_pending=True))
    total = micro_average_v2(per_doc)
    for m in COUNTS + B3:
        assert total[m]["f1"] == 1.0, m
    for m in ACCURACIES:
        assert total[m]["accuracy"] == 1.0, m
    doc = next(d for d in docs if d["doc_id"] == "the_mysterious_affair_at_styles/ch01")
    pred = gold_as_prediction(doc)
    pred["mentions"] = pred["mentions"][::2]                                     # half the mentions gone
    keep = {m["mention_id"] for m in pred["mentions"]}
    for c in pred["coreference_clusters"]:
        c["mentions"] = [m for m in c["mentions"] if m in keep]
    pred["relationships"] = [{**r, "predicate": "KNOWS"} for r in pred["relationships"]]
    s = score_document_v2(pred, doc, include_pending=True)
    assert s["mentions_exact"]["recall"] < 0.6 and s["relationships"]["f1"] < 0.5
