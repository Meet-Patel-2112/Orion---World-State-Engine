"""
The facts stage (`extractor.facts`, Qwen3.5 9B) replayed on a prediction directory's own mentions and coreference, so
it can be scored against NuExtract's facts with nothing else changed. This is how the stage was chosen (2026-10-19).

    python -m experiments.open_facts PRED_DIR OUT_DIR [--model qwen3.5:9b]

Writes OUT_DIR/pred/<doc_id>.json: the input documents with `facts` rebuilt as the deterministic title facts
(`relations.title_facts`) plus the stage's grounded answers. Calls are cached in OUT_DIR/llm_cache.json
(`closed.MeteredLLM`, the same request body as `llm.generate`), so a rerun costs nothing; run_meta.json has the cost.
"""
import argparse
import json
import time
from pathlib import Path

import extractor  # noqa: F401  (puts ../backend on sys.path)
from experiments.closed import MeteredLLM
from extractor import facts as F, relations as R
from extractor.mentions import spacy_nlp


def rebuild(doc, call: MeteredLLM) -> None:
    doc["facts"] = [{"fact_id": f"F{n}", "property": prop, "value": value, "entity_mention_id": mid}
                    for n, (mid, prop, value) in enumerate(R.title_facts(doc), 1)]
    F.grounded_facts(doc, lambda system, user, schema: call(system, user, schema, 1024)["answer"] or {},
                     spacy_nlp()(doc["text"]))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pred_dir")
    ap.add_argument("out_dir")
    ap.add_argument("--model", default="qwen3.5:9b")
    a = ap.parse_args(argv)
    out = Path(a.out_dir)
    call = MeteredLLM(out / "llm_cache.json", model=a.model, extra={"think": False})
    t0 = time.time()
    for path in sorted(Path(a.pred_dir).rglob("ch*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        rebuild(doc, call)
        target = out / "pred" / path.relative_to(a.pred_dir)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{doc['doc_id']}: {len(doc['facts'])} facts", flush=True)
    seconds = sum(e["seconds"] for e in call.store.values())
    (out / "run_meta.json").write_text(json.dumps({"model": a.model, "requests": len(call.store), "hits": call.hits,
                                                   "model_seconds": round(seconds, 1),
                                                   "wall_seconds": round(time.time() - t0, 1)}, indent=1))
    print(f"{len(call.store)} requests, {seconds:.0f} model s, {time.time() - t0:.0f} wall s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
