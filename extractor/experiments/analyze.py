"""
Score a prediction directory against the reviewed gold v2 chapters and write the claim diagnosis.

    python -m experiments.analyze PRED_DIR OUT_DIR [--map-predicates] [--containment]

Writes OUT_DIR/score.json (same numbers as `score-v2`), OUT_DIR/diagnosis.json (every claim classified) and
OUT_DIR/summary.json. With --map-predicates, the predictions are first rewritten with `claims.map_predicates` into
OUT_DIR/pred/ (the input directory is never modified) and the mapping log is added to the summary.
"""
import argparse
import json
import sys
from pathlib import Path

import extractor  # noqa: F401  (puts ../backend on sys.path)
from app.evaluation.score_v2 import REVIEWED, format_table_v2, micro_average_v2, score_document_v2
from experiments.claims import ContainmentResolver, diagnose, jsonable, map_predicates, summarize

GOLD = Path(__file__).resolve().parents[2] / "gold" / "v2"


def reviewed_gold():
    for path in sorted(GOLD.rglob("ch*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if doc["annotation"]["status"] in REVIEWED:
            yield doc


def run(pred_dir: Path, out: Path, map_preds: bool = False, containment: bool = False) -> dict:
    """`containment`: score and diagnose with claims.ContainmentResolver (a diagnostic, not the official score)."""
    import app.evaluation.score_v2 as score_v2
    official = score_v2._Resolver
    if containment:
        score_v2._Resolver = ContainmentResolver           # only for this call; restored below
    try:
        return _run(pred_dir, out, map_preds, ContainmentResolver if containment else official)
    finally:
        score_v2._Resolver = official


def _run(pred_dir: Path, out: Path, map_preds: bool, resolver: type) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    scores, diags, log = [], [], {}
    for gold in reviewed_gold():
        src = pred_dir / f"{gold['doc_id']}.json"
        pred = json.loads(src.read_text(encoding="utf-8")) if src.exists() else {"text": gold["text"]}
        if map_preds:
            pred, counts = map_predicates(pred)
            log[gold["doc_id"]] = dict(counts)
            dst = out / "pred" / f"{gold['doc_id']}.json"
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(json.dumps(pred, ensure_ascii=False, indent=1), encoding="utf-8")
        scores.append(score_document_v2(pred, gold))
        diags.append(diagnose(pred, gold, resolver))
    micro = micro_average_v2(scores)
    summary = {"micro": {k: micro[k] for k in ("facts", "relationships", "relationships_lenient", "mentions_exact",
                                               "mentions_overlap", "coreference_b3", "coreference_b3_linked",
                                               "mention_linking")},
               "claims": summarize(diags), **({"predicate_mapping": log} if map_preds else {})}
    (out / "score.json").write_text(json.dumps({"chapters": scores, "micro": micro}, indent=1), encoding="utf-8")
    (out / "diagnosis.json").write_text(json.dumps(jsonable(diags), ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(jsonable(summary), ensure_ascii=False, indent=1, default=str),
                                      encoding="utf-8")
    print(format_table_v2(micro))
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pred_dir")
    ap.add_argument("out_dir")
    ap.add_argument("--map-predicates", action="store_true")
    ap.add_argument("--containment", action="store_true", help="diagnostic resolver (claims.ContainmentResolver)")
    a = ap.parse_args()
    run(Path(a.pred_dir), Path(a.out_dir), a.map_predicates, a.containment)
    sys.exit(0)
