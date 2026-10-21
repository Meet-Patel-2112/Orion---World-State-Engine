"""The facts stage: open answers from the model, grounded by code (extractor/facts.py)."""
from extractor import facts as F
from extractor.mentions import spacy_nlp
from extractor.pipeline import LISTS

TEXT = ("I am Twenty four. Old Mr. Hale, a grey-haired\nwoman's husband, was a farmer from the north of England, "
        "and Sir Tom was a doctors' friend. Dan, a child, said \u2018hello\u2019 to Mrs. Ames.")


def mention(mid, s, kind, t="character"):
    i = TEXT.index(s)
    return {"mention_id": mid, "text": s, "type": t, "mention_kind": kind, "start": i, "end": i + len(s)}


def doc():
    ms = [mention("M1", "I", "pronominal"), mention("M2", "Mr. Hale", "proper"), mention("M3", "Tom", "proper"),
          mention("M4", "Dan", "proper"), mention("M5", "he", "pronominal"), mention("M6", "Mrs. Ames", "proper")]
    return {"text": TEXT, **{k: [] for k in LISTS}, "mentions": ms, "coreference_clusters": []}


def test_answers_are_kept_only_when_the_text_states_them(monkeypatch):
    farmer = "Old Mr. Hale, a grey-haired woman's husband, was a farmer from the north of England, and Sir Tom..."
    answer = {"facts": [
        {"name": "I", "property": "age", "value": "Twenty four", "evidence": "I am Twenty four."},      # the narrator
        {"name": "Mr. Hale", "property": "occupation", "value": "farmer", "evidence": farmer},           # one line, ...
        {"name": "Hale", "property": "origin", "value": "north of England", "evidence": farmer},         # + "the"
        {"name": "Tom", "property": "title", "value": "Sir", "evidence": "and Sir Tom was a doctors' friend."},
        {"name": "Mrs. Ames", "property": "title", "value": "Mrs.", "evidence": "said hello to Mrs. Ames."},  # honorific
        {"name": "Dan", "property": "age", "value": "child", "evidence": "Dan, a child, said"},          # no number
        {"name": "Dan", "property": "species", "value": "child", "evidence": "Dan, a child, said"},      # never kept
        {"name": "he", "property": "occupation", "value": "farmer", "evidence": farmer},                # a pronoun
        {"name": "Tom", "property": "occupation", "value": "doctors", "evidence": "Sir Tom was a doctors' friend."},
        {"name": "Dan", "property": "occupation", "value": "baker", "evidence": "Dan was a baker."}]}    # not a quote
    d = doc()
    F.grounded_facts(d, lambda system, user, schema: answer, spacy_nlp()(TEXT))
    assert [(f["entity_mention_id"], f["property"], f["value"]) for f in d["facts"]] == [
        ("M1", "age", "Twenty four"), ("M2", "occupation", "farmer"), ("M2", "origin", "the north of England"),
        ("M3", "title", "Sir")]


def test_a_missing_model_keeps_the_title_facts(monkeypatch, capsys):
    import urllib.error

    def missing(*a, **k):
        raise urllib.error.HTTPError("http://x", 404, "model not found", {}, None)
    monkeypatch.setattr(F, "generate", missing)
    d = doc()
    d["facts"] = [{"fact_id": "F1", "property": "title", "value": "Sir", "entity_mention_id": "M3"}]
    F.facts(d)
    assert len(d["facts"]) == 1 and "ollama pull" in capsys.readouterr().err
