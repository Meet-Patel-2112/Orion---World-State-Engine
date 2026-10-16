"""
Scores a prediction against a gold v2 chapter (`orion_gold_v2.schema.json`, rules in docs/gold_v2_guidelines.md).

The prediction is the extractor's document (the v1 shape): `mentions` with offsets, `coreference_clusters`, and
`facts` / `relationships` that point at mentions (`entity_mention_id`, `subject_mention_id`, `object_mention_id`).
Optional, per fact or relationship: `assertion` (default `asserted`) and `claimed_by_mention_id` (default:
narration). Optional `quotes`: [{start, end, speaker_mention_id}]. A predicted mention without offsets counts in no
mention metric, but its text can still name an entity (see Entities).

Which gold items count
    default           items whose review.status is `accepted` or `corrected`. Pending items are an ignore zone: a
                      prediction matching one is neither a true nor a false positive. Evaluation results use this
                      mode, on reviewed or adjudicated chapters (the CLI skips the others).
    include_pending   pending items count as gold. DEVELOPMENT ONLY (guidelines §1): every result carries
                      `provisional: true`, and these numbers are never reported as evaluation results.

Coverage (`annotation.layers`)
    exhaustive  precision and recall.
    partial     recall only: unmatched predictions are not false positives, precision and F1 are undefined (None).
    none        not scored: the layer reports coverage `none` and adds nothing to a micro-average.
A mention or quote `region` limits both sides to spans inside it: a prediction outside the region is not a false
positive. A region on facts or relationships keeps gold claims whose evidence lies inside it and makes the layer
recall only, since predicted claims have no position.

Zero denominators
    precision = None when nothing was predicted on an exhaustive layer (or the layer is partial); recall = None when
    there is no gold; F1 = None when there is neither gold nor prediction or the layer is partial, otherwise
    2PR/(P+R) with an undefined side read as 0 (gold but no prediction scores F1 0; predictions but no gold score
    F1 0). Accuracies are None when nothing was matched. B-cubed precision / recall are None when their side is
    empty. Micro-averages sum the counts and apply the same rules; precision uses only exhaustive chapters.

Duplicates
    A predicted mention repeating a span (or span and type) already predicted is a false positive. Predicted facts
    or relationships repeating a tuple count once (an extractor may state a fact at each mention). Gold claims
    sharing a tuple merge, pooling their claimants and assertions.

Entities
    The scorer must say which gold entity each predicted mention names. In order:
      exact / overlap   the gold mention the prediction aligns to (overlapping spans, one to one, largest overlap
                        first), over every gold mention inside or outside the region; a prediction aligned to a gold
                        mention whose entity is null names nothing; one aligned to a pending (ignored) gold mention
                        goes on to the name step
      name              otherwise the one entity whose name or alias equals the mention text (casefolded); a text
                        matching several entities names nothing (`ambiguous_name`)
    A clustered mention names the entity most members of its predicted cluster name (the extractor's entity is the
    cluster); a tie names nothing (`cluster_tie`). The result is labelled `cluster` when the winning entity is
    backed by an aligned member, `cluster_name` when only by name matches.
    `name` and `cluster_name` are fallbacks: they rest on the scorer's string matching, not on a gold mention.
    `diagnostics` counts every predicted mention by source, lists each fallback mapping and each ambiguity, and each
    claim layer reports `tp_fallback`, the true positives with an endpoint resolved by a fallback, and
    `unresolved`, predictions with an endpoint naming nothing (always false positives).

Metrics (counts: tp / fp / fn with precision / recall / F1; accuracies: correct / total)
    mentions_exact          span identical
    mentions_overlap        spans overlap (the alignment above)
    mentions_typed          span identical and same type
    mention_linking         accuracy over predicted mentions aligned to a gold mention with an entity: names it
    coreference_b3          B-cubed over gold mentions with an entity in the region, clustered by entity key;
                            predicted mentions map to gold mentions through the alignment, unaligned ones stay as
                            their own items (mentions aligned to null-entity or pending gold mentions are left out)
    coreference_b3_linked   the same on mentions both sides have: linking quality apart from mention detection
    facts                   (entity, property, value); values casefolded and whitespace-normalized; `status` facts
                            compare `status_value`, `age` facts also match on `age_years`
    relationships           (subject, predicate, object); symmetric predicates unordered, CHILD_OF read as PARENT_OF
                            reversed
    relationships_lenient   the same with FATHER_OF / MOTHER_OF / PARENT_OF all read as PARENT_OF
    claim_attribution       accuracy over matched facts and relationships: the predicted claimant is a claimant of
                            the gold claim (narration matches narration; an unresolved claimant matches nothing)
    claim_assertion         accuracy over matched facts and relationships: same assertion value
    quotes_overlap          quote spans overlap (a gold quote spans its first to last piece)
    quote_speaker           accuracy over aligned quotes: the predicted speaker is the gold speaker
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Sequence, Set, Tuple

from app.evaluation.score import align

Span = Tuple[int, int]
GOLD_STATUSES = ("accepted", "corrected")
REVIEWED = ("reviewed", "adjudicated")
SYMMETRIC = {"FRIEND_OF", "ENEMY_OF", "SIBLING_OF", "MARRIED_TO", "ENGAGED_TO", "ALLY_OF", "KNOWS", "RELATED_TO"}
PARENT = {"FATHER_OF", "MOTHER_OF", "PARENT_OF"}
STATUS_VALUES = {"ALIVE", "DEAD", "MISSING", "INJURED", "UNCONSCIOUS", "OTHER"}
COUNTS = ("mentions_exact", "mentions_overlap", "mentions_typed", "facts", "relationships", "relationships_lenient",
          "quotes_overlap")
CLAIMS = ("facts", "relationships", "relationships_lenient")
ACCURACIES = ("mention_linking", "claim_attribution", "claim_assertion", "quote_speaker")
B3 = ("coreference_b3", "coreference_b3_linked")
B3_KEYS = ("p_num", "p_den", "r_num", "r_den")
SOURCES = ("exact", "overlap", "name", "cluster", "cluster_name", "aligned_to_null", "ambiguous_name", "cluster_tie",
           "unresolved")
FALLBACK = ("name", "cluster_name")
UNRESOLVED = "<unresolved>"        # a claimant that names nothing: never equal to a gold claimant


# ---------------------------------------------------------------------------------------------------- rates
def counts(tp: int = 0, fp: int = 0, fn: int = 0, coverage: str = "exhaustive", **extra: int) -> Dict[str, Any]:
    """A count metric for one chapter: precision counts only when the layer is exhaustive."""
    c = {"coverage": coverage, "tp": tp, "fp": fp, "fn": fn, "p_tp": tp if coverage == "exhaustive" else 0,
         "exhaustive": int(coverage == "exhaustive"), "partial": int(coverage == "partial"), **extra}
    return {**c, **rates(c)}


def rates(c: Dict[str, Any]) -> Dict[str, Optional[float]]:
    measurable = c["exhaustive"] > 0
    p = c["p_tp"] / (c["p_tp"] + c["fp"]) if measurable and c["p_tp"] + c["fp"] else None
    r = c["tp"] / (c["tp"] + c["fn"]) if c["tp"] + c["fn"] else None
    if not measurable or c["tp"] + c["fp"] + c["fn"] == 0:
        f1 = None
    else:
        p0, r0 = p or 0.0, r or 0.0
        f1 = 2 * p0 * r0 / (p0 + r0) if p0 + r0 else 0.0
    rnd = lambda x: None if x is None else round(x, 4)
    return {"precision": rnd(p), "recall": rnd(r), "f1": rnd(f1)}


def accuracy(correct: int, total: int) -> Dict[str, Any]:
    return {"correct": correct, "total": total, "accuracy": round(correct / total, 4) if total else None}


def b3(c: Dict[str, float]) -> Dict[str, Any]:
    p = c["p_num"] / c["p_den"] if c["p_den"] else None
    r = c["r_num"] / c["r_den"] if c["r_den"] else None
    if p is None and r is None:
        f1 = None
    else:
        p0, r0 = p or 0.0, r or 0.0
        f1 = 2 * p0 * r0 / (p0 + r0) if p0 + r0 else 0.0
    rnd = lambda x: None if x is None else round(x, 4)
    return {**c, "precision": rnd(p), "recall": rnd(r), "f1": rnd(f1)}


def _side(a: Sequence[FrozenSet[str]], b: Sequence[FrozenSet[str]]) -> Tuple[float, int]:
    """B-cubed in entity-overlap form: sum of |A ∩ B|² / |A| over cluster pairs, and the number of items in `a`."""
    return sum(len(x & y) ** 2 / len(x) for x in a for y in b), sum(len(x) for x in a)


# ---------------------------------------------------------------------------------------------------- helpers
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


class _Gold:
    """The gold items that count, and the pending ones that are ignored, for one chapter."""

    def __init__(self, doc: Dict[str, Any], include_pending: bool):
        def split(items):
            counts = [include_pending or i.get("review", {}).get("status") in GOLD_STATUSES for i in items]
            return ([i for i, c in zip(items, counts) if c], [i for i, c in zip(items, counts) if not c])
        self.entities, _ = split(doc["entities"])
        self.mentions, self.ignored_mentions = split(doc["mentions"])
        self.facts, self.ignored_facts = split(doc["facts"])
        self.relationships, self.ignored_relationships = split(doc["relationships"])
        self.quotes, self.ignored_quotes = split(doc["quotes"])


class _Resolver:
    """Predicted mention id -> (gold entity key or None, source), as described under Entities."""

    def __init__(self, pred: Dict[str, Any], gold: _Gold):
        self.by_id = {m["mention_id"]: m for m in pred.get("mentions", [])}
        p_spans = {mid: sp for mid, m in self.by_id.items() if (sp := _span(m))}
        g = {m["mention_id"]: m for m in gold.mentions + gold.ignored_mentions}
        counted = {m["mention_id"] for m in gold.mentions}
        aligned = align(p_spans, {gid: (m["start"], m["end"]) for gid, m in g.items()})
        names: Dict[str, Set[str]] = {}
        for e in gold.entities:
            for name in {e["name"], *e.get("aliases", [])}:
                names.setdefault(_norm(name), set()).add(e["entity_key"])
        self.own: Dict[str, Tuple[Optional[str], str]] = {}
        for mid, m in self.by_id.items():
            if mid in aligned and aligned[mid] in counted:
                gm = g[aligned[mid]]
                source = "exact" if p_spans[mid] == (gm["start"], gm["end"]) else "overlap"
                self.own[mid] = (gm["entity_key"], source) if gm["entity_key"] else (None, "aligned_to_null")
            else:
                named = names.get(_norm(m.get("text", "")), set())
                self.own[mid] = ((next(iter(named)), "name") if len(named) == 1
                                 else (None, "ambiguous_name") if named else (None, "unresolved"))
        self.cluster = {mid: [x for x in c["mentions"] if x in self.by_id]
                        for c in pred.get("coreference_clusters", []) for mid in c["mentions"]}

    def __call__(self, mid: Any) -> Tuple[Optional[str], str]:
        if mid not in self.by_id:
            return None, "unresolved"
        members = self.cluster.get(mid) or [mid]
        if len(members) == 1:
            return self.own[mid]
        votes = Counter(k for m in members if (k := self.own[m][0]) is not None).most_common()
        if not votes:
            return None, "unresolved"
        if len(votes) > 1 and votes[0][1] == votes[1][1]:
            return None, "cluster_tie"
        key = votes[0][0]
        if self.own[mid][0] == key:
            return self.own[mid]
        backed = any(self.own[m][0] == key and self.own[m][1] in ("exact", "overlap") for m in members)
        return key, "cluster" if backed else "cluster_name"

    def diagnostics(self) -> Dict[str, Any]:
        resolved = {mid: self(mid) for mid in self.by_id}
        by_source = Counter(src for _, src in resolved.values())
        listing = lambda sources: [{"mention_id": mid, "text": self.by_id[mid].get("text"), "entity_key": key,
                                    "source": src} for mid, (key, src) in resolved.items() if src in sources]
        return {"mention_sources": {s: by_source.get(s, 0) for s in SOURCES},
                "fallback_mappings": listing(FALLBACK),
                "uncertain_mappings": listing(("ambiguous_name", "cluster_tie"))}


def _relation(subject: Any, predicate: Any, obj: Any, lenient: bool) -> Tuple[Any, Any, Any]:
    if predicate == "CHILD_OF":
        subject, predicate, obj = obj, "PARENT_OF", subject
    if lenient and predicate in PARENT:
        predicate = "PARENT_OF"
    if predicate in SYMMETRIC and str(obj) < str(subject):
        subject, obj = obj, subject
    return subject, predicate, obj


def _fact_keys(key: Any, prop: Any, item: Dict[str, Any]) -> Set[Tuple[Any, Any, str]]:
    value = _norm(item.get("value", ""))
    if prop == "status":
        sv = item.get("status_value") or value.upper()
        return {(key, prop, sv if sv in STATUS_VALUES else value)}
    keys = {(key, prop, value)}
    if prop == "age" and item.get("age_years") is not None:
        keys.add((key, prop, str(item["age_years"])))
    elif prop == "age" and value.isdigit():
        keys.add((key, prop, str(int(value))))
    return keys


def _score_claims(preds: List[Dict[str, Any]], gold_claims: List[Dict[str, Any]], ignored: List[Dict[str, Any]],
                  coverage: str) -> Tuple[Dict[str, Any], List[Tuple[Dict, Dict]]]:
    """Each claim: {keys, claimant, assertion} (+ for predictions: fallback, unresolved). One-to-one, in order."""
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
    seen: Set[Any] = set()
    matched: List[Tuple[Dict, Dict]] = []
    taken: Set[int] = set()
    fp = 0
    for p in preds:
        if p["keys"] & seen:
            continue                                        # a repeated tuple counts once
        seen |= p["keys"]
        hit = next((n for n, g in enumerate(merged) if n not in taken and g["keys"] & p["keys"]), None)
        if hit is not None:
            taken.add(hit)
            matched.append((p, merged[hit]))
        elif not (p["keys"] & ignore_keys) and coverage == "exhaustive":
            fp += 1
    tp = len(matched)
    return counts(tp, fp, len(merged) - tp, coverage, tp_fallback=sum(p["fallback"] for p, _ in matched),
                  unresolved=sum(p["unresolved"] for p in preds)), matched


# ---------------------------------------------------------------------------------------------------- score
def score_document_v2(pred: Dict[str, Any], gold_doc: Dict[str, Any], include_pending: bool = False) -> Dict[str, Any]:
    if pred.get("text") != gold_doc["text"]:
        raise ValueError(f"{gold_doc['doc_id']}: the prediction's text differs from the gold text")
    gold = _Gold(gold_doc, include_pending)
    resolve = _Resolver(pred, gold)
    res: Dict[str, Any] = {"doc_id": gold_doc["doc_id"], "provisional": include_pending}
    p_mentions = pred.get("mentions", [])
    res["pred_unanchored"] = sum(_span(m) is None for m in p_mentions)

    # ------------------------------------------------------------ mentions and coreference
    coverage, region = _layer(gold_doc, "mentions")
    g_in = {m["mention_id"]: (m["start"], m["end"]) for m in gold.mentions if _inside((m["start"], m["end"]), region)}
    i_in = {m["mention_id"]: (m["start"], m["end"]) for m in gold.ignored_mentions
            if _inside((m["start"], m["end"]), region)}
    p_in = [(m["mention_id"], sp, m.get("type")) for m in p_mentions if (sp := _span(m)) and _inside(sp, region)]
    if coverage == "none":
        for k in ("mentions_exact", "mentions_overlap", "mentions_typed"):
            res[k] = counts(coverage="none")
        res["mention_linking"] = accuracy(0, 0)
        for k in B3:
            res[k] = b3({k2: 0 for k2 in B3_KEYS})
    else:
        ignore_spans = set(i_in.values()) - set(g_in.values())
        g_typed = {(sp, m["type"]) for m in gold.mentions if (sp := (m["start"], m["end"])) in set(g_in.values())}

        def exact_counts(key_of, gold_keys):
            tp = fp = 0
            hit: Set[Any] = set()
            for mid, sp, typ in p_in:
                k = key_of(sp, typ)
                if k in gold_keys and k not in hit:
                    hit.add(k)
                    tp += 1
                elif sp not in ignore_spans and coverage == "exhaustive":
                    fp += 1
            return counts(tp, fp, len(gold_keys) - tp, coverage)

        res["mentions_exact"] = exact_counts(lambda sp, typ: sp, set(g_in.values()))
        res["mentions_typed"] = exact_counts(lambda sp, typ: (sp, typ), g_typed)
        m_align = align({mid: sp for mid, sp, _ in p_in}, {**g_in, **i_in})
        tp = sum(1 for gid in m_align.values() if gid in g_in)
        fp = len(p_in) - len(m_align) if coverage == "exhaustive" else 0
        res["mentions_overlap"] = counts(tp, fp, len(g_in) - tp, coverage)

        g_key = {m["mention_id"]: m["entity_key"] for m in gold.mentions}
        linked = [(pid, gid) for pid, gid in m_align.items() if gid in g_in and g_key[gid] is not None]
        res["mention_linking"] = accuracy(sum(resolve(pid)[0] == g_key[gid] for pid, gid in linked), len(linked))

        keyed = {gid for gid in g_in if g_key[gid] is not None}
        by_key: Dict[str, Set[str]] = {}
        for gid in keyed:
            by_key.setdefault(g_key[gid], set()).add(gid)
        key_clusters = [frozenset(v) for v in by_key.values()]
        in_ids = {mid for mid, _, _ in p_in}
        drop = {pid for pid, gid in m_align.items() if gid not in keyed}     # aligned to null-entity or pending gold
        clustered = {mid for c in pred.get("coreference_clusters", []) for mid in c["mentions"]}
        groups = [c["mentions"] for c in pred.get("coreference_clusters", [])]
        groups += [[mid] for mid in in_ids if mid not in clustered]
        for name, linked_only in (("coreference_b3", False), ("coreference_b3_linked", True)):
            response = []
            for grp in groups:
                ids = frozenset(m_align[m] if m in m_align else f"pred:{m}" for m in grp
                                if m in in_ids and m not in drop and (m in m_align or not linked_only))
                if ids:
                    response.append(ids)
            key = key_clusters
            if linked_only:
                present = set().union(*response) if response else set()
                key = [k for c in key_clusters if (k := c & present)]
            r_num, r_den = _side(key, response)
            p_num, p_den = _side(response, key)
            res[name] = b3({"p_num": p_num, "p_den": p_den, "r_num": r_num, "r_den": r_den})

    # ------------------------------------------------------------ facts and relationships
    def endpoint(mid: Any, flags: Dict[str, bool]) -> Optional[str]:
        key, source = resolve(mid)
        flags["fallback"] |= source in FALLBACK
        flags["unresolved"] |= key is None
        return key

    def claimant(item: Dict[str, Any], flags: Dict[str, bool]) -> Optional[str]:
        if item.get("claimed_by_mention_id") is None:
            return None
        key, source = resolve(item["claimed_by_mention_id"])
        flags["fallback"] |= source in FALLBACK
        return key if key is not None else UNRESOLVED

    def gold_claims(items: Iterable[Dict[str, Any]], keys) -> List[Dict[str, Any]]:
        return [{"keys": keys(i), "claimant": i.get("claimed_by"), "assertion": i["assertion"]} for i in items]

    def in_region(items: Iterable[Dict[str, Any]], region: Optional[Span]) -> List[Dict[str, Any]]:
        return [i for i in items if _inside((i["evidence"]["start"], i["evidence"]["end"]), region)]

    matched_claims: List[Tuple[Dict, Dict]] = []
    coverage, region = _layer(gold_doc, "facts")
    if region is not None and coverage == "exhaustive":
        coverage = "partial"
    if coverage == "none":
        res["facts"] = counts(coverage="none", tp_fallback=0, unresolved=0)
    else:
        fact_keys = lambda f: _fact_keys(f["entity_key"], f["property"], f)
        preds = []
        for n, f in enumerate(pred.get("facts", [])):
            flags = {"fallback": False, "unresolved": False}
            key = endpoint(f.get("entity_mention_id"), flags)
            preds.append({"keys": _fact_keys(key, f.get("property"), f) if key else {("unresolved", n)},
                          "claimant": claimant(f, flags), "assertion": f.get("assertion", "asserted"), **flags})
        res["facts"], matched = _score_claims(preds, gold_claims(in_region(gold.facts, region), fact_keys),
                                              gold_claims(gold.ignored_facts, fact_keys), coverage)
        matched_claims += matched

    coverage, region = _layer(gold_doc, "relationships")
    if region is not None and coverage == "exhaustive":
        coverage = "partial"
    for name, lenient in (("relationships", False), ("relationships_lenient", True)):
        if coverage == "none":
            res[name] = counts(coverage="none", tp_fallback=0, unresolved=0)
            continue
        rel_keys = lambda r: {_relation(r["subject_entity_key"], r["predicate"], r["object_entity_key"], lenient)}
        preds = []
        for n, r in enumerate(pred.get("relationships", [])):
            flags = {"fallback": False, "unresolved": False}
            s, o = endpoint(r.get("subject_mention_id"), flags), endpoint(r.get("object_mention_id"), flags)
            preds.append({"keys": {_relation(s, r.get("predicate"), o, lenient)} if s and o else {("unresolved", n)},
                          "claimant": claimant(r, flags), "assertion": r.get("assertion", "asserted"), **flags})
        res[name], matched = _score_claims(preds, gold_claims(in_region(gold.relationships, region), rel_keys),
                                           gold_claims(gold.ignored_relationships, rel_keys), coverage)
        if not lenient:
            matched_claims += matched
    res["claim_attribution"] = accuracy(sum(p["claimant"] in g["claimants"] for p, g in matched_claims),
                                        len(matched_claims))
    res["claim_assertion"] = accuracy(sum(p["assertion"] in g["assertions"] for p, g in matched_claims),
                                      len(matched_claims))

    # ------------------------------------------------------------ quotes
    coverage, region = _layer(gold_doc, "quotes")
    whole = lambda q: (q["spans"][0]["start"], q["spans"][-1]["end"])
    g_q = {q["quote_id"]: whole(q) for q in gold.quotes if _inside(whole(q), region)}
    i_q = {q["quote_id"]: whole(q) for q in gold.ignored_quotes if _inside(whole(q), region)}
    p_q = {n: sp for n, q in enumerate(pred.get("quotes", [])) if (sp := _span(q)) and _inside(sp, region)}
    if coverage == "none":
        res["quotes_overlap"], res["quote_speaker"] = counts(coverage="none"), accuracy(0, 0)
    else:
        q_align = align(p_q, {**g_q, **i_q})
        tp = sum(1 for gid in q_align.values() if gid in g_q)
        res["quotes_overlap"] = counts(tp, len(p_q) - len(q_align) if coverage == "exhaustive" else 0,
                                       len(g_q) - tp, coverage)
        speaker = {q["quote_id"]: q["speaker_entity_key"] for q in gold.quotes}
        pairs = [(n, gid) for n, gid in q_align.items() if gid in g_q]
        res["quote_speaker"] = accuracy(
            sum(resolve(pred["quotes"][n].get("speaker_mention_id"))[0] == speaker[gid] for n, gid in pairs),
            len(pairs))

    res["gold_counted"] = {"mentions": len(g_in) if _layer(gold_doc, "mentions")[0] != "none" else 0,
                           "facts": len(gold.facts), "relationships": len(gold.relationships), "quotes": len(g_q)}
    res["gold_ignored_pending"] = {"mentions": len(gold.ignored_mentions), "facts": len(gold.ignored_facts),
                                   "relationships": len(gold.ignored_relationships), "quotes": len(gold.ignored_quotes)}
    res["diagnostics"] = resolve.diagnostics()
    return res


def micro_average_v2(per_doc: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Sums counts over chapters, then recomputes the rates with the same zero-denominator rules."""
    out: Dict[str, Any] = {"provisional": any(d["provisional"] for d in per_doc), "documents": len(per_doc)}
    for m in COUNTS:
        keys = ("tp", "fp", "fn", "p_tp", "exhaustive", "partial") + (("tp_fallback", "unresolved") if m in CLAIMS
                                                                       else ())
        c = {k: sum(d[m][k] for d in per_doc) for k in keys}
        c["coverage"] = ("none" if not c["exhaustive"] + c["partial"] else "exhaustive" if not c["partial"]
                         else "partial" if not c["exhaustive"] else "mixed")
        out[m] = {**c, **rates(c)}
    for m in ACCURACIES:
        out[m] = accuracy(sum(d[m]["correct"] for d in per_doc), sum(d[m]["total"] for d in per_doc))
    for m in B3:
        out[m] = b3({k: sum(d[m][k] for d in per_doc) for k in B3_KEYS})
    for key in ("gold_counted", "gold_ignored_pending"):
        out[key] = {k: sum(d[key][k] for d in per_doc) for k in per_doc[0][key]} if per_doc else {}
    out["pred_unanchored"] = sum(d["pred_unanchored"] for d in per_doc)
    out["diagnostics"] = {"mention_sources": {s: sum(d["diagnostics"]["mention_sources"][s] for d in per_doc)
                                              for s in SOURCES}}
    return out


def format_table_v2(scores: Dict[str, Any]) -> str:
    f = lambda x: "   n/a" if x is None else f"{x:6.3f}"
    rows = []
    if scores["provisional"]:
        rows.append("PROVISIONAL: pending (unreviewed) items counted as gold. Development only; never report these.")
    rows.append(f"{'metric':24s} {'P':>6s} {'R':>6s} {'F1':>6s} {'tp':>5s} {'fp':>5s} {'fn':>5s}  coverage")
    for m in COUNTS:
        s = scores[m]
        extra = f"  (tp via fallback {s['tp_fallback']}, unresolved predictions {s['unresolved']})" if m in CLAIMS \
            else ""
        rows.append(f"{m:24s} {f(s['precision'])} {f(s['recall'])} {f(s['f1'])} {s['tp']:5d} {s['fp']:5d} "
                    f"{s['fn']:5d}  {s['coverage']}{extra}")
    for m in B3:
        s = scores[m]
        rows.append(f"{m:24s} {f(s['precision'])} {f(s['recall'])} {f(s['f1'])}")
    for m in ACCURACIES:
        s = scores[m]
        rows.append(f"{m:24s} accuracy {f(s['accuracy'])}  ({s['correct']}/{s['total']})")
    src = scores["diagnostics"]["mention_sources"]
    rows.append("predicted mentions by entity source: " + ", ".join(f"{k} {v}" for k, v in src.items() if v))
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
