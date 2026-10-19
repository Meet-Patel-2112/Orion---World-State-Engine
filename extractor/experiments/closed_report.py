"""
Compare the closed-question experiments with the baseline (A0) and run C, per chapter and in aggregate.

    python -m experiments.closed_report CLOSED_DIR ORACLE_DIR OUT.json

Reads CLOSED_DIR/<experiment>/{pred,analysis,answers.json,run_meta.json} and ORACLE_DIR's A0 and C analyses (official
scorer; C also with the diagnostic containment resolver), and ORACLE_DIR/llm_raw.json for the production raw-answer
recall (8 of 28 facts). Facts:
    raw recall        gold facts with an answer for the right entity whose value contains, or is contained in, the
                      gold value (the llm_raw.py definition, so it compares with 8/28); any answer, kept or not
    scored            the official score-v2 counts on the kept facts
    exact agreement   of the gold facts found by raw recall, those whose kept value equals the gold value (normalized)
    evidence valid    of the non-none answers, those copied from their context (kept / (kept + invalid))
    evidence overlap  of the scored true positives, those whose evidence sentence overlaps the gold evidence
Relationships: scored strict and parentage-lenient counts, evidence validity, and for rels-oracle the recognition rate
(gold relationships found among the pairs asked about).
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

import extractor  # noqa: F401
from app.evaluation.score_v2 import REVIEWED, _Gold, _norm, _Resolver
from experiments.llm_raw import _contains

GOLD = Path(__file__).resolve().parents[2] / "gold" / "v2"
COUNT_KEYS = ("tp", "fp", "fn", "precision", "recall", "f1")


def gold_docs() -> Dict[str, Dict[str, Any]]:
    out = {}
    for p in sorted(GOLD.rglob("ch*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        if d["annotation"]["status"] in REVIEWED:
            out[d["doc_id"]] = d
    return out


def scores(analysis_dir: Path) -> Dict[str, Any]:
    s = json.loads((analysis_dir / "score.json").read_text(encoding="utf-8"))
    pick = lambda d: {m: {k: d[m][k] for k in COUNT_KEYS} for m in ("facts", "relationships", "relationships_lenient")}
    return {"micro": pick(s["micro"]), "chapters": {c["doc_id"]: pick(c) for c in s["chapters"]}}


def fact_details(exp_dir: Path, golds: Dict[str, Dict[str, Any]], upstream_dir: Path) -> Dict[str, Any]:
    answers = json.loads((exp_dir / "answers.json").read_text(encoding="utf-8"))
    diag = {d["doc_id"]: d for d in json.loads((exp_dir / "analysis" / "diagnosis.json").read_text(encoding="utf-8"))}
    per = defaultdict(lambda: {"raw_found": 0, "gold": 0, "exact": 0})
    recovered, false_pos = [], []
    results = Counter(a["result"] for a in answers)
    overlap = tps = 0
    for doc_id, gold in golds.items():
        upstream = json.loads((upstream_dir / f"{doc_id}.json").read_text(encoding="utf-8"))
        res = _Resolver(upstream, _Gold(gold, include_pending=False))
        from experiments.closed import Chapter
        ch = Chapter(upstream)
        key_of_group = {}
        for g, ms in ch.groups.items():
            votes = Counter(k for m in ms if (k := res(m["mention_id"])[0]))
            key_of_group[g] = votes.most_common(1)[0][0] if votes else None
        mine = [a for a in answers if a["doc_id"] == doc_id and a["value"]]
        for f in gold["facts"]:
            per[doc_id]["gold"] += 1
            hits = [a for a in mine if key_of_group.get(a["entity"]) == f["entity_key"] and a["property"] == f["property"]
                    and _contains(a["value"], f["value"])]
            if hits:
                per[doc_id]["raw_found"] += 1
                kept = [a for a in hits if a["result"] == "kept"]
                if any(_norm(a["value"]) == _norm(f["value"]) for a in kept):
                    per[doc_id]["exact"] += 1
        for p in diag[doc_id]["pred_facts"]:
            ev = p.get("evidence")
            text = " ".join(gold["text"][ev["start"]:ev["end"]].split()) if ev else ""
            if p["class"] == "tp":
                tps += 1
                gold_ev = [g["gold"]["evidence"] for g in diag[doc_id]["gold_facts"] if g["class"] == "found"
                           and g["gold"]["entity_key"] == p["entity"] and g["gold"]["property"] == p["property"]]
                if ev and any(e["start"] < ev["end"] and ev["start"] < e["end"] for e in gold_ev):
                    overlap += 1
                recovered.append({"doc_id": doc_id, "entity": p["entity"], "property": p["property"],
                                  "value": p["value"], "evidence": text})
            elif p["class"] in ("false_positive", "wrong_value", "wrong_entity"):
                false_pos.append({"doc_id": doc_id, "class": p["class"], "entity": p["entity"],
                                  "entity_text": p["entity_text"], "property": p["property"], "value": p["value"],
                                  "evidence": text})
    raw = sum(v["raw_found"] for v in per.values())
    return {"raw_recall": f"{raw}/{sum(v['gold'] for v in per.values())}",
            "raw_recall_per_chapter": {k: f"{v['raw_found']}/{v['gold']}" for k, v in per.items()},
            "exact_value_agreement": f"{sum(v['exact'] for v in per.values())}/{raw}",
            "answers": dict(results),
            "evidence_valid": f"{results['kept']}/{results['kept'] + results['invalid']}",
            "evidence_overlaps_gold_on_tp": f"{overlap}/{tps}", "recovered": recovered, "false_positives": false_pos}


def rel_details(exp_dir: Path) -> Dict[str, Any]:
    answers = json.loads((exp_dir / "answers.json").read_text(encoding="utf-8"))
    diag = json.loads((exp_dir / "analysis" / "diagnosis.json").read_text(encoding="utf-8"))
    results = Counter(a["result"] for a in answers)
    found, false_pos = [], []
    gold_by_doc = gold_docs()
    for d in diag:
        text = gold_by_doc[d["doc_id"]]["text"]
        for p in d["pred_relationships"]:
            ev = p.get("evidence")
            item = {"doc_id": d["doc_id"], "class": p["class"], "subject": p["subject"], "predicate": p["predicate"],
                    "object": p["object"], "evidence": " ".join(text[ev["start"]:ev["end"]].split()) if ev else ""}
            (found if p["class"] in ("tp", "lenient_only") else false_pos).append(item)
    return {"answers": dict(results), "evidence_valid": f"{results['kept']}/{results['kept'] + results['invalid']}",
            "pairs_asked": len({(a["doc_id"], tuple(a["pair"])) for a in answers}), "questions": len(answers),
            "found": found, "errors": false_pos,
            "gold": dict(Counter(g["class"] for d in diag for g in d["gold_relationships"]))}


def main(argv: List[str]) -> int:
    closed, oracle, out = Path(argv[0]), Path(argv[1]), Path(argv[2])
    golds = gold_docs()
    report = {"baselines": {"A0 production": scores(oracle / "A0_analysis"),
                            "C gold mentions+coref, production LLM (official)": scores(oracle / "C" / "analysis"),
                            "C (diagnostic containment resolver)": scores(oracle / "containment_C")},
              "production_raw_fact_recall": "8/28 (llm_raw.json)", "experiments": {}}
    for exp in ("probe", "facts", "rels-oracle", "rels-candidates"):
        d = closed / exp
        if not (d / "analysis" / "score.json").exists():
            continue
        meta = json.loads((d / "run_meta.json").read_text(encoding="utf-8"))
        entry = {"scores": scores(d / "analysis"), "cost": meta["cost_all_cached_requests"],
                 "questions_per_chapter": {c["doc_id"]: c["questions"] for c in meta["chapters"]}}
        entry.update(fact_details(d, golds, Path(meta["upstream"])) if exp in ("probe", "facts") else rel_details(d))
        report["experiments"][exp] = entry
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    for name, e in report["experiments"].items():
        m = e["scores"]["micro"]
        layer = "facts" if name in ("probe", "facts") else "relationships"
        line = {k: m[layer][k] for k in ("tp", "fp", "fn", "f1")}
        extra = (f" raw {e['raw_recall']} exact {e['exact_value_agreement']} evidence {e['evidence_valid']}"
                 if layer == "facts" else
                 f" lenient {m['relationships_lenient']['tp']}/{m['relationships_lenient']['fp']}/"
                 f"{m['relationships_lenient']['fn']} F1 {m['relationships_lenient']['f1']} evidence {e['evidence_valid']}")
        print(name, layer, line, extra, "| requests", e["cost"]["requests"], "model s", e["cost"]["model_seconds"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
