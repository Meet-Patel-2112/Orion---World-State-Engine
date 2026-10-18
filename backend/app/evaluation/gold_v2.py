"""
Gold v2 (`orion_gold_v2.schema.json`, repo root): checks a chapter document beyond what the schema can say, and the
chapters of one work against each other. Conventions: docs/gold_v2_guidelines.md.

`doc_errors` reports, besides schema violations:
    - spans outside the text, empty, or with whitespace at an edge; mention / time-expression text unlike its span
    - duplicate ids; references to unknown entity keys, mention ids or event ids
    - a `status` fact without `status_value`, `age_years` on another property, a `value_span` outside its evidence or
      unlike `value`, a relationship from an entity to itself
    - a `source_entity_key` equal to `claimed_by` (a character is not the hearsay source of their own claim)
    - items in a layer whose coverage is `none`, and a layer region outside the text
    - a document marked `reviewed` / `adjudicated` that still has `pending` items
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from app.evaluation.schema import validate

SCHEMA_V2_PATH = Path(__file__).resolve().parents[3] / "orion_gold_v2.schema.json"
LAYERS = ("mentions", "quotes", "events", "facts", "relationships", "temporal_expressions", "temporal_relations")
GOLD_STATUSES = {"accepted", "corrected"}
ID_FIELDS = {"mentions": "mention_id", "quotes": "quote_id", "events": "event_id", "facts": "fact_id",
             "relationships": "relationship_id", "temporal_expressions": "temporal_id",
             "temporal_relations": "temporal_relation_id"}


def load_schema_v2() -> Dict[str, Any]:
    return json.loads(SCHEMA_V2_PATH.read_text(encoding="utf-8"))


def is_gold(item: Dict[str, Any]) -> bool:
    """A person has accepted or corrected it (guidelines §1). Items without a review record are not gold."""
    return item.get("review", {}).get("status") in GOLD_STATUSES


def _span_error(text: str, where: str, start: Any, end: Any) -> Optional[str]:
    if not (isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(text)):
        return f"{where}: span ({start}, {end}) is empty or outside the text (length {len(text)})"
    if text[start].isspace() or text[end - 1].isspace():
        return f"{where}: span ({start}, {end}) has whitespace at an edge: {text[start:end]!r}"
    return None


def _inside(inner: Dict[str, int], outer: Dict[str, int]) -> bool:
    return outer["start"] <= inner["start"] and inner["end"] <= outer["end"]


def doc_errors(doc: Any) -> List[str]:
    """Every problem in one gold v2 chapter document (empty list = valid)."""
    schema = load_schema_v2()
    errors = validate(doc, schema, schema)
    if errors:   # the checks below assume the document's shape
        return [f"schema: {e}" for e in errors]
    text, work = doc["text"], doc["work"]
    expected_id = f"{work['work_id']}/ch{work['chapter_number']:02d}"
    if doc["doc_id"] != expected_id:
        errors.append(f"doc_id {doc['doc_id']!r} should be {expected_id!r}")

    keys = Counter(e["entity_key"] for e in doc["entities"])
    errors += [f"entity_key {k!r} listed {n} times" for k, n in keys.items() if n > 1]

    def known(key: Optional[str], where: str) -> None:
        if key is not None and key not in keys:
            errors.append(f"{where}: unknown entity_key {key!r}")

    for layer, id_field in ID_FIELDS.items():
        counts = Counter(item[id_field] for item in doc[layer])
        errors += [f"{layer}: id {i!r} used {n} times" for i, n in counts.items() if n > 1]

    for m in doc["mentions"]:
        where = f"mention {m['mention_id']}"
        problem = _span_error(text, where, m["start"], m["end"])
        if problem:
            errors.append(problem)
        elif text[m["start"]:m["end"]] != m["text"]:
            errors.append(f"{where}: text {m['text']!r} but the span holds {text[m['start']:m['end']]!r}")
        known(m["entity_key"], where)

    for q in doc["quotes"]:
        where = f"quote {q['quote_id']}"
        for s in q["spans"]:
            problem = _span_error(text, where, s["start"], s["end"])
            if problem:
                errors.append(problem)
        known(q["speaker_entity_key"], where)
        for key in q["addressee_entity_keys"]:
            known(key, where)

    def attribution(item: Dict[str, Any], where: str) -> None:
        known(item.get("claimed_by"), where)
        known(item.get("source_entity_key"), where)
        if item.get("source_entity_key") and item.get("source_entity_key") == item.get("claimed_by"):
            errors.append(f"{where}: source_entity_key equals claimed_by; leave the source unset")

    mention_ids = {m["mention_id"] for m in doc["mentions"]}
    for ev in doc["events"]:
        where = f"event {ev['event_id']}"
        problem = _span_error(text, where, ev["start"], ev["end"])
        if problem:
            errors.append(problem)
        errors += [f"{where}: unknown mention {p['mention_id']!r}" for p in ev["participants"]
                   if p["mention_id"] not in mention_ids]

    for f in doc["facts"]:
        where = f"fact {f['fact_id']}"
        known(f["entity_key"], where)
        attribution(f, where)
        problem = _span_error(text, f"{where} evidence", f["evidence"]["start"], f["evidence"]["end"])
        if problem:
            errors.append(problem)
        if f["property"] == "status" and "status_value" not in f:
            errors.append(f"{where}: a status fact needs status_value")
        if f["property"] != "status" and "status_value" in f:
            errors.append(f"{where}: status_value on a {f['property']} fact")
        if "age_years" in f and f["property"] != "age":
            errors.append(f"{where}: age_years on a {f['property']} fact")
        vs = f.get("value_span")
        if vs:
            if not problem and not _inside(vs, f["evidence"]):
                errors.append(f"{where}: value_span ({vs['start']}, {vs['end']}) is outside the evidence")
            elif text[vs["start"]:vs["end"]] != f["value"]:
                errors.append(f"{where}: value {f['value']!r} but value_span holds {text[vs['start']:vs['end']]!r}")

    for r in doc["relationships"]:
        where = f"relationship {r['relationship_id']}"
        known(r["subject_entity_key"], where)
        known(r["object_entity_key"], where)
        attribution(r, where)
        if r["subject_entity_key"] == r["object_entity_key"]:
            errors.append(f"{where}: an entity related to itself")
        problem = _span_error(text, f"{where} evidence", r["evidence"]["start"], r["evidence"]["end"])
        if problem:
            errors.append(problem)

    for t in doc["temporal_expressions"]:
        where = f"temporal expression {t['temporal_id']}"
        problem = _span_error(text, where, t["start"], t["end"])
        if problem:
            errors.append(problem)
        elif text[t["start"]:t["end"]] != t["text"]:
            errors.append(f"{where}: text {t['text']!r} but the span holds {text[t['start']:t['end']]!r}")
    event_ids = {ev["event_id"] for ev in doc["events"]}
    for tr in doc["temporal_relations"]:
        for field in ("source_event_id", "target_event_id"):
            if tr[field] not in event_ids:
                errors.append(f"temporal relation {tr['temporal_relation_id']}: unknown event {tr[field]!r}")

    for layer, scope in doc["annotation"]["layers"].items():
        if scope["coverage"] == "none" and doc[layer]:
            errors.append(f"layer {layer} has coverage none but {len(doc[layer])} items")
        region = scope.get("region")
        if region and not (0 <= region["start"] < region["end"] <= len(text)):
            errors.append(f"layer {layer}: region ({region['start']}, {region['end']}) is outside the text")

    if doc["annotation"]["status"] in ("reviewed", "adjudicated"):
        pending = sum(1 for layer in LAYERS for item in doc[layer] if not is_gold(item))
        pending += sum(1 for e in doc["entities"] if not is_gold(e))
        if pending:
            errors.append(f"annotation.status is {doc['annotation']['status']} but {pending} items are not reviewed")
    return errors


def work_errors(docs: Iterable[Dict[str, Any]]) -> List[str]:
    """An entity_key must mean the same entity in every chapter of a work: same name and type."""
    seen: Dict[tuple, Dict[str, Any]] = {}
    errors = []
    for doc in docs:
        for e in doc.get("entities", []):
            ident = (doc["work"]["work_id"], e["entity_key"])
            first = seen.setdefault(ident, {**e, "doc_id": doc["doc_id"]})
            for field in ("name", "type"):
                if e[field] != first[field]:
                    errors.append(f"{ident[0]}: {e['entity_key']} is {field} {first[field]!r} in {first['doc_id']} "
                                  f"but {e[field]!r} in {doc['doc_id']}")
    return errors
