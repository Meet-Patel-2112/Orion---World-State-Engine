"""
Command line (run from backend/):

    python -m app.evaluation convert ANNOTATION.json... --text-dir STORIES_DIR --out-dir GOLD_DIR
        teammate annotation files -> gold documents GOLD_DIR/<story_id>.json (+ <story_id>.issues.txt)

    python -m app.evaluation score GOLD_DIR PRED_DIR [--json OUT.json]
        per-story and micro-averaged scores; a story without a prediction is scored as an empty prediction

    python -m app.evaluation pdnc WORK.json --pdnc-dir PDNC_NOVEL_DIR --revision SHA [--reference-text FILE] [--force]
        gold v2 drafts from the Project Dialogism Novel Corpus: one chNN.json (+ chNN.issues.txt) per chapter listed
        in WORK.json (or only --chapters 3,22), written next to it; an existing chNN.json is kept unless --force

    python -m app.evaluation validate-v2 PATH...
        check gold v2 chapter files (or every ch*.json under a directory) and the chapters of each work together

Predictions come from ../extractor (`python -m extractor predict` there).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from app.evaluation import pdnc
from app.evaluation.convert import convert_annotation
from app.evaluation.gold_v2 import doc_errors, work_errors
from app.evaluation.score import format_table, micro_average, score_document

LISTS = ("mentions", "coreference_clusters", "events", "relationships", "facts", "temporal_expressions",
         "temporal_relations")


def _write(out_dir: Path, story_id: str, doc: Dict[str, Any], issues: List[str]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{story_id}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / f"{story_id}.issues.txt").write_text("".join(f"{i}\n" for i in issues), encoding="utf-8")


def cmd_convert(args: argparse.Namespace) -> int:
    for path in args.annotations:
        ann = json.loads(Path(path).read_text(encoding="utf-8"))
        text = (Path(args.text_dir) / ann["source_file"]).read_text(encoding="utf-8")
        doc, issues = convert_annotation(ann, text)
        _write(Path(args.out_dir), doc["story_id"], doc, issues)
        schema = sum(i.startswith("schema:") for i in issues)
        print(f"{doc['story_id']}: {len(doc['mentions'])} mentions, {len(doc['events'])} events, "
              f"{len(issues)} issues ({schema} schema errors)")
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    per_story = []
    for gold_path in sorted(Path(args.gold_dir).glob("*.json")):
        gold = json.loads(gold_path.read_text(encoding="utf-8"))
        pred_path = Path(args.pred_dir) / gold_path.name
        pred = (json.loads(pred_path.read_text(encoding="utf-8")) if pred_path.exists()
                else {"text": gold["text"], **{k: [] for k in LISTS}})
        s = score_document(pred, gold)
        per_story.append(s)
        print(f"\n== {gold['story_id']}{'' if pred_path.exists() else '  (no prediction)'}\n{format_table(s)}")
    total = micro_average(per_story)
    print(f"\n== MICRO AVERAGE over {len(per_story)} stories\n{format_table(total)}")
    if args.json:
        Path(args.json).write_text(json.dumps({"stories": per_story, "micro": total}, indent=1), encoding="utf-8")
    return 0


def cmd_pdnc(args: argparse.Namespace) -> int:
    import csv
    work_path = Path(args.work)
    config = json.loads(work_path.read_text(encoding="utf-8"))
    novel_dir = Path(args.pdnc_dir)
    text = pdnc_text = (novel_dir / "novel_text.txt").read_text(encoding="utf-8")
    offset_map = None
    if args.reference_text:
        reference = Path(args.reference_text).read_text(encoding="utf-8-sig")
        mode = config.get("reference_text", {}).get("mode", "char")
        text, restored, unmatched, offset_map = pdnc.restore_from_reference(text, reference, mode)
        print(f"restored {restored} characters from {args.reference_text} (mode {mode}); {len(unmatched)} lines "
              "left as they were")
    read = lambda name: list(csv.DictReader((novel_dir / name).open(encoding="utf-8")))
    characters = pdnc.Characters(read("character_info.csv"), config)
    quote_rows = read("quotation_info.csv")
    chapters = pdnc.split_chapters(text)
    for number in args.chapters or config["chapters"]:
        doc, issues = pdnc.convert_chapter(text, quote_rows, characters, config, number, chapters[number - 1],
                                           args.revision, pdnc_text, offset_map)
        issues += [f"validation: {e}" for e in doc_errors(doc)]
        out = work_path.parent / f"ch{number:02d}.json"
        (work_path.parent / f"ch{number:02d}.issues.txt").write_text("".join(f"{i}\n" for i in issues),
                                                                     encoding="utf-8")
        status = "kept (exists; --force to replace)" if out.exists() and not args.force else "written"
        if status == "written":
            out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"{doc['doc_id']}: {len(doc['text'])} chars, {len(doc['entities'])} entities, {len(doc['quotes'])} "
              f"quotes, {len(doc['mentions'])} mentions, {len(issues)} issues; {status}")
    return 0


def cmd_validate_v2(args: argparse.Namespace) -> int:
    paths = []
    for p in map(Path, args.paths):
        paths += sorted(p.rglob("ch*.json")) if p.is_dir() else [p]
    docs, failed = [], 0
    for path in paths:
        doc = json.loads(path.read_text(encoding="utf-8"))
        errors = doc_errors(doc)
        failed += bool(errors)
        print(f"{path}: {'OK' if not errors else f'{len(errors)} errors'}")
        for e in errors:
            print(f"  {e}")
        if not errors:
            docs.append(doc)
    across = work_errors(docs)
    for e in across:
        print(f"across chapters: {e}")
    print(f"{len(paths)} documents, {failed} with errors, {len(across)} cross-chapter errors")
    return 1 if failed or across else 0


def main(argv: List[str] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.evaluation", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("convert")
    c.add_argument("annotations", nargs="+")
    c.add_argument("--text-dir", required=True)
    c.add_argument("--out-dir", required=True)
    s = sub.add_parser("score")
    s.add_argument("gold_dir")
    s.add_argument("pred_dir")
    s.add_argument("--json")
    p = sub.add_parser("pdnc")
    p.add_argument("work")
    p.add_argument("--pdnc-dir", required=True)
    p.add_argument("--revision", required=True)
    p.add_argument("--reference-text")
    p.add_argument("--force", action="store_true")
    p.add_argument("--chapters", type=lambda s: [int(n) for n in s.split(",")],
                   help="only these chapters, e.g. 3,22 (default: every chapter in WORK.json)")
    v = sub.add_parser("validate-v2")
    v.add_argument("paths", nargs="+")
    args = ap.parse_args(argv)
    return {"convert": cmd_convert, "score": cmd_score, "pdnc": cmd_pdnc,
            "validate-v2": cmd_validate_v2}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
