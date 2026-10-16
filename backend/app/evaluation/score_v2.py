"""
Scores a prediction against a gold v2 chapter (`orion_gold_v2.schema.json`, rules in docs/gold_v2_guidelines.md).

The prediction is the extractor's document (the v1 shape): `mentions` with offsets, `coreference_clusters`, and
`facts` / `relationships` that point at mentions (`entity_mention_id`, `subject_mention_id`, `object_mention_id`).
Optional, per fact or relationship: `assertion` (default `asserted`) and `claimed_by_mention_id` (default: narration).
Optional `quotes`: [{start, end, speaker_mention_id}]. A predicted mention without offsets can still name an entity
(its text is matched against entity names and aliases), but it counts in no mention metric.

Which gold items count:
    default           items whose review.status is `accepted` or `corrected`. Pending items are an ignore zone: a
                      prediction matching one is neither right nor wrong. This is the mode for evaluation results.
    include_pending   pending items count as gold. DEVELOPMENT ONLY (guidelines §1): every result carries
                      `provisional: true`, and these numbers are never reported as evaluation results.

Coverage (`annotation.layers`): `exhaustive` gives precision and recall; `partial` gives recall only (unmatched
predictions are not false positives); `none` is not scored. A mention or quote `region` limits both sides to spans
inside it. A region on facts or relationships keeps gold claims whose evidence lies inside it and scores recall only,
since predicted claims have no position.

Entities. A predicted mention names the gold entity of the gold mention it aligns to (overlapping spans, one to one,
largest overlap first), or, failing that, the entity whose name or alias equals its text (casefolded; ambiguous names
name nothing). A clustered mention names the entity most of its cluster names.

Metrics (counts: tp / fp / fn with precision / recall / F1; accuracies: correct / total):
    mentions_exact          span identical
    mentions_overlap        spans overlap (the alignment above)
    mentions_typed          span identical and same type
    mention_linking         accuracy over aligned mentions whose gold mention has an entity: right entity named
    coreference_b3          B-cubed over gold mentions with an entity, clustered by entity key; predicted mentions
                            map to gold mentions through the alignment, and unaligned ones stay as their own items
    coreference_b3_linked   the same on mentions both sides have: linking quality apart from mention detection
    facts                   (entity, property, value); values casefolded and whitespace-normalized; `status` facts
                            compare `status_value`, `age` facts also match on `age_years`
    relationships           (subject, predicate, object); symmetric predicates unordered, CHILD_OF read as PARENT_OF
                            reversed
    relationships_lenient   the same with FATHER_OF / MOTHER_OF / PARENT_OF all read as PARENT_OF
    claim_attribution       accuracy over matched facts and relationships: the predicted claimant is a claimant of
                            the gold claim (narration matches narration)
    claim_assertion         accuracy over matched facts and relationships: same assertion value
    quotes_overlap          quote spans overlap (a gold quote spans its first to last piece)
    quote_speaker           accuracy over aligned quotes: the predicted speaker is the gold speaker
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Sequence, Set, Tuple

from app.evaluation.score import align, prf

Span = Tuple[int, int]
GOLD_STATUSES = ("accepted", "corrected")
REVIEWED = ("reviewed", "adjudicated")
SYMMETRIC = {"FRIEND_OF", "ENEMY_OF", "SIBLING_OF", "MARRIED_TO", "ENGAGED_TO", "ALLY_OF", "KNOWS", "RELATED_TO"}
PARENT = {"FATHER_OF", "MOTHER_OF", "PARENT_OF"}
STATUS_VALUES = {"ALIVE", "DEAD", "MISSING", "INJURED", "UNCONSCIOUS", "OTHER"}
COUNTS = ("mentions_exact", "mentions_overlap", "mentions_typed", "facts", "relationships", "relationships_lenient",
          "quotes_overlap")
ACCURACIES = ("mention_linking", "claim_attribution", "claim_assertion", "quote_speaker")
B3 = ("coreference_b3", "coreference_b3_linked")
B3_KEYS = ("p_num", "p_den", "r_num", "r_den")


def accuracy(correct: int, total: int) -> Dict[str, Any]:
    return {"correct": correct, "total": total, "accuracy": round(correct / total, 4) if total else 0.0}


def b3(counts: Dict[str, float]) -> Dict[str, Any]:
    p = counts["p_num"] / counts["p_den"] if counts["p_den"] else 0.0
    r = counts["r_num"] / counts["r_den"] if counts["r_den"] else 0.0
    return {**counts, "precision": round(p, 4), "recall": round(r, 4),
            "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0}


def _side(a: Sequence[FrozenSet[str]], b: Sequence[FrozenSet[str]]) -> Tuple[float, int]:
    """B-cubed in entity-overlap form: sum of |A ∩ B|² / |A| over cluster pairs, and the number of items in `a`."""
    return sum(len(x & y) ** 2 / len(x) for x in a for y in b), sum(len(x) for x in a)


def _span(item: Dict[str, Any]) -> Optional[Span]:
    s, e = item.get("start"), item.get("end")
    return (s, e) if isinstance(s, int) and isinstance(e, int) else None


def _inside(span: Span, region: Optional[Span]) -> bool:
    return region is None or (region[0] <= span[0] and span[1] <= region[1])


def _norm(value: Any) -> str:
    return " ".join(str(value).split()).casefold()


def _layer(gold: Dict[str, Any], name: str) -> Tuple[str, Optional[Span]]:
    scope = gold["annotation"]["layers"].get(name, {"coverage": "none"})
    region = scope.get("region")
    return scope["coverage"], (region["start"], region["end"]) if region else None


def _match_counts(pred: Sequence[Any], gold: Set[Any], ignore: Set[Any]) -> Tuple[int, int, int]:
    pred = set(pred) - (ignore - gold)
    return len(pred & gold), len(pred - gold), len(gold - pred)


class _Gold:
    """The gold items that count, and the pending ones that are ignored, for one chapter."""

    def __init__(self, doc: Dict[str, Any], include_pending: bool):
        counts = lambda item: include_pending or item.get("review", {}).get("status") in GOLD_STATUSES
        self.doc = doc
        self.entities = [e for e in doc["entities"] if counts(e)]
        self.mentions = [m for m in doc["mentions"] if counts(m)]
        self.ignored_mentions = [m for m in doc["mentions"] if not counts(m)]
        self.facts = [f for f in doc["facts"] if counts(f)]
        self.ignored_facts = [f for f in doc["facts"] if not counts(f)]
        self.relationships = [r for r in doc["relationships"] if counts(r)]
        self.ignored_relationships = [r for r in doc["relationships"] if not counts(r)]
        self.quotes = [q for q in doc["quotes"] if counts(q)]
        self.ignored_quotes = [q for q in doc["quotes"] if not counts(q)]


class _Resolver:
    """Predicted mention id -> gold entity key (or None), as described in the module docstring."""

    def __init__(self, pred: Dict[str, Any], gold: _Gold, m_align: Dict[str, str]):
        self.by_id = {m["mention_id"]: m for m in pred.get("mentions", [])}
        gold_key = {m["mention_id"]: m["entity_key"] for m in gold.mentions}
        names: Dict[str, Set[str]] = {}
        for e in gold.entities:
            for name in [e["name"], *e.get("aliases", [])]:
                names.setdefault(_norm(name), set()).add(e["entity_key"])
        self.own: Dict[str, Optional[str]] = {}
        for mid, m in self.by_id.items():
            key = gold_key.get(m_align[mid]) if mid in m_align else None
            if key is None:
                named = names.get(_norm(m.get("text", "")), set())
                key = next(iter(named)) if len(named) == 1 else None
            self.own[mid] = key
        self.cluster = {mid: c["mentions"] for c in pred.get("coreference_clusters", []) for mid in c["mentions"]}

    def __call__(self, mid: Any) -> Optional[str]:
        if mid not in self.by_id:
            return None
        votes = Counter(k for m in self.cluster.get(mid, [mid]) if (k := self.own.get(m)) is not None)
        return votes.most_common(1)[0][0] if votes else None


def _relation(subject: Any, predicate: Any, obj: Any, lenient: bool) -> Tuple[Any, Any, Any]:
    if predicate == "CHILD_OF":
        subject, predicate, obj = obj, "PARENT_OF", subject
    if lenient and predicate in PARENT:
        predicate = "PARENT_OF"
    if predicate in SYMMETRIC and str(obj) < str(subject):
        subject, obj = obj, subject
    return subject, predicate, obj


def _fact_keys(key: Any, prop: Any, item: Dict[str, Any]) -> Set[Tuple[Any, Any, str]]:
    if prop == "status":
        sv = item.get("status_value") or _norm(item.get("value", "")).upper()
        return {(key, prop, sv if sv in STATUS_VALUES else _norm(item.get("value", "")))}
    keys = {(key, prop, _norm(item.get("value", "")))}
    if prop == "age" and item.get("age_years") is not None:
        keys.add((key, prop, str(item["age_years"])))
    elif prop == "age" and _norm(item.get("value", "")).isdigit():
        keys.add((key, prop, str(int(_norm(item["value"])))))
    return keys


def _score_claims(pred_claims: List[Dict[str, Any]], gold_claims: List[Dict[str, Any]],
                  ignored: List[Dict[str, Any]], recall_only: bool) -> Tuple[Dict[str, Any], List[Tuple[Dict, Dict]]]:
    """Each claim: {keys: set of tuples, claimant, assertion}. Gold claims sharing a tuple merge (their claimants and
    assertions pool). Predictions match one to one in order; a duplicate of a matched prediction is a false positive.
    Returns the counts and the matched (prediction, gold) pairs."""
    merged: List[Dict[str, Any]] = []
    for g in gold_claims:
        same = next((m for m in merged if m["keys"] & g["keys"]), None)
        if same:
            same["keys"] |= g["keys"]
            same["claimants"].add(g["claimant"])
            same["assertions"].add(g["assertion"])
        else:
            merged.append({"keys": set(g["keys"]), "claimants": {g["claimant"]}, "assertions": {g["assertion"]}})
    ignore_keys = set().union(*(i["keys"] for i in ignored)) if ignored else set()
    matched: List[Tuple[Dict, Dict]] = []
    taken: Set[int] = set()
    tp = fp = 0
    for p in pred_claims:
        hit = next((n for n, g in enumerate(merged) if n not in taken and g["keys"] & p["keys"]), None)
        if hit is not None:
            taken.add(hit)
            matched.append((p, merged[hit]))
            tp += 1
        elif not (p["keys"] & ignore_keys) and not recall_only:
            fp += 1
    return prf(tp, fp, len(merged) - tp), matched


def score_document_v2(pred: Dict[str, Any], gold_doc: Dict[str, Any], include_pending: bool = False) -> Dict[str, Any]:
    if pred.get("text") != gold_doc["text"]:
        raise ValueError(f"{gold_doc['doc_id']}: the prediction's text differs from the gold text")
    gold = _Gold(gold_doc, include_pending)
    res: Dict[str, Any] = {"doc_id": gold_doc["doc_id"], "provisional": include_pending}
    p_mentions = pred.get("mentions", [])

    # ---------------------------------------------------------------- mentions and coreference
    coverage, region = _layer(gold_doc, "mentions")
    g_in = {m["mention_id"]: (m["start"], m["end"]) for m in gold.mentions if _inside((m["start"], m["end"]), region)}
    i_in = {m["mention_id"]: (m["start"], m["end"]) for m in gold.ignored_mentions
            if _inside((m["start"], m["end"]), region)}
    p_in = {m["mention_id"]: sp for m in p_mentions if (sp := _span(m)) and _inside(sp, region)}
    m_align = align(p_in, {**g_in, **i_in})
    resolve = _Resolver(pred, gold, align({m["mention_id"]: sp for m in p_mentions if (sp := _span(m))},
                                          {m["mention_id"]: (m["start"], m["end"]) for m in gold.mentions}))
    g_type = {m["mention_id"]: m["type"] for m in gold.mentions}
    p_type = {m["mention_id"]: m.get("type") for m in p_mentions}
    res["pred_unanchored"] = sum(_span(m) is None for m in p_mentions)
    if coverage == "none":
        for k in ("mentions_exact", "mentions_overlap", "mentions_typed"):
            res[k] = prf(0, 0, 0)
        res["mention_linking"] = accuracy(0, 0)
        for k in B3:
            res[k] = b3({k2: 0 for k2 in B3_KEYS})
    else:
        recall_only = coverage == "partial"
        exact = _match_counts(p_in.values(), set(g_in.values()), set(i_in.values()))
        overlap_tp = sum(1 for pid, gid in m_align.items() if gid in g_in)
        overlap_fp = 0 if recall_only else len(p_in) - len(m_align)
        typed = _match_counts(((sp, p_type[i]) for i, sp in p_in.items()),
                              {(sp, g_type[i]) for i, sp in g_in.items()},
                              {(sp, t) for sp in i_in.values() for t in set(p_type.values())})
        res["mentions_exact"] = prf(exact[0], 0 if recall_only else exact[1], exact[2])
        res["mentions_overlap"] = prf(overlap_tp, overlap_fp, len(g_in) - overlap_tp)
        res["mentions_typed"] = prf(typed[0], 0 if recall_only else typed[1], typed[2])

        g_key = {m["mention_id"]: m["entity_key"] for m in gold.mentions}
        linked = [(pid, gid) for pid, gid in m_align.items() if gid in g_in and g_key[gid] is not None]
        res["mention_linking"] = accuracy(sum(resolve(pid) == g_key[gid] for pid, gid in linked), len(linked))

        keyed = {gid for gid in g_in if g_key[gid] is not None}
        by_key: Dict[str, Set[str]] = {}
        for gid in keyed:
            by_key.setdefault(g_key[gid], set()).add(gid)
        key_clusters = [frozenset(v) for v in by_key.values()]
        drop = {pid for pid, gid in m_align.items() if gid not in keyed}   # aligned to a null-key or ignored mention
        clustered = {mid for c in pred.get("coreference_clusters", []) for mid in c["mentions"]}
        groups = [c["mentions"] for c in pred.get("coreference_clusters", [])]
        groups += [[mid] for mid in p_in if mid not in clustered]
        for name, linked_only in (("coreference_b3", False), ("coreference_b3_linked", True)):
            response = []
            for g in groups:
                ids = frozenset(m_align[m] if m in m_align else f"pred:{m}" for m in g
                                if m in p_in and m not in drop and (m in m_align or not linked_only))
                if ids:
                    response.append(ids)
            key = key_clusters
            if linked_only:
                present = set().union(*response) if response else set()
                key = [k for c in key_clusters if (k := c & present)]
            r_num, r_den = _side(key, response)
            p_num, p_den = _side(response, key)
            res[name] = b3({"p_num": p_num, "p_den": p_den, "r_num": r_num, "r_den": r_den})

    # ---------------------------------------------------------------- facts and relationships
    def claimant(item: Dict[str, Any]) -> Optional[str]:
        return resolve(item["claimed_by_mention_id"]) if item.get("claimed_by_mention_id") is not None else None

    def gold_claims(items: Iterable[Dict[str, Any]], keys) -> List[Dict[str, Any]]:
        return [{"keys": keys(i), "claimant": i.get("claimed_by"), "assertion": i["assertion"]} for i in items]

    def in_region(items: Iterable[Dict[str, Any]], region: Optional[Span]) -> List[Dict[str, Any]]:
        return [i for i in items if _inside((i["evidence"]["start"], i["evidence"]["end"]), region)]

    matched_claims: List[Tuple[Dict, Dict]] = []
    coverage, region = _layer(gold_doc, "facts")
    if coverage == "none":
        res["facts"] = prf(0, 0, 0)
    else:
        fact_keys = lambda f: _fact_keys(f["entity_key"], f["property"], f)
        preds = []
        for f in pred.get("facts", []):
            key = resolve(f.get("entity_mention_id"))
            preds.append({"keys": _fact_keys(key, f.get("property"), f) if key else {("unresolved", id(f))},
                          "claimant": claimant(f), "assertion": f.get("assertion", "asserted")})
        res["facts"], matched = _score_claims(_dedup(preds), gold_claims(in_region(gold.facts, region), fact_keys),
                                              gold_claims(gold.ignored_facts, fact_keys),
                                              coverage == "partial" or region is not None)
        matched_claims += matched

    coverage, region = _layer(gold_doc, "relationships")
    for name, lenient in (("relationships", False), ("relationships_lenient", True)):
        if coverage == "none":
            res[name] = prf(0, 0, 0)
            continue
        rel_keys = lambda r: {_relation(r["subject_entity_key"], r["predicate"], r["object_entity_key"], lenient)}
        preds = []
        for r in pred.get("relationships", []):
            s, o = resolve(r.get("subject_mention_id")), resolve(r.get("object_mention_id"))
            preds.append({"keys": {_relation(s, r.get("predicate"), o, lenient)} if s and o else {("unresolved", id(r))},
                          "claimant": claimant(r), "assertion": r.get("assertion", "asserted")})
        res[name], matched = _score_claims(_dedup(preds), gold_claims(in_region(gold.relationships, region), rel_keys),
                                           gold_claims(gold.ignored_relationships, rel_keys),
                                           coverage == "partial" or region is not None)
        if not lenient:
            matched_claims += matched
    res["claim_attribution"] = accuracy(sum(p["claimant"] in g["claimants"] for p, g in matched_claims),
                                        len(matched_claims))
    res["claim_assertion"] = accuracy(sum(p["assertion"] in g["assertions"] for p, g in matched_claims),
                                      len(matched_claims))

    # ---------------------------------------------------------------- quotes
    coverage, region = _layer(gold_doc, "quotes")
    whole = lambda q: (q["spans"][0]["start"], q["spans"][-1]["end"])
    g_q = {q["quote_id"]: whole(q) for q in gold.quotes if _inside(whole(q), region)}
    i_q = {q["quote_id"]: whole(q) for q in gold.ignored_quotes if _inside(whole(q), region)}
    p_q = {n: sp for n, q in enumerate(pred.get("quotes", [])) if (sp := _span(q)) and _inside(sp, region)}
    if coverage == "none":
        res["quotes_overlap"], res["quote_speaker"] = prf(0, 0, 0), accuracy(0, 0)
    else:
        q_align = align(p_q, {**g_q, **i_q})
        tp = sum(1 for gid in q_align.values() if gid in g_q)
        res["quotes_overlap"] = prf(tp, 0 if coverage == "partial" else len(p_q) - len(q_align), len(g_q) - tp)
        speaker = {q["quote_id"]: q["speaker_entity_key"] for q in gold.quotes}
        pairs = [(n, gid) for n, gid in q_align.items() if gid in g_q]
        res["quote_speaker"] = accuracy(
            sum(resolve(pred["quotes"][n].get("speaker_mention_id")) == speaker[gid] for n, gid in pairs), len(pairs))

    res["gold_counted"] = {"mentions": len(g_in) if _layer(gold_doc, "mentions")[0] != "none" else 0,
                           "facts": len(gold.facts), "relationships": len(gold.relationships), "quotes": len(g_q)}
    res["gold_ignored_pending"] = {"mentions": len(gold.ignored_mentions), "facts": len(gold.ignored_facts),
                                   "relationships": len(gold.ignored_relationships), "quotes": len(gold.ignored_quotes)}
    return res


def _dedup(claims: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """A prediction repeating an earlier one's tuple counts once, as in the v1 scorer's sets."""
    seen: Set[Any] = set()
    out = []
    for c in claims:
        if not (c["keys"] & seen):
            out.append(c)
        seen |= c["keys"]
    return out


def micro_average_v2(per_doc: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Sums counts over chapters, then recomputes the rates."""
    out: Dict[str, Any] = {"provisional": any(d["provisional"] for d in per_doc), "documents": len(per_doc)}
    for m in COUNTS:
        out[m] = prf(*(sum(d[m][k] for d in per_doc) for k in ("tp", "fp", "fn")))
    for m in ACCURACIES:
        out[m] = accuracy(sum(d[m]["correct"] for d in per_doc), sum(d[m]["total"] for d in per_doc))
    for m in B3:
        out[m] = b3({k: sum(d[m][k] for d in per_doc) for k in B3_KEYS})
    for key in ("gold_counted", "gold_ignored_pending"):
        out[key] = {k: sum(d[key][k] for d in per_doc) for k in per_doc[0][key]} if per_doc else {}
    out["pred_unanchored"] = sum(d["pred_unanchored"] for d in per_doc)
    return out


def format_table_v2(scores: Dict[str, Any]) -> str:
    rows = []
    if scores["provisional"]:
        rows.append("PROVISIONAL: pending (unreviewed) items counted as gold. Development only; never report these.")
    rows.append(f"{'metric':24s} {'P':>6s} {'R':>6s} {'F1':>6s} {'tp':>5s} {'fp':>5s} {'fn':>5s}")
    for m in COUNTS:
        s = scores[m]
        rows.append(f"{m:24s} {s['precision']:6.3f} {s['recall']:6.3f} {s['f1']:6.3f} "
                    f"{s['tp']:5d} {s['fp']:5d} {s['fn']:5d}")
    for m in B3:
        s = scores[m]
        rows.append(f"{m:24s} {s['precision']:6.3f} {s['recall']:6.3f} {s['f1']:6.3f}")
    for m in ACCURACIES:
        s = scores[m]
        rows.append(f"{m:24s} accuracy {s['accuracy']:6.3f}  ({s['correct']}/{s['total']})")
    rows.append(f"gold counted: {scores['gold_counted']}   pending, ignored: {scores['gold_ignored_pending']}   "
                f"predicted mentions without offsets: {scores['pred_unanchored']}")
    return "\n".join(rows)


def gold_as_prediction(gold_doc: Dict[str, Any]) -> Dict[str, Any]:
    """The gold chapter written as an extractor prediction: every mention, one cluster per entity key, and facts,
    relationships and quotes pointing at a mention of their entity. An entity with no gold mention gets a mention
    without offsets carrying its name. Used to test the scorer (a perfect prediction) and for oracle experiments."""
    mentions = [{"mention_id": m["mention_id"], "text": m["text"], "start": m["start"], "end": m["end"],
                 "type": m["type"], "mention_kind": m["mention_kind"]} for m in gold_doc["mentions"]]
    first: Dict[str, str] = {}
    for m in gold_doc["mentions"]:
        if m["entity_key"] is not None:
            first.setdefault(m["entity_key"], m["mention_id"])
    names = {e["entity_key"]: e["name"] for e in gold_doc["entities"]}

    def mention_of(key: Optional[str]) -> Optional[str]:
        if key is None:
            return None
        if key not in first:
            first[key] = f"N{len(mentions) + 1}"
            mentions.append({"mention_id": first[key], "text": names[key], "type": "character",
                             "mention_kind": "proper"})
        return first[key]

    clusters: Dict[str, List[str]] = {}
    for m in gold_doc["mentions"]:
        if m["entity_key"] is not None:
            clusters.setdefault(m["entity_key"], []).append(m["mention_id"])
    facts = [{"fact_id": f["fact_id"], "entity_mention_id": mention_of(f["entity_key"]), "property": f["property"],
              "value": f["value"], **({"status_value": f["status_value"]} if "status_value" in f else {}),
              "assertion": f["assertion"], "claimed_by_mention_id": mention_of(f.get("claimed_by"))}
             for f in gold_doc["facts"]]
    rels = [{"relationship_id": r["relationship_id"], "subject_mention_id": mention_of(r["subject_entity_key"]),
             "predicate": r["predicate"], "object_mention_id": mention_of(r["object_entity_key"]),
             "assertion": r["assertion"], "claimed_by_mention_id": mention_of(r.get("claimed_by"))}
            for r in gold_doc["relationships"]]
    quotes = [{"start": q["spans"][0]["start"], "end": q["spans"][-1]["end"],
               "speaker_mention_id": mention_of(q["speaker_entity_key"])} for q in gold_doc["quotes"]]
    return {"doc_id": gold_doc["doc_id"], "text": gold_doc["text"], "mentions": mentions,
            "coreference_clusters": [{"cluster_id": f"C{n}", "mentions": ids}
                                     for n, ids in enumerate(clusters.values(), 1)],
            "facts": facts, "relationships": rels, "quotes": quotes}
