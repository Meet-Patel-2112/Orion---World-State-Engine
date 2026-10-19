"""
Side-by-side tables for closed-question runs (e.g. NuExtract vs another model) against the production baseline.

    python -m experiments.closed_compare ORACLE_DIR OUT.md LABEL=CLOSED_DIR [LABEL=CLOSED_DIR ...]

Each CLOSED_DIR must hold a `closed_report` report.json and its experiments' analysis/ folders. Relationship errors
are split as in claims.diagnose: wrong predicate, wrong endpoint, unresolved endpoint, unsupported (false_positive:
a relationship between resolved entities that the gold does not have in any form).
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List

LAYER = {"probe": "facts", "facts": "facts", "rels-oracle": "relationships", "rels-candidates": "relationships"}


def fmt(s: Dict) -> str:
    p = "–" if s["precision"] is None else f"{s['precision']:.2f}"
    r = "–" if s["recall"] is None else f"{s['recall']:.2f}"
    f = "–" if s["f1"] is None else f"{s['f1']:.3f}"
    return f"{s['tp']} / {s['fp']} / {s['fn']} | {p} | {r} | {f}"


def main(argv: List[str]) -> int:
    oracle, out = Path(argv[0]), Path(argv[1])
    runs = {lab: Path(p) for lab, p in (a.split("=", 1) for a in argv[2:])}
    reports = {lab: json.loads((d / "report.json").read_text(encoding="utf-8")) for lab, d in runs.items()}
    base = next(iter(reports.values()))["baselines"]
    lines: List[str] = []
    w = lines.append
    chapters = sorted(base["A0 production"]["chapters"])
    short = lambda d: {"pride_and_prejudice/ch01": "Pride and Prejudice", "oliver_twist/ch01": "Oliver Twist",
                       "the_invisible_man/ch01": "The Invisible Man",
                       "the_mysterious_affair_at_styles/ch01": "Styles"}.get(d, d)

    for exp, layer in (("facts", "facts"), ("rels-oracle", "relationships"), ("rels-candidates", "relationships")):
        w(f"\n### {exp} ({layer}{'; ORACLE pairs, not production performance' if exp == 'rels-oracle' else ''})\n")
        cols = ["strict"] if layer == "facts" else ["strict", "lenient"]
        for col in cols:
            m = layer if col == "strict" else "relationships_lenient"
            w(f"\n{'Facts' if layer == 'facts' else 'Relationships, ' + col}: all chapters, then tp/fp/fn per chapter\n")
            w("| Run | tp / fp / fn | P | R | F1 | " + " | ".join(short(c) for c in chapters) + " |")
            w("| --- | --- | --- | --- | --- | " + " | ".join("---" for _ in chapters) + " |")
            rows = [("A0 production", base["A0 production"])]
            if layer == "relationships":
                rows.append(("C gold upstream (diagnostic resolver)", base["C (diagnostic containment resolver)"]))
            rows += [(f"{lab} closed", r["experiments"][exp]["scores"]) for lab, r in reports.items()
                     if exp in r["experiments"]]
            for name, s in rows:
                w(f"| {name} | {fmt(s['micro'][m])} | " + " | ".join(
                    f"{s['chapters'][c][m]['tp']}/{s['chapters'][c][m]['fp']}/{s['chapters'][c][m]['fn']}"
                    for c in chapters) + " |")
        w("")
        w("| Run | Answers (kept / none / invalid) | Evidence valid | " +
          ("Raw recall | Exact value agreement | Evidence overlaps gold (tp) |" if layer == "facts"
           else "Wrong predicate | Wrong endpoint | Unresolved endpoint | Unsupported |") +
          " Requests | Prompt / output tokens | Model s | Wall s |")
        w("| --- | --- | --- | " + ("--- | --- | --- |" if layer == "facts" else "--- | --- | --- | --- |") +
          " --- | --- | --- | --- |")
        for lab, r in reports.items():
            if exp not in r["experiments"]:
                continue
            e = r["experiments"][exp]
            a, c = e["answers"], e["cost"]
            ans = f"{a.get('kept', 0)} / {a.get('none', 0)} / {a.get('invalid', 0)}"
            if layer == "facts":
                mid = f"{e['raw_recall']} | {e['exact_value_agreement']} | {e['evidence_overlaps_gold_on_tp']} |"
            else:
                errs = Counter(x["class"] for x in e["errors"])
                mid = (f"{errs['wrong_predicate']} | {errs['wrong_endpoint']} | {errs['unresolved']} | "
                       f"{errs['false_positive']} |")
            wall = c.get("request_wall_seconds") or "–"
            w(f"| {lab} | {ans} | {e['evidence_valid']} | {mid} {c['requests']} | {c['prompt_tokens']:,} / "
              f"{c['output_tokens']:,} | {c['model_seconds']} | {wall} |")

    w("\n### Facts: precision per property (correct / predicted; gold count)\n")
    props = defaultdict(dict)
    gold_n = Counter()
    for lab, d in runs.items():
        diag_path = d / "facts" / "analysis" / "diagnosis.json"
        if not diag_path.exists():
            continue
        for doc in json.loads(diag_path.read_text(encoding="utf-8")):
            for p in doc["pred_facts"]:
                c = props[p["property"]].setdefault(lab, Counter())
                c["pred"] += 1
                c["tp"] += p["class"] == "tp"
            for g in doc["gold_facts"]:
                gold_n[(lab, g["gold"]["property"])] += 1
    labs = [lab for lab in runs if (runs[lab] / "facts" / "analysis").exists()]
    w("| Property | Gold | " + " | ".join(labs) + " |")
    w("| --- | --- | " + " | ".join("---" for _ in labs) + " |")
    for prop in sorted(props, key=lambda p: -max(props[p].get(l, Counter())["pred"] for l in labs)):
        cells = []
        for lab in labs:
            c = props[prop].get(lab, Counter())
            cells.append(f"{c['tp']}/{c['pred']}" + (f" ({c['tp'] / c['pred']:.2f})" if c["pred"] else ""))
        w(f"| {prop} | {gold_n[(labs[0], prop)]} | " + " | ".join(cells) + " |")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
