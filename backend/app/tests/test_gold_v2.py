"""Gold v2: the validator's checks beyond the schema, and the PDNC converter (docs/gold_v2_guidelines.md)."""
import copy
import json

import pytest

from app.evaluation.gold_v2 import SCHEMA_V2_PATH, doc_errors, is_gold, work_errors
from app.evaluation.pdnc import Characters, convert_chapter, entity_key, restore_from_reference, split_chapters

pytestmark = pytest.mark.skipif(not SCHEMA_V2_PATH.exists(), reason="orion_gold_v2.schema.json not present")

TEXT = '"My dear Mr. Bennet," said his lady to him one day. Mr. Bennet replied that he had not.'


def sp(phrase):
    s = TEXT.index(phrase)
    return {"start": s, "end": s + len(phrase)}


def doc():
    return {
        "schema_version": "2.0", "doc_id": "pride_and_prejudice/ch01",
        "work": {"work_id": "pride_and_prejudice", "title": "Pride and Prejudice", "author": "Jane Austen",
                 "chapter_number": 1, "source": {"corpus": "pdnc", "license": "CC-BY 4.0"}},
        "text": TEXT,
        "annotation": {"guidelines_version": "2.0", "status": "draft",
                       "layers": {"mentions": {"coverage": "exhaustive"}, "quotes": {"coverage": "exhaustive"},
                                  "events": {"coverage": "none"}, "facts": {"coverage": "exhaustive"},
                                  "relationships": {"coverage": "exhaustive"},
                                  "temporal_expressions": {"coverage": "none"},
                                  "temporal_relations": {"coverage": "none"}}},
        "entities": [{"entity_key": "mr_bennet", "name": "Mr. Bennet", "type": "character"},
                     {"entity_key": "mrs_bennet", "name": "Mrs. Bennet", "type": "character"}],
        "mentions": [{"mention_id": "M1", "text": "Mr. Bennet", "type": "character", "mention_kind": "proper",
                      "entity_key": "mr_bennet", **sp("Mr. Bennet")}],
        "quotes": [{"quote_id": "Q1", "spans": [sp("My dear Mr. Bennet,")], "speaker_entity_key": "mrs_bennet",
                    "addressee_entity_keys": ["mr_bennet"], "quote_type": "anaphoric",
                    "review": {"origin": "pdnc", "status": "accepted"}}],
        "events": [], "temporal_expressions": [], "temporal_relations": [],
        "facts": [{"fact_id": "F1", "entity_key": "mr_bennet", "property": "status", "value": "replied",
                   "status_value": "ALIVE", "evidence": sp("Mr. Bennet replied that he had not."),
                   "value_span": sp("replied"), "assertion": "asserted"}],
        "relationships": [{"relationship_id": "R1", "subject_entity_key": "mrs_bennet", "predicate": "MARRIED_TO",
                           "object_entity_key": "mr_bennet", "evidence": sp("said his lady to him one day"),
                           "assertion": "asserted", "review": {"origin": "claude_draft", "status": "pending"}}],
    }


def test_a_well_formed_document_has_no_errors():
    assert doc_errors(doc()) == []


@pytest.mark.parametrize("break_it, expected", [
    (lambda d: d["mentions"][0].update(text="Mrs. Bennet"), "but the span holds 'Mr. Bennet'"),
    (lambda d: d["mentions"][0].update(start=TEXT.index(" Mr."), end=TEXT.index(" Mr.") + 11, text=" Mr. Bennet"),
     "whitespace at an edge"),
    (lambda d: d["quotes"][0].update(speaker_entity_key="lizzy"), "unknown entity_key 'lizzy'"),
    (lambda d: d["facts"][0].pop("status_value"), "a status fact needs status_value"),
    (lambda d: d["facts"][0].update(value_span=sp("lady")), "outside the evidence"),
    (lambda d: d["relationships"][0].update(object_entity_key="mrs_bennet"), "an entity related to itself"),
    (lambda d: d["annotation"]["layers"]["facts"].update(coverage="none"), "layer facts has coverage none"),
    (lambda d: d["annotation"].update(status="reviewed"), "items are not reviewed"),
    (lambda d: d.update(doc_id="pride_and_prejudice/ch02"), "should be 'pride_and_prejudice/ch01'"),
    (lambda d: d["relationships"][0].update(predicate="CHILD_OF"), "schema:"),
    (lambda d: d["relationships"][0].update(claimed_by="mrs_bennet", source_entity_key="mrs_bennet"),
     "source_entity_key equals claimed_by"),
    (lambda d: d["facts"][0].update(source_entity_key="mrs_long"), "unknown entity_key 'mrs_long'"),
])
def test_each_violation_is_reported(break_it, expected):
    d = doc()
    break_it(d)
    assert any(expected in e for e in doc_errors(d)), doc_errors(d)


def test_only_reviewed_items_are_gold():
    d = doc()
    assert is_gold(d["quotes"][0]) and not is_gold(d["relationships"][0]) and not is_gold(d["facts"][0])


def test_an_entity_key_must_mean_the_same_entity_in_every_chapter():
    a, b = doc(), copy.deepcopy(doc())
    b["doc_id"], b["work"]["chapter_number"] = "pride_and_prejudice/ch03", 3
    assert work_errors([a, b]) == []
    b["entities"][0]["name"] = "Mr. Collins"
    assert "mr_bennet is name 'Mr. Bennet'" in work_errors([a, b])[0]


# ---------------------------------------------------------------------------------------------------- converter
NOVEL = ("Title\n\nCHAPTER I.\n\n\"Hello there,\" said Jane. \"Lizzy, come. \"\n\n"
         "CHAPTER I.\nVOLUME TWO OPENS\n\n\"I wo n t,\" said Lizzy.\n")


def test_chapters_are_numbered_by_position_even_when_the_numerals_restart():
    bounds = split_chapters(NOVEL)
    assert len(bounds) == 2
    assert NOVEL[bounds[1][0]:bounds[1][1]].startswith("CHAPTER I.\nVOLUME TWO") and not NOVEL[bounds[0][1] - 1].isspace()


def test_restore_puts_back_only_what_a_matching_line_proves():
    pdnc = "It s Kemp s house.\nA line PDNC changed  oddly."
    reference = "It’s Kemp’s house.\r\nA line PDNC changed — differently."
    text, restored, unmatched = restore_from_reference(pdnc, reference)
    assert text == "It's Kemp's house.\nA line PDNC changed  oddly." and restored == 2
    assert unmatched == ["A line PDNC changed  oddly."] and len(text) == len(pdnc)


ROWS = [{"Character ID": "0", "Main Name": "Jane", "Aliases": "{'Jane', 'Miss Bennet'}"},
        {"Character ID": "1", "Main Name": "Elizabeth", "Aliases": "{'Elizabeth', 'Lizzy'}"},
        {"Character ID": "2", "Main Name": "Charlotte Lucas", "Aliases": "{'Charlotte', 'Lady Lucas'}"},
        {"Character ID": "3", "Main Name": "_group", "Aliases": "['_group']"}]
CONFIG = {"work_id": "pride_and_prejudice", "title": "Pride and Prejudice", "author": "Jane Austen",
          "entities": {"Elizabeth": {"key": "elizabeth_bennet", "name": "Elizabeth Bennet"},
                       "Charlotte Lucas": {"drop_aliases": ["Lady Lucas"]}},
          "extra_entities": [{"key": "lady_lucas", "name": "Lady Lucas"}],
          "name_map": {"Lady Lucas": "lady_lucas"}}


def test_names_resolve_through_fixes_main_names_and_unique_aliases():
    chars = Characters(ROWS, CONFIG)
    assert chars.resolve("Lizzy") == ("elizabeth_bennet", None)
    assert chars.resolve("Lady Lucas") == ("lady_lucas", None)          # not Charlotte, as PDNC has it
    assert chars.resolve("_group") == (None, None)
    assert chars.resolve("Mr. Nobody")[1] and entity_key("Mr. Collins' Father") == "mr_collins_father"


def quote_row(qid, quote_text, speaker, addressees, spans_with_ws, mentions=()):
    subs = [NOVEL[s:e] for s, e in spans_with_ws]
    return {"quoteID": qid, "quoteText": quote_text, "subQuotationList": repr(subs),
            "quoteByteSpans": repr([list(x) for x in spans_with_ws]), "speaker": speaker,
            "addressees": repr(addressees), "quoteType": "Explicit",
            "mentionTextsList": repr([[m[0] for m in mentions]] + [[] for _ in subs[1:]]),
            "mentionSpansList": repr([[list(m[1]) for m in mentions]] + [[] for _ in subs[1:]]),
            "mentionEntitiesList": repr([[m[2] for m in mentions]] + [[] for _ in subs[1:]])}


def test_a_chapter_converts_to_a_valid_draft_with_trimmed_spans_and_local_offsets():
    hello = NOVEL.index("Hello there,")
    lizzy = NOVEL.index("Lizzy, come.")
    rows = [quote_row("Q0", "Hello there,", "Jane", ["Elizabeth"], [(hello, hello + 12)]),
            # PDNC-style stray space at the end of the span, a group addressee, and a two-person mention
            quote_row("Q1", "Lizzy, come. ", "Jane", ["Elizabeth", "_group"], [(lizzy, lizzy + 13)],
                      mentions=[("Lizzy", (lizzy, lizzy + 5), ["Elizabeth"]),
                                ("you", (lizzy, lizzy + 5), ["Elizabeth", "Jane"])])]
    bounds = split_chapters(NOVEL)[0]
    d, issues = convert_chapter(NOVEL, rows, Characters(ROWS, CONFIG), CONFIG, 1, bounds, "abc1234")
    assert issues == [] and doc_errors(d) == []
    chapter = d["text"]
    q1 = d["quotes"][1]
    assert chapter[q1["spans"][0]["start"]:q1["spans"][0]["end"]] == "Lizzy, come."      # trailing space trimmed
    assert q1["speaker_entity_key"] == "jane" and q1["addressee_entity_keys"] == ["elizabeth_bennet"]
    assert [m["entity_key"] for m in d["mentions"]] == ["elizabeth_bennet"]             # the 2-person mention skipped
    assert {e["entity_key"] for e in d["entities"]} == {"jane", "elizabeth_bennet"}
    assert d["annotation"]["layers"]["quotes"]["coverage"] == "exhaustive"
    assert json.loads(json.dumps(d)) == d


def test_a_span_whose_text_differs_from_pdnc_is_dropped_and_reported():
    hello = NOVEL.index("Hello there,")
    row = quote_row("Q0", "Goodbye", "Jane", [], [(hello, hello + 12)])
    row["subQuotationList"] = repr(["Goodbye"])
    d, issues = convert_chapter(NOVEL, [row], Characters(ROWS, CONFIG), CONFIG, 1, split_chapters(NOVEL)[0], "abc")
    assert d["quotes"] == [] and "dropped" in issues[0]
