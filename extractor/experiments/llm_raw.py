"""
What NuExtract said before the code filtered it: replays each chunk's exact prompt through the oracle runs' LLM cache
(no model call; a missing entry is an error) and checks every gold fact and relationship against the raw answers for
the chunk holding its evidence.

    python -m experiments.llm_raw LLM_CACHE.json OUT.json

Per gold claim:
    facts           raw_value_right_entity (some answer names the entity and gives a value containing, or contained
                    in, the gold value for that property) | raw_value_wrong_entity | raw_none
    relationships   raw_match (an answer names both entities, any order, with the gold predicate; FATHER_OF and
                    MOTHER_OF accept parent_of / child_of) | raw_other_relation (both entities, another relation) |
                    raw_none
An answer's name stands for an entity when its `name_key` (the pipeline's own matching) equals the key of the entity's
name, an alias, or the text of one of its gold mentions in the chunk. Chunks are the pipeline's (2,000 characters).
"""
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Set

import extractor  # noqa: F401
from app.evaluation.score_v2 import REVIEWED
from app.preprocessing import chunk_document, preprocess_chapter
from experiments.oracle import CachedLLM
from extractor import relations as R

GOLD = Path(__file__).resolve().parents[2] / "gold" / "v2"
PARENTISH = {"FATHER_OF", "MOTHER_OF", "PARENT_OF"}


def _names(gold: Dict[str, Any], key: str, chunk: Any) -> Set[str]:
    ent = next(e for e in gold["entities"] if e["entity_key"] == key)
    names = {ent["name"], *ent.get("aliases", [])}
    names |= {m["text"] for m in gold["mentions"] if m["entity_key"] == key and chunk.start <= m["start"] < chunk.end}
    return {R.name_key(n) for n in names}


def _contains(a: str, b: str) -> bool:
    a, b = " ".join(a.split()).casefold(), " ".join(b.split()).casefold()
    return bool(a and b) and (a in b or b in a)


def analyse(cache: CachedLLM, gold: Dict[str, Any]) -> List[Dict[str, Any]]:
    def replay(system, user, schema, *args, **kwargs):
        k = cache.key(system, user, schema, *args, **kwargs)
        if k not in cache.store:
            raise KeyError(f"{gold['doc_id']}: no cached answer for a chunk prompt")
        return cache.store[k]

    R.generate = replay
    document = preprocess_chapter(gold["text"])
    chunks = list(chunk_document(document, max_chars=R.CHUNK_CHARS, overlap_sentences=0))
    raw = [(c, R.ask(R.PEOPLE, c.text).get("people") or [], R.ask(R.RELATIONSHIPS, c.text).get("relationships") or [])
           for c in chunks]
    chunk_of = lambda pos: next(i for i, (c, _, _) in enumerate(raw) if c.start <= pos < c.end)
    out = []
    for f in gold["facts"]:
        c, people, _ = raw[chunk_of(f["evidence"]["start"])]
        mine = _names(gold, f["entity_key"], c)
        values = [(R.name_key(p.get("name") or ""), p.get(f["property"])) for p in people
                  if isinstance(p.get(f["property"]), str) and _contains(p[f["property"]], f["value"])]
        cls = ("raw_value_right_entity" if any(n in mine for n, _ in values)
               else "raw_value_wrong_entity" if values else "raw_none")
        out.append({"kind": "fact", "id": f["fact_id"], "entity": f["entity_key"], "property": f["property"],
                    "value": f["value"], "raw": cls, "raw_values": [v for _, v in values][:3]})
    for r in gold["relationships"]:
        c, _, rels = raw[chunk_of(r["evidence"]["start"])]
        a, b = _names(gold, r["subject_entity_key"], c), _names(gold, r["object_entity_key"], c)
        pair = [x for x in rels if isinstance(x.get("subject"), str) and isinstance(x.get("object"), str)
                and ((R.name_key(x["subject"]) in a and R.name_key(x["object"]) in b)
                     or (R.name_key(x["subject"]) in b and R.name_key(x["object"]) in a))]
        ok = lambda x: str(x.get("relation", "")).upper() in ({"PARENT_OF", "CHILD_OF"} if r["predicate"] in PARENTISH
                                                              else {r["predicate"]})
        cls = "raw_match" if any(ok(x) for x in pair) else "raw_other_relation" if pair else "raw_none"
        out.append({"kind": "relationship", "id": r["relationship_id"], "subject": r["subject_entity_key"],
                    "predicate": r["predicate"], "object": r["object_entity_key"], "raw": cls,
                    "raw_relations": sorted({str(x.get("relation")) for x in pair})})
    return out


def main(argv: List[str]) -> int:
    cache = CachedLLM(Path(argv[0]))
    result = {}
    for path in sorted(GOLD.rglob("ch*.json")):
        gold = json.loads(path.read_text(encoding="utf-8"))
        if gold["annotation"]["status"] in REVIEWED:
            result[gold["doc_id"]] = analyse(cache, gold)
    flat = [x for v in result.values() for x in v]
    summary = {k: dict(Counter(x["raw"] for x in flat if x["kind"] == k)) for k in ("fact", "relationship")}
    Path(argv[1]).write_text(json.dumps({"summary": summary, "claims": result}, ensure_ascii=False, indent=1),
                             encoding="utf-8")
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
