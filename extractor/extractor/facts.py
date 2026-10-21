"""
Facts with one open question per chunk to a general instruction model (Qwen3.5 9B, thinking off), replacing NuExtract's
people template. NuExtract's raw answers held 8 of the 28 reviewed gold facts before any filtering; on the reviewed
gold v2 chapters this stage takes facts from F1 0.41 to 0.53 (P 0.73 -> 0.71, R 0.29 -> 0.43), and on four unseen
draft chapters from 0.23 to 0.44 (provisional; runs/2026-10-19_*, experiments/open_facts.py).

The deterministic title facts (`relations.title_facts`) come first; this stage adds to them. Every answer is grounded
by code, and one that fails a check is dropped:
    name      a named or nominal character / organization mention in the chunk, or a first-person pronoun (the
              narrator); never another pronoun ("He" would pick whichever "he" comes first)
    evidence  a quote from the chunk: the model shortens quotes with "...", puts them on one line and straightens the
              quotes, so each piece is looked up in the chunk read the same way
    value     inside the evidence, at most MAX_VALUE_CHARS, and `relations.fact_value` accepts it; a place keeps its
              determiner ("the north of England", as the gold writes places)
    plausible a title is a rank (never Mr/Mrs/Miss), an age has a number, an origin names a place, an occupation is
              not plural ("doctors"); species is asked but never kept ("species: Jew" was answered)
Scene state (location, status) is never kept (`relations.SCENE_STATE`). The worked example is made up
(`relations.EXAMPLE`), never gold text. The model is ORION_FACTS_LLM; without it in Ollama the stage keeps only the
title facts and says so on stderr, so a chapter still extracts.
"""
import json
import os
import re
import sys
import urllib.error
from typing import Any, Callable, Dict, List

from app.contracts.gold import FACT_PROPERTIES
from app.preprocessing import chunk_document, preprocess_chapter
from extractor import relations as R
from extractor.llm import generate
from extractor.mentions import spacy_nlp

MODEL = os.environ.get("ORION_FACTS_LLM", "qwen3.5:9b")
PROPERTIES = [p for p in FACT_PROPERTIES if p not in R.SCENE_STATE]
NEVER_KEPT = {"species"}           # ponytail: keep it with a creature lexicon if a fantasy manuscript needs it
SYSTEM = """You read an excerpt of a novel and list the standing facts it states about its characters.

Properties:
- occupation: a job or trade (nurse, surgeon, barrister, maid). Not a family or social role (wife, friend, gentleman).
- age: how old they are, in the text's words (thirty, about forty, seventy).
- title: a rank written with the name (Sir, Lady, Lord, Colonel, Captain). Never Mr, Mrs or Miss.
- hair_color, eye_color: the colour words only.
- birth_place: where they were born. origin: where they come from.
- species: only for a character who is not human. date_of_birth: only when stated.

Rules:
- Only what the excerpt itself says. No guesses, no world knowledge, nothing about where someone is or how they feel.
- name: the character's name exactly as the excerpt writes it ("Mr. Hale", "Marta"); never a pronoun.
- value: copied from the excerpt, as short as possible.
- evidence: the sentence that states it, copied exactly.
- No fact stated: return {"facts": []}."""
SCHEMA = {"type": "object", "required": ["facts"], "properties": {"facts": {"type": "array", "items": {
    "type": "object", "required": ["name", "property", "value", "evidence"],
    "properties": {"name": {"type": "string"}, "property": {"type": "string", "enum": PROPERTIES},
                   "value": {"type": "string"}, "evidence": {"type": "string"}}}}}}
_FIRST = R.EXAMPLE[:R.EXAMPLE.index(".") + 1]
EXAMPLE_ANSWER = {"facts": [
    {"name": "Marta Lindqvist", "property": "age", "value": "thirty", "evidence": _FIRST},
    {"name": "Marta Lindqvist", "property": "occupation", "value": "nurse", "evidence": _FIRST},
    {"name": "Marta Lindqvist", "property": "hair_color", "value": "red", "evidence": _FIRST},
    {"name": "Tomas", "property": "occupation", "value": "farmhand",
     "evidence": "‘Tomas will be your new farmhand,’ old Mr. Hale told me."}]}

RANKS = {w for w, (prop, _) in R.TITLE_FACTS.items() if prop == "title"}
NUMBER = re.compile(r"\d|\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|"
                    r"sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|"
                    r"hundred|score)", re.IGNORECASE)
PLACES = {"birth_place", "origin"}
DETERMINERS = ("the ", "this ", "that ", "a ", "an ")
QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})


def prompt(text: str) -> str:
    return (f"Example excerpt:\n{R.EXAMPLE}\nExample answer:\n{json.dumps(EXAMPLE_ANSWER, ensure_ascii=False)}\n\n"
            f"Excerpt:\n{text}")


def plausible(prop: str, value: str) -> bool:
    if prop == "title":                                  # "Mrs." and "lady" ("a lady who liked...") were answered
        return value[:1].isupper() and value.rstrip(".").casefold() in RANKS
    if prop == "age":                                    # "child" was answered
        return bool(NUMBER.search(value))
    if prop == "origin":                                 # "native place" was answered
        return any(w[:1].isupper() for w in value.split())
    if prop == "birth_place":                            # "this workhouse", "Derby"
        return any(w[:1].isupper() for w in value.split()) or value.casefold().startswith(DETERMINERS)
    return True


def _flatten(text: str):
    """Case-folded text with straight quotes and every whitespace run as one space, and for each of its characters the
    offset of that character in `text`."""
    out, where = [], []
    for i, c in enumerate(text.translate(QUOTES).casefold()):
        if c.isspace():
            if out and out[-1] == " ":
                continue
            c = " "
        out.append(c)
        where.append(i)
    return "".join(out), where


def locate(evidence: str, value: str, chunk: str) -> int:
    """The value's offset in the chunk, found through the evidence; -1 when the evidence is not a quote from the chunk
    or does not hold the value."""
    flat, where = _flatten(chunk)
    pieces = [x for x in (_flatten(p)[0].strip(" ,;:'\"") for p in re.split(r"\.\.\.|…", evidence)) if x]
    want = _flatten(value)[0]
    if not pieces or not want or any(x not in flat for x in pieces):
        return -1
    for x in pieces:
        if want in x:
            return where[flat.find(x) + x.find(want)]
    return -1


def with_determiner(prop: str, text: str, start: int) -> int:
    if prop in PLACES:
        for d in DETERMINERS:
            if text[max(0, start - len(d)):start].casefold() == d:
                return start - len(d)
    return start


def grounded_facts(doc: Dict[str, Any], ask: Callable[[str, str, Any], Dict[str, Any]], parsed: Any) -> None:
    """Asks `ask(system, user, schema) -> answer` once per chunk and appends the grounded facts to doc["facts"], after
    the ones already there (same entity, property and value are kept once)."""
    document = preprocess_chapter(doc["text"])
    sentences = list(document.iter_sentences())
    groups = R.entities(doc)
    group_of = {m["mention_id"]: k for k, ms in groups.items() for m in ms}
    kind_of = {k: max(set(t := [m["type"] for m in ms]), key=t.count) for k, ms in groups.items()}
    seen = {(group_of[f["entity_mention_id"]], f["property"], f["value"].casefold()) for f in doc["facts"]}

    def add(m: Dict[str, Any], prop: str, value: str) -> None:
        key = (group_of[m["mention_id"]], prop, value.casefold())
        if key not in seen:
            seen.add(key)
            sentence = next(s for s in sentences if s.start <= m["start"] < s.end)
            doc["facts"].append({"fact_id": f"F{len(doc['facts']) + 1}", "property": prop, "value": value,
                                 "entity_mention_id": R.representative(groups[group_of[m["mention_id"]]],
                                                                       sentence)["mention_id"]})

    for chunk in chunk_document(document, max_chars=R.CHUNK_CHARS, overlap_sentences=0):
        names: Dict[str, Dict[str, Any]] = {}
        for m in doc["mentions"]:
            if chunk.start <= m["start"] < chunk.end and kind_of[group_of[m["mention_id"]]] in R.TYPES and (
                    m["mention_kind"] in ("proper", "nominal") or m["text"].casefold() in R.FIRST_PERSON):
                names.setdefault(R.name_key(m["text"]), m)
        if not names:
            continue
        for f in (ask(SYSTEM, prompt(chunk.text), SCHEMA) or {}).get("facts") or []:
            m = names.get(R.name_key(f.get("name") or ""))
            prop, value, evidence = f.get("property"), (f.get("value") or "").strip(), (f.get("evidence") or "").strip()
            if (not m or prop not in PROPERTIES or prop in NEVER_KEPT or not value or len(value) > R.MAX_VALUE_CHARS
                    or not plausible(prop, value)):
                continue
            at = locate(evidence, value, chunk.text)
            if at < 0:
                continue
            start = with_determiner(prop, doc["text"], chunk.start + at)
            span = parsed.char_span(start, chunk.start + at + len(value), alignment_mode="expand")
            if span is None:
                continue
            # a rank (`plausible`) is the whole value; fact_value would drop "Sir" as the modifier of "Sir Tom"
            value = span.text if prop == "title" else R.fact_value(prop, span)
            if value and not (prop == "occupation" and span[-1].tag_ == "NNS"):
                add(m, prop, value)


def facts(doc: Dict[str, Any]) -> None:
    ask = lambda system, user, schema: generate(system, user, schema, 1024, model=MODEL, extra={"think": False})
    try:
        grounded_facts(doc, ask, spacy_nlp()(doc["text"]))
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
        print(f"facts: Ollama has no {MODEL} (ollama pull {MODEL}); only title facts kept", file=sys.stderr)
