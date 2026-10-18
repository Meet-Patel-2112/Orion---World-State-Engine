"""
Where a contradiction comes from, and whether the author already rejected it.

- `sources_for`: each side of a contradiction (old/new fact or relationship version, or the two events) located in its
  chapter's current text: chapter, line, the sentence, and the span of the conflicting words, so the UI can link
  straight to it. The versions store their chapter but no offsets (no schema change, SPLIT.md Rule S.1), so the
  sentence is found by text: the one that holds the value and, preferably, the entity's name.
- `claim_signature`: what a contradiction is about, independent of version ids, so a contradiction the author rejected
  is not raised again when a later chapter states the same thing.
"""
import re
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.contracts.normalization import normalize_entity_name
from app.models.chapter import Chapter
from app.models.chapter_version import ChapterVersion
from app.models.contradiction import Contradiction
from app.models.entity import Entity
from app.models.event import Event
from app.models.fact import FactVersion
from app.models.relationship import RelationshipVersion
from app.preprocessing import preprocess_chapter
from app.utils.file_handler import read_file_text


def _names(entity: Optional[Entity]) -> List[str]:
    if entity is None:
        return []
    names = [entity.canonical_name, *(a.alias for a in entity.aliases)]
    names += [normalize_entity_name(n) for n in names]          # "Mr. Bennet" is also written "Bennet"
    return sorted({n for n in names if n}, key=len, reverse=True)


def _find(text: str, needle: str, start: int = 0, end: Optional[int] = None) -> Optional[Tuple[int, int]]:
    m = re.compile(r"(?<!\w)" + re.escape(needle) + r"(?!\w)", re.IGNORECASE).search(text, start, end or len(text))
    return (m.start(), m.end()) if m else None


def _current_text(db: Session, chapter: Chapter) -> Optional[str]:
    version = db.query(ChapterVersion).filter(ChapterVersion.chapter_id == chapter.id,
                                              ChapterVersion.is_current == True).first()  # noqa: E712
    try:
        return read_file_text(version.content_path) if version and version.content_path else None
    except (FileNotFoundError, OSError):
        return None


def locate(text: str, values: List[str], names: List[str]) -> Optional[Dict[str, Any]]:
    """The sentence that states `values` (all of them if possible) about one of `names`, and the span to highlight:
    the first value found, else the name."""
    best = None
    for s in preprocess_chapter(text).iter_sentences():
        hits = [h for v in values if v and (h := _find(text, v, s.start, s.end))]
        named = next((h for n in names if (h := _find(text, n, s.start, s.end))), None)
        score = (len(hits), named is not None)
        if (hits or named) and (best is None or score > best[0]):
            best = (score, s, hits[0] if hits else named)
        if best and best[0] == (len([v for v in values if v]), True):
            break                                                  # every value and a name: can't do better
    if best is None:
        return None
    _, s, (a, b) = best
    return {"start": a, "end": b, "sentence_start": s.start, "sentence_end": s.end,
            "line": text.count("\n", 0, a) + 1, "snippet": s.text.strip(), "highlight": text[a:b]}


def _source(db: Session, side: str, chapter: Optional[Chapter], value: str, values: List[str],
            names: List[str]) -> Dict[str, Any]:
    out = {"side": side, "value": value, "chapter_id": None, "chapter_number": None, "chapter_title": None,
           "manuscript_id": None, "line": None, "start": None, "end": None, "snippet": None, "highlight": value}
    if chapter is None:
        out["label"] = "Added manually"                            # no chapter: the author entered it
        return out
    out.update(chapter_id=chapter.id, chapter_number=chapter.chapter_number, chapter_title=chapter.title,
               manuscript_id=chapter.manuscript_id, label=f"Chapter {chapter.chapter_number}")
    text = _current_text(db, chapter)
    found = locate(text, values, names) if text else None
    if found:
        out.update(found)
        out["label"] = f"Chapter {chapter.chapter_number} · line {found['line']}"
    return out


def sources_for(db: Session, con: Contradiction) -> List[Dict[str, Any]]:
    sources = []
    for side, vid in (("old", con.old_fact_version_id), ("new", con.new_fact_version_id)):
        fv = db.get(FactVersion, vid) if vid else None
        if fv is not None:
            value = "" if fv.value is None else str(fv.value)
            sources.append(_source(db, side, fv.chapter, value, [value], _names(fv.fact.entity)))
    for side, vid in (("old", con.old_relationship_version_id), ("new", con.new_relationship_version_id)):
        rv = db.get(RelationshipVersion, vid) if vid else None
        if rv is not None:
            rel = rv.relationship
            src, dst = _names(rel.source_entity), _names(rel.target_entity)
            # The sentence naming both people; highlight the other one
            value = f"{rel.source_entity.canonical_name} {rv.relationship_type} {rel.target_entity.canonical_name}"
            sources.append(_source(db, side, rv.chapter, value, dst[:1] + src[:1], src + dst))
    for side, eid in (("a", con.event_id_a), ("b", con.event_id_b)):
        ev = db.get(Event, eid) if eid else None
        if ev is not None:
            words = ev.description.strip().rstrip(".")
            sources.append(_source(db, side, ev.chapter, ev.description, [words, words[:60]], []))
    return sources


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value)).strip().casefold()


def claim_signature(db: Session, *, old_fact_version_id=None, new_fact_version_id=None,
                    old_relationship_version_id=None, new_relationship_version_id=None,
                    event_id_a=None, event_id_b=None, **_) -> Optional[Tuple]:
    """What the contradiction is about: the fact and its two values, the pair and its two types, or the two events."""
    fvs = [db.get(FactVersion, v) for v in (old_fact_version_id, new_fact_version_id) if v]
    if fvs and all(fvs):
        return ("fact", fvs[0].fact_id, frozenset(_norm(f.value) for f in fvs))
    rvs = [db.get(RelationshipVersion, v) for v in (old_relationship_version_id, new_relationship_version_id) if v]
    if rvs and all(rvs):
        pairs = frozenset(frozenset((r.relationship.source_entity_id, r.relationship.target_entity_id)) for r in rvs)
        return ("relationship", pairs, frozenset(_norm(r.relationship_type) for r in rvs))
    evs = [db.get(Event, e) for e in (event_id_a, event_id_b) if e]
    if evs and all(evs):
        return ("event", frozenset(_norm(e.description) for e in evs))
    return None


def rejected_signatures(db: Session, world_id: str) -> set:
    rows = db.query(Contradiction).filter(Contradiction.world_id == world_id,
                                          Contradiction.status == "DISMISSED").all()
    return {sig for c in rows if (sig := claim_signature(
        db, old_fact_version_id=c.old_fact_version_id, new_fact_version_id=c.new_fact_version_id,
        old_relationship_version_id=c.old_relationship_version_id,
        new_relationship_version_id=c.new_relationship_version_id,
        event_id_a=c.event_id_a, event_id_b=c.event_id_b))}
