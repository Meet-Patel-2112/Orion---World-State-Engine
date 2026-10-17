"""Closed-question experiment harness (experiments/closed.py): caching, parsing, `none`, evidence preservation."""
import json

from experiments.closed import (Chapter, MeteredLLM, _keep_fact, answer_value, locate, pair_windows, parse_relation,
                                rel_options, run_facts, run_rels)

TEXT = "Anna Bell was a nurse. Ben worked for Anna Bell. Later, Ben left the farm."


def mention(mid, surface, kind="proper", typ="character", nth=0):
    s = -1
    for _ in range(nth + 1):
        s = TEXT.index(surface, s + 1)
    return {"mention_id": mid, "text": surface, "type": typ, "mention_kind": kind, "start": s, "end": s + len(surface)}


def upstream():
    return {"text": TEXT, "mentions": [mention("M1", "Anna Bell"), mention("M2", "Ben"), mention("M3", "Anna Bell", nth=1),
                                       mention("M4", "Ben", nth=1), mention("M5", "the farm", "nominal", "location")],
            "coreference_clusters": [{"cluster_id": "C1", "mentions": ["M1", "M3"]},
                                     {"cluster_id": "C2", "mentions": ["M2", "M4"]}],
            "facts": [], "relationships": []}


class FakeOllama:
    def __init__(self, answer):
        self.answer, self.calls = answer, []

    def __call__(self, path, body, timeout):
        self.calls.append(body)
        content = self.answer(body) if callable(self.answer) else self.answer
        return {"message": {"content": json.dumps(content)}, "prompt_eval_count": 120, "eval_count": 7,
                "total_duration": 250_000_000, "done_reason": "stop"}


def test_metered_cache_records_cost_and_replays(tmp_path):
    fake = FakeOllama({"x": "y"})
    call = MeteredLLM(tmp_path / "c.json", fake)
    first, again = call("s", "u"), call("s", "u")
    assert first == again == {"answer": {"x": "y"}, "cut_off": False, "prompt_tokens": 120, "output_tokens": 7,
                              "seconds": 0.25}
    assert (call.hits, call.misses, len(fake.calls)) == (1, 1, 1)
    assert fake.calls[0]["options"] == {"temperature": 0, "num_ctx": 4096, "num_predict": 1024}   # llm.generate's body
    replay = MeteredLLM(tmp_path / "c.json", FakeOllama(lambda b: 1 / 0))       # a cached call never reaches the model
    assert replay("s", "u")["answer"] == {"x": "y"}


def test_cut_off_replies_are_kept_as_no_answer(tmp_path):
    class Cut(FakeOllama):
        def __call__(self, path, body, timeout):
            return {**super().__call__(path, body, timeout), "done_reason": "length"}
    assert MeteredLLM(tmp_path / "c.json", Cut({"x": 1}))("s", "u")["answer"] is None


def test_none_answers():
    for v in (None, "", "  ", "none", "None.", "null", "N/A", "unknown", 3, ["nurse"]):
        assert answer_value(v) is None, v
    assert answer_value("  a   nurse. ") == "a nurse"


def test_locate_preserves_chapter_offsets():
    ch = Chapter(upstream())
    s, a, b = locate("A NURSE", ch.sentences)
    assert TEXT[a:b] == "a nurse" and s.text == "Anna Bell was a nurse."
    assert locate("a doctor", ch.sentences) is None


def test_keep_fact_drops_values_not_in_the_context_and_keeps_evidence():
    ch, log = Chapter(upstream()), []
    group = ch.group_of["M1"]
    window = [ch.sentences[i] for i in ch.mentioned(group)]
    assert _keep_fact(ch, group, "occupation", "doctor", window, log, "t") == [] and log[-1]["result"] == "invalid"
    assert _keep_fact(ch, group, "occupation", None, window, log, "t") == [] and log[-1]["result"] == "none"
    [fact] = _keep_fact(ch, group, "occupation", "Nurse", window, log, "t")
    assert fact["value"] == "nurse" and fact["entity_mention_id"] == "M1"           # the source's own characters
    assert TEXT[fact["evidence"]["start"]:fact["evidence"]["end"]] == "Anna Bell was a nurse."
    assert log[-1]["value_span"] == {"start": TEXT.index("nurse"), "end": TEXT.index("nurse") + 5}


def test_relation_options_and_parsing_keep_direction():
    opts = rel_options("Ben", "Anna Bell", "character", "character")
    assert parse_relation({"q": "Ben works for Anna Bell"}, "q", opts) == ("WORKS_FOR", True)
    assert parse_relation({"q": ["Anna Bell works for Ben"]}, "q", opts) == ("WORKS_FOR", False)
    assert parse_relation({"q": "none"}, "q", opts) is None
    assert parse_relation({"q": "Ben loves Anna Bell"}, "q", opts) is None              # not an offered option
    assert parse_relation("not a dict", "q", opts) is None
    loc = rel_options("Ben", "the farm", "character", "location")
    assert [p for _, p, _ in loc] == ["OWNS"] and loc[0][0] == "Ben owns the farm"


def test_run_rels_and_facts_end_to_end_with_a_fake_model(tmp_path):
    ch = Chapter(upstream())
    ben, anna = ch.group_of["M2"], ch.group_of["M1"]
    assert pair_windows(ch, ben, anna)[0] == [ch.sentence_index(TEXT.index("Ben worked"))]

    def answer(body):
        user = body["messages"][1]["content"]
        context = user.split("# Context:\n")[1]
        if "How are" in user:
            return ({"How are Ben and Anna Bell related?": "Ben works for Anna Bell", "evidence": "worked for Anna Bell"}
                    if "worked for" in context else {"How are Ben and Anna Bell related?": "none", "evidence": None})
        return {"occupation of Anna Bell": "nurse"} if "occupation of Anna Bell" in user else {}

    log = []
    rels = run_rels(ch, MeteredLLM(tmp_path / "r.json", FakeOllama(answer)), [(ben, anna)], log, "t")
    assert [(r["predicate"], r["subject_mention_id"], r["object_mention_id"]) for r in rels] == [("WORKS_FOR", "M2", "M3")]
    assert TEXT[rels[0]["evidence"]["start"]:rels[0]["evidence"]["end"]] == "worked for Anna Bell"
    facts = run_facts(ch, MeteredLLM(tmp_path / "f.json", FakeOllama(answer)), log := [])
    assert [(f["property"], f["value"]) for f in facts] == [("occupation", "nurse")]
    assert {e["result"] for e in log} == {"kept", "none"}
