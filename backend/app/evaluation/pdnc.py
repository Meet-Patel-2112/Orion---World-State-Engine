"""
Project Dialogism Novel Corpus (PDNC, CC-BY 4.0) -> gold v2 chapter drafts (docs/gold_v2_guidelines.md §10).

A work's `work.json` names the PDNC folder, the chapters to convert, and fixes to PDNC's character list. For each
chapter the converter writes the chapter text, the characters it refers to, every quote with speaker and addressees,
and the character mentions PDNC marks inside quotes. It never writes facts or relationships (the drafting pass does)
and repairs only what it can verify, reporting the rest as issues:
    - chapters are numbered by position: Pride and Prejudice restarts its numerals in each volume
    - quote and mention spans are trimmed of whitespace PDNC sometimes includes at an edge, and checked against
      PDNC's own text; a span whose text still differs is dropped
    - a name resolves through work.json's `name_map`, then PDNC main names, then an alias that names one character
    - `_group` and `_unknowable` speakers become a null speaker; a mention of several characters ("you" said to two
      people) is skipped, since a gold mention has one entity
    - with a reference edition, characters PDNC replaced by spaces are restored, line by line, only on lines that
      match that edition exactly. PDNC did this two ways: one space per character (The Invisible Man, mode "char")
      and one space per UTF-8 byte (The Mysterious Affair at Styles, mode "bytes": an em dash became three spaces).
      Every PDNC span is moved through the resulting offset map. Spans are still trimmed and checked on PDNC's own
      text (a stray edge space that was really an em dash stays outside the span); an elision apostrophe that starts
      a quote ("'Ed or no 'ed") is put back inside it
"""
from __future__ import annotations

import ast
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

PDNC_URL = "https://github.com/Priya22/project-dialogism-novel-corpus"
LICENSE = "Annotations: CC-BY 4.0 (PDNC, Vishnubhotla, Hammond and Hirst 2022); text: public domain"
CHAPTER_HEADING = re.compile(r"(?m)^[ \t]*CHAPTER [IVXLC]+\b")
SPECIAL_SPEAKERS = {"_group", "_unknowable"}
QUOTE_TYPES = {"Explicit": "explicit", "Anaphoric": "anaphoric", "Implicit": "implicit"}
PRONOUNS = {"i", "me", "my", "mine", "myself", "we", "us", "our", "ours", "ourselves", "you", "your", "yours",
            "yourself", "yourselves", "he", "him", "his", "himself", "she", "her", "hers", "herself", "they", "them",
            "their", "theirs", "themselves", "thee", "thou", "thy", "thine"}
MENTION_REGION_WORDS = 2000    # mentions are exhaustive over about the first 2,000 words (guidelines §3)
SPACE_STANDINS = "‘’"   # PDNC turned these into spaces; restored as a straight apostrophe


def entity_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def split_chapters(text: str) -> List[Tuple[int, int]]:
    """(start, end) of each chapter, numbered by position (index 0 is chapter 1); trailing whitespace excluded."""
    starts = [m.start() for m in CHAPTER_HEADING.finditer(text)]
    bounds = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        bounds.append((start, start + len(text[start:end].rstrip())))
    return bounds


def _pdnc_form(c: str, mode: str) -> str:
    """What PDNC's text has in place of the edition's character `c`."""
    if c in "\u201c\u201d":
        return '"'
    if mode == "bytes" and c == "\u2019":
        return "'"
    if ord(c) < 128:
        return c
    return " " * (len(c.encode("utf-8")) if mode == "bytes" else 1)


def restore_from_reference(text: str, reference: str, mode: str = "char") -> Tuple[str, int, List[str], List[int]]:
    """Restore characters PDNC replaced by spaces. Returns (text, characters restored, lines left as they were,
    offset map). offset_map[p] is the restored-text index of the character at PDNC offset p (len(text) + 1 entries);
    a span (s, e) moves to (offset_map[s], offset_map[e - 1] + 1)."""
    by_pdnc_form: Dict[str, set] = {}
    for line in reference.replace("\r\n", "\n").split("\n"):
        by_pdnc_form.setdefault("".join(_pdnc_form(c, mode) for c in line), set()).add(line)
    out: List[str] = []
    offset_map: List[int] = []
    restored, unmatched, q = 0, [], 0
    for line in text.split("\n"):
        if out:
            offset_map.append(q)        # the newline
            q += 1
        candidates = by_pdnc_form.get(line, set())
        if len(candidates) == 1:
            pieces = []
            for c in next(iter(candidates)):
                form = _pdnc_form(c, mode)
                if ord(c) >= 128 and not form.strip():
                    pieces.append("'" if c in SPACE_STANDINS else c)
                    restored += 1
                else:
                    pieces.append(form)
                offset_map.extend([q] * len(form))
                q += 1
            out.append("".join(pieces))
        else:
            if line.strip():
                unmatched.append(line)
            offset_map.extend(range(q, q + len(line)))
            q += len(line)
            out.append(line)
    offset_map.append(q)
    return "\n".join(out), restored, unmatched, offset_map


def _trim(text: str, start: int, end: int) -> Tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _names(cell: str) -> List[str]:
    return [] if cell in ("", "nan") else list(ast.literal_eval(cell))


class Characters:
    """PDNC's character list with work.json's fixes: keys, names, merged duplicates, dropped and added aliases,
    extra entities, and `name_map` for names PDNC resolves wrongly or not at all."""

    def __init__(self, rows: Sequence[Dict[str, str]], config: Dict[str, Any]):
        overrides = config.get("entities", {})
        self.entities: Dict[str, Dict[str, Any]] = {}
        self._by_main: Dict[str, str] = {}
        by_alias: Dict[str, set] = {}
        for row in rows:
            main = row["Main Name"]
            if main in SPECIAL_SPEAKERS:
                continue
            fix = overrides.get(main, {})
            key = fix.get("key") or entity_key(main)
            aliases = (set(_names(row["Aliases"])) - set(fix.get("drop_aliases", []))) | set(fix.get("add_aliases", []))
            entity = self.entities.setdefault(key, {"entity_key": key, "name": fix.get("name", main),
                                                    "type": "character", "aliases": set(), "pdnc_ids": []})
            if "name" in fix:
                entity["name"] = fix["name"]
            entity["aliases"] |= aliases | {main}
            entity["pdnc_ids"].append(row["Character ID"])
            self._by_main[main] = key
            for alias in aliases:
                by_alias.setdefault(alias, set()).add(key)
        for extra in config.get("extra_entities", []):
            self.entities[extra["key"]] = {"entity_key": extra["key"], "name": extra["name"],
                                           "type": extra.get("type", "character"),
                                           "aliases": set(extra.get("aliases", [])), "pdnc_ids": []}
        self._by_alias = {a: next(iter(ks)) for a, ks in by_alias.items() if len(ks) == 1}
        self._ambiguous = {a for a, ks in by_alias.items() if len(ks) > 1}
        self._name_map: Dict[str, Optional[str]] = config.get("name_map", {})

    def resolve(self, name: str) -> Tuple[Optional[str], Optional[str]]:
        """(entity_key, problem); key None with no problem means a speaker PDNC marks as a group or unknowable."""
        if name in self._name_map:
            return self._name_map[name], None
        if name in SPECIAL_SPEAKERS:
            return None, None
        if name in self._by_main:
            return self._by_main[name], None
        if name in self._by_alias:
            return self._by_alias[name], None
        if name in self._ambiguous:
            return None, f"name {name!r} is an alias of several characters; add it to name_map"
        return None, f"name {name!r} is not in the character list; add it to name_map or extra_entities"

    def record(self, key: str) -> Dict[str, Any]:
        e = self.entities[key]
        rec: Dict[str, Any] = {"entity_key": key, "name": e["name"], "type": e["type"],
                               "aliases": sorted(a for a in e["aliases"] if a != e["name"])}
        if e["pdnc_ids"]:
            rec["external_ids"] = {"pdnc": ";".join(e["pdnc_ids"])}
        rec["review"] = {"origin": "pdnc", "status": "accepted", "by": "pdnc"}
        return rec


def _chapter_title(chapter: str) -> Optional[str]:
    """The heading's title line when the book has one in capitals (Oliver Twist), else None (Pride and Prejudice)."""
    lines = [l.strip() for l in chapter.split("\n")[1:6] if l.strip()]
    if lines and lines[0].upper() == lines[0] and any(c.isalpha() for c in lines[0]):
        return lines[0]
    return None


def _mention_region(chapter: str) -> Optional[Dict[str, int]]:
    words = list(re.finditer(r"\S+", chapter))
    if len(words) <= MENTION_REGION_WORDS:
        return None
    cut = words[MENTION_REGION_WORDS - 1].end()
    para = chapter.find("\n\n", cut)
    end = len(chapter) if para < 0 else para
    return {"start": 0, "end": end}


def _kind(surface: str) -> str:
    if surface.lower() in PRONOUNS:
        return "pronominal"
    return "proper" if surface[:1].isupper() else "nominal"


def convert_chapter(text: str, quote_rows: Sequence[Dict[str, str]], characters: Characters,
                    config: Dict[str, Any], number: int, bounds: Tuple[int, int], revision: str,
                    pdnc_text: Optional[str] = None,
                    offset_map: Optional[Sequence[int]] = None) -> Tuple[Dict[str, Any], List[str]]:
    """One gold v2 draft for chapter `number` (by position) at `bounds` in the novel text. `pdnc_text` and
    `offset_map` come from `restore_from_reference`, when it was applied: spans are checked on PDNC's text, then
    moved into `text`."""
    pdnc_text = pdnc_text if pdnc_text is not None else text
    omap = offset_map if offset_map is not None else range(len(pdnc_text) + 1)

    def to_text(s: int, e: int) -> Tuple[int, int]:
        return omap[s], (omap[e - 1] + 1 if e > s else omap[s])

    start, end = bounds
    chapter = text[start:end]
    issues: List[str] = []
    referenced: set = set()

    def local(s: int, e: int, expected: str, where: str) -> Optional[Tuple[int, int]]:
        s, e = _trim(pdnc_text, s, e)
        if pdnc_text[s:e] != expected.strip():
            issues.append(f"{where}: text at ({s}, {e}) is {pdnc_text[s:e]!r}, PDNC has {expected.strip()!r}; "
                          "dropped")
            return None
        before = pdnc_text[s - 1] if s > 0 else ""
        s, e = to_text(s, e)
        if s > start and text[s - 1] == "'" and before == " " and text[s].isalnum():
            s -= 1     # a restored elision apostrophe: 'Ed
        return s - start, e - start

    quotes, mentions = [], {}
    for row in quote_rows:
        spans = ast.literal_eval(row["quoteByteSpans"])
        inside = [start <= to_text(s, e)[0] and to_text(s, e)[1] <= end for s, e in spans]
        if not any(inside):
            continue
        qid = row["quoteID"]
        if not all(inside):
            issues.append(f"PDNC {qid}: crosses the chapter boundary; dropped")
            continue
        subs = ast.literal_eval(row["subQuotationList"])
        local_spans = [sp for sp in (local(s, e, sub, f"PDNC {qid}") for sub, (s, e) in zip(subs, spans)) if sp]
        if not local_spans:
            continue
        speaker, problem = characters.resolve(row["speaker"])
        if problem:
            issues.append(f"PDNC {qid} speaker: {problem}")
        addressees = []
        for name in _names(row["addressees"]):
            key, problem = characters.resolve(name)
            if problem:
                issues.append(f"PDNC {qid} addressee: {problem}")
            elif key and key not in addressees and key != speaker:
                addressees.append(key)
        qtype = QUOTE_TYPES.get(row["quoteType"])
        if qtype is None:
            issues.append(f"PDNC {qid}: quote type {row['quoteType']!r}, recorded as implicit")
            qtype = "implicit"
        note = f"PDNC {qid}" + (f"; PDNC speaker {row['speaker']}" if row["speaker"] in SPECIAL_SPEAKERS else "")
        quotes.append({"spans": [{"start": s, "end": e} for s, e in local_spans], "speaker_entity_key": speaker,
                       "addressee_entity_keys": addressees, "quote_type": qtype,
                       "review": {"origin": "pdnc", "status": "accepted", "by": "pdnc", "note": note}})
        referenced.update(k for k in [speaker, *addressees] if k)

        for texts, spans_, entities in zip(ast.literal_eval(row["mentionTextsList"]),
                                           ast.literal_eval(row["mentionSpansList"]),
                                           ast.literal_eval(row["mentionEntitiesList"])):
            for surface, (s, e), names in zip(texts, spans_, entities):
                if len(names) != 1:
                    continue      # a mention of several characters: one entity per gold mention
                key, problem = characters.resolve(names[0])
                if problem or key is None:
                    if problem:
                        issues.append(f"PDNC {qid} mention {surface!r}: {problem}")
                    continue
                sp = local(s, e, surface, f"PDNC {qid} mention")
                if sp and sp not in mentions:
                    mentions[sp] = {"text": chapter[sp[0]:sp[1]], "type": "character",
                                    "mention_kind": _kind(chapter[sp[0]:sp[1]]), "entity_key": key,
                                    "start": sp[0], "end": sp[1],
                                    "review": {"origin": "pdnc", "status": "accepted", "by": "pdnc",
                                               "note": "mention_kind set by the converter"}}
                    referenced.add(key)

    quotes.sort(key=lambda q: q["spans"][0]["start"])
    for i, q in enumerate(quotes, 1):
        q["quote_id"] = f"Q{i}"
    ordered_mentions = [mentions[sp] for sp in sorted(mentions)]
    for i, m in enumerate(ordered_mentions, 1):
        m["mention_id"] = f"M{i}"

    work_id = config["work_id"]
    work: Dict[str, Any] = {"work_id": work_id, "title": config["title"], "author": config["author"],
                            "chapter_number": number}
    title = _chapter_title(chapter)
    if title:
        work["chapter_title"] = title
    work["source"] = {"corpus": "pdnc", "url": PDNC_URL, "revision": revision, "license": LICENSE,
                      "text_offset": start}
    mention_scope: Dict[str, Any] = {"coverage": "partial"}
    region = _mention_region(chapter)
    if region:
        mention_scope["region"] = region
    none = {"coverage": "none"}
    doc = {
        "schema_version": "2.0",
        "doc_id": f"{work_id}/ch{number:02d}",
        "work": work,
        "text": chapter,
        "annotation": {
            "guidelines_version": "2.0", "status": "draft",
            "layers": {"mentions": mention_scope, "quotes": {"coverage": "exhaustive"}, "events": none,
                       "facts": none, "relationships": none, "temporal_expressions": none,
                       "temporal_relations": none},
            "notes": f"Quotes, characters and the mentions inside quotes imported from PDNC at {revision[:7]}. "
                     "Mentions are partial until the drafting pass covers the region.",
        },
        "entities": [characters.record(k) for k in sorted(referenced)],
        "mentions": [{k: m[k] for k in ("mention_id", "text", "type", "mention_kind", "entity_key", "start", "end",
                                        "review")} for m in ordered_mentions],
        "quotes": [{k: q[k] for k in ("quote_id", "spans", "speaker_entity_key", "addressee_entity_keys",
                                      "quote_type", "review")} for q in quotes],
        "events": [], "facts": [], "relationships": [], "temporal_expressions": [], "temporal_relations": [],
    }
    return doc, issues
