"""
Claim-level error analysis and the predicate-mapping experiment, on top of the v2 scorer.

Every predicted fact and relationship is resolved to gold entity keys exactly as `score-v2` resolves it (its
`_Resolver`, so the counts reconcile with the scores) and classified:

    relationships   tp (strict match) | lenient_only (matches only with FATHER_OF/MOTHER_OF/PARENT_OF merged: a
                    schema mismatch) | wrong_predicate (a gold relationship joins the same two entities with another
                    predicate) | wrong_endpoint (a gold relationship with this predicate shares one endpoint) |
                    unresolved (an endpoint names no gold entity) | false_positive (none of these)
    facts           tp | wrong_value (the entity has a gold fact for this property with another value) |
                    wrong_entity (another entity has this property and value) | unresolved | false_positive

Every gold claim is classified as found, found_lenient_only (relationships), or missed, and a miss is explained by
the nearest prediction (wrong predicate / endpoint / value) or by `entity_not_predicted`: no predicted mention resolves
to one of the claim's entities, so mention detection or coreference lost it before relation extraction could.
Gold claims the extractor's output format cannot express are counted apart (`unexpressible`): a claim with
`claimed_by` or a non-asserted `assertion` (the extractor emits neither), and FATHER_OF / MOTHER_OF (the extractor's
vocabulary has only PARENT_OF).
"""
from __future__ import annotations

import copy
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

import extractor  # noqa: F401  (puts ../backend on sys.path)
from app.evaluation.score_v2 import FALLBACK, _fact_keys, _Gold, _relation, _Resolver

V1_TO_V2 = {p: p for p in ("FRIEND_OF", "ENEMY_OF", "SIBLING_OF", "PARENT_OF", "MARRIED_TO", "ALLY_OF", "WORKS_FOR",
                           "MEMBER_OF", "OWNS", "KNOWS", "RELATED_TO")}
# CHILD_OF is PARENT_OF with the ends swapped. PARENT_OF -> FATHER_OF / MOTHER_OF would need the parent's gender, which
# the predicate does not carry: not mapped.
SWAPPED = {"CHILD_OF": "PARENT_OF"}
UNMAPPABLE_NOTE = {"PARENT_OF": "v2 also has FATHER_OF / MOTHER_OF; choosing one needs the parent's gender"}


def map_predicates(pred: Dict[str, Any]) -> Tuple[Dict[str, Any], Counter]:
    """A copy of the prediction with v1 predicates written as their exact v2 equivalents; counts of what happened."""
    out, log = copy.deepcopy(pred), Counter()
    for r in out.get("relationships", []):
        p = r.get("predicate")
        if p in SWAPPED:
            r["subject_mention_id"], r["object_mention_id"] = r["object_mention_id"], r["subject_mention_id"]
            r["predicate"] = SWAPPED[p]
            log[f"{p} -> {SWAPPED[p]} (ends swapped)"] += 1
        elif p in V1_TO_V2:
            log[f"{p} -> {p} (same in v2)"] += 1
        else:
            log[f"{p}: not a v1 predicate, left as is"] += 1
    return out, log


class ContainmentResolver(_Resolver):
    """DIAGNOSTIC ONLY, not the official score: the scorer's resolver, plus one rule. A predicted mention it leaves
    unresolved, and that lies strictly inside a gold mention with an entity, takes the entity of the smallest such
    gold mention (source "containment"). It separates the extractor's span convention ("wife", which `role_pairs`
    creates when the gold-style span is "his wife") from what the extractor actually linked."""

    def __init__(self, pred: Dict[str, Any], gold: _Gold):
        super().__init__(pred, gold)
        spans = [(m["start"], m["end"], m["entity_key"]) for m in gold.mentions if m["entity_key"] is not None]
        for mid, m in self.by_id.items():
            if self.own[mid][0] is None and self.own[mid][1] == "unresolved" and isinstance(m.get("start"), int):
                inside = [(e - s, k) for s, e, k in spans if s <= m["start"] and m["end"] <= e
                          and (s, e) != (m["start"], m["end"])]
                if inside:
                    self.own[mid] = (min(inside)[1], "containment")


def _pair(t: Tuple[Any, Any, Any]) -> frozenset:
    return frozenset((t[0], t[2]))


def diagnose(pred: Dict[str, Any], gold_doc: Dict[str, Any], resolver: type = _Resolver) -> Dict[str, Any]:
    gold = _Gold(gold_doc, include_pending=False)
    resolve = resolver(pred, gold)
    text = gold_doc["text"]
    by_id = {m["mention_id"]: m for m in pred.get("mentions", [])}
    region = gold_doc["annotation"]["layers"]["mentions"].get("region")
    region_end = region["end"] if region else len(text)
    surface = lambda mid: (by_id.get(mid) or {}).get("text")
    predicted_entities = {k for mid in by_id if (k := resolve(mid)[0]) is not None}
    where = lambda c: "in_region" if c["evidence"]["end"] <= region_end else "after_region"
    ev = lambda c: " ".join(text[c["evidence"]["start"]:c["evidence"]["end"]].split())

    # ---------------------------------------------------------------- relationships
    g_rels = [{"gold": r, "strict": _relation(r["subject_entity_key"], r["predicate"], r["object_entity_key"], False),
               "lenient": _relation(r["subject_entity_key"], r["predicate"], r["object_entity_key"], True)}
              for r in gold.relationships]
    p_rels, seen = [], set()
    for r in pred.get("relationships", []):
        (s, s_src), (o, o_src) = resolve(r.get("subject_mention_id")), resolve(r.get("object_mention_id"))
        entry = {"predicate": r.get("predicate"), "subject": s, "object": o,
                 "subject_text": surface(r.get("subject_mention_id")), "object_text": surface(r.get("object_mention_id")),
                 "fallback": s_src in FALLBACK or o_src in FALLBACK, "sources": [s_src, o_src]}
        if s is None or o is None:
            entry["class"] = "unresolved"
        else:
            strict, lenient = _relation(s, r.get("predicate"), o, False), _relation(s, r.get("predicate"), o, True)
            if strict in seen:
                continue                                    # a repeated tuple counts once, as in the scorer
            seen.add(strict)
            if any(g["strict"] == strict for g in g_rels):
                entry["class"] = "tp"
            elif any(g["lenient"] == lenient for g in g_rels):
                entry["class"] = "lenient_only"
            elif any(_pair(g["strict"]) == _pair(strict) for g in g_rels):
                entry["class"] = "wrong_predicate"
            elif any(g["lenient"][1] == lenient[1] and len(_pair(g["strict"]) & _pair(strict)) == 1 for g in g_rels):
                entry["class"] = "wrong_endpoint"
            else:
                entry["class"] = "false_positive"
            entry["strict"], entry["lenient"] = strict, lenient
        p_rels.append(entry)
    for g in g_rels:
        r = g["gold"]
        hits = [p for p in p_rels if p.get("strict") == g["strict"]]
        lenient_hits = [p for p in p_rels if p.get("lenient") == g["lenient"]]
        if hits:
            g["class"] = "found"
        elif lenient_hits:
            g["class"] = "found_lenient_only"
        elif any(p.get("strict") and _pair(p["strict"]) == _pair(g["strict"]) for p in p_rels):
            g["class"] = "missed_wrong_predicate"
        elif not {r["subject_entity_key"], r["object_entity_key"]} <= predicted_entities:
            g["class"] = "missed_entity_not_predicted"
        elif any(p.get("lenient") and p["lenient"][1] == g["lenient"][1] and len(_pair(p["strict"]) & _pair(g["strict"])) == 1
                 for p in p_rels):
            g["class"] = "missed_wrong_endpoint"
        else:
            g["class"] = "missed_no_prediction"
        g.update(where=where(r), evidence=ev(r), unexpressible=[x for x in (
            "claimed_by" if r.get("claimed_by") else None, "assertion" if r["assertion"] != "asserted" else None,
            "parent_gender" if r["predicate"] in ("FATHER_OF", "MOTHER_OF") else None) if x])

    # ---------------------------------------------------------------- facts
    g_facts = [{"gold": f, "keys": _fact_keys(f["entity_key"], f["property"], f)} for f in gold.facts]
    p_facts, seen_f = [], set()
    for n, f in enumerate(pred.get("facts", [])):
        k, src = resolve(f.get("entity_mention_id"))
        entry = {"property": f.get("property"), "value": f.get("value"), "entity": k,
                 "entity_text": surface(f.get("entity_mention_id")), "fallback": src in FALLBACK, "source": src}
        if k is None:
            entry["class"] = "unresolved"
        else:
            keys = _fact_keys(k, f.get("property"), f)
            if keys & seen_f:
                continue
            seen_f |= keys
            entry["keys"] = keys
            if any(g["keys"] & keys for g in g_facts):
                entry["class"] = "tp"
            elif any(g["gold"]["entity_key"] == k and g["gold"]["property"] == f.get("property") for g in g_facts):
                entry["class"] = "wrong_value"
            elif any({(None, p, v) for _, p, v in g["keys"]} & {(None, p, v) for _, p, v in keys} for g in g_facts):
                entry["class"] = "wrong_entity"
            else:
                entry["class"] = "false_positive"
        p_facts.append(entry)
    for g in g_facts:
        f = g["gold"]
        if any(p.get("keys") and p["keys"] & g["keys"] for p in p_facts):
            g["class"] = "found"
        elif any(p["entity"] == f["entity_key"] and p["property"] == f["property"] for p in p_facts):
            g["class"] = "missed_wrong_value"
        elif f["entity_key"] not in predicted_entities:
            g["class"] = "missed_entity_not_predicted"
        else:
            g["class"] = "missed_no_prediction"
        g.update(where=where(f), evidence=ev(f), unexpressible=[x for x in (
            "claimed_by" if f.get("claimed_by") else None,
            "assertion" if f["assertion"] != "asserted" else None) if x])
    return {"doc_id": gold_doc["doc_id"], "pred_relationships": p_rels, "gold_relationships": g_rels,
            "pred_facts": p_facts, "gold_facts": g_facts}


def summarize(diags: List[Dict[str, Any]]) -> Dict[str, Any]:
    c = lambda items: dict(Counter(x["class"] for x in items))
    flat = lambda key: [x for d in diags for x in d[key]]
    out = {k: c(flat(k)) for k in ("pred_relationships", "gold_relationships", "pred_facts", "gold_facts")}
    for k in ("pred_relationships", "pred_facts"):
        out[k + "_tp_via_fallback"] = sum(1 for x in flat(k) if x["class"] in ("tp", "lenient_only") and x["fallback"])
    for k in ("gold_relationships", "gold_facts"):
        out[k + "_by_region"] = dict(Counter((x["where"], x["class"]) for x in flat(k)))
        out[k + "_unexpressible"] = dict(Counter(u for x in flat(k) for u in x["unexpressible"]))
    out["pred_relationships_by_predicate"] = dict(Counter((x["predicate"], x["class"]) for x in flat("pred_relationships")))
    return out


def jsonable(x: Any) -> Any:
    if isinstance(x, dict):
        return {(" / ".join(map(str, k)) if isinstance(k, tuple) else k): jsonable(v) for k, v in x.items()
                if k != "keys"}
    if isinstance(x, (list, tuple, set, frozenset)):
        return [jsonable(v) for v in x]
    return x
