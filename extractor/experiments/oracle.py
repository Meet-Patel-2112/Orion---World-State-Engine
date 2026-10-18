"""
Oracle runs: the production pipeline's stages, in their production order, with the mention and coreference stages
optionally replaced by gold annotations. Nothing in extractor/extractor is changed.

    python -m experiments.oracle RUN OUT_DIR --cache LLM_CACHE.json GOLD_CHAPTER.json...

    A   mentions (GLiNER2) and coreference (BookNLP + link + merge) as in production
    B   gold mentions inside each chapter's mention region; coreference as in production, then any mention it adds
        inside the region is removed again, so the region's mention set is exactly the gold one
    C   B, then the clusters replaced: inside the region, gold mentions grouped by gold entity key (null-key mentions
        unclustered); a mention after the region joins the gold entity that most of its predicted cluster's
        in-region members belong to, or keeps its predicted cluster

Gold mentions exist only inside the mention region (all of chapter 1 except Styles, whose region ends at character
11,526), so after the region B and C keep the predicted mentions (GLiNER2) and C keeps predicted links for them.
Every LLM call goes through a cache keyed on the full request (system prompt, prompt, schema, length, model): run A
fills it, B and C replay it, so NuExtract's answers are identical across runs and only what the mentions and
clusters do downstream (which chunks are asked, which answers ground to a mention, entity grouping, role and title
rules) can change. Misses are called live and counted.
"""
import argparse
import hashlib
import inspect
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import extractor  # noqa: F401  (puts ../backend on sys.path)
from extractor import events as events_module, llm, relations as relations_module
from extractor.coref import coref
from extractor.events import events, llm_types
from extractor.mentions import mentions
from extractor.pipeline import LISTS, release_encoders, release_llm
from extractor.relations import relations
from extractor.temporal import temporal
from app.contracts.gold import GOLD_SCHEMA_VERSION
from app.evaluation.schema import schema_errors


# ---------------------------------------------------------------- LLM cache
class CachedLLM:
    def __init__(self, path: Path):
        self.path, self.hits, self.misses = path, 0, 0
        self.store: Dict[str, Any] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        self.signature = inspect.signature(llm.generate)

    def key(self, *args: Any, **kwargs: Any) -> str:
        bound = self.signature.bind(*args, **kwargs)
        bound.apply_defaults()
        return hashlib.sha256(json.dumps(bound.arguments, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        k = self.key(*args, **kwargs)
        if k in self.store:
            self.hits += 1
            return self.store[k]
        self.misses += 1
        self.store[k] = llm.generate(*args, **kwargs)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.store, ensure_ascii=False), encoding="utf-8")
        return self.store[k]


# ---------------------------------------------------------------- gold injection (pure functions, tested)
def region_end(gold: Dict[str, Any]) -> int:
    r = gold["annotation"]["layers"]["mentions"].get("region")
    return r["end"] if r else len(gold["text"])


def hybrid_mentions(gold: Dict[str, Any], predicted: List[Dict[str, Any]]):
    """Gold mentions inside the region, predicted mentions starting after it, in text order, numbered M1.. as the
    pipeline expects. Returns (mentions, {new id: gold mention id})."""
    end = region_end(gold)
    picked = [("gold", m) for m in gold["mentions"] if m["end"] <= end]
    picked += [("pred", m) for m in predicted if m["start"] >= end]
    picked.sort(key=lambda x: (x[1]["start"], -x[1]["end"]))
    out, gold_id = [], {}
    for i, (src, m) in enumerate(picked, 1):
        mid = f"M{i}"
        out.append({"mention_id": mid, "text": m["text"], "type": m["type"],
                    "mention_kind": m["mention_kind"], "start": m["start"], "end": m["end"]})
        if src == "gold":
            gold_id[mid] = m["mention_id"]
    return out, gold_id


def drop_added_in_region(doc: Dict[str, Any], gold_id: Dict[str, str], end: int) -> int:
    """Remove mentions inside the region that are not gold (coreference adds pronouns and short names)."""
    drop = {m["mention_id"] for m in doc["mentions"] if m["end"] <= end and m["mention_id"] not in gold_id}
    doc["mentions"] = [m for m in doc["mentions"] if m["mention_id"] not in drop]
    clusters = []
    for c in doc["coreference_clusters"]:
        kept = [x for x in c["mentions"] if x not in drop]
        if len(kept) >= 2:
            clusters.append({"cluster_id": f"C{len(clusters) + 1}", "mentions": kept})
    doc["coreference_clusters"] = clusters
    return len(drop)


def gold_clusters(doc: Dict[str, Any], gold_id: Dict[str, str], gold: Dict[str, Any]) -> Dict[str, int]:
    """Replace the clusters as described for run C; returns counts of how mentions after the region were linked."""
    key_of_gold = {m["mention_id"]: m["entity_key"] for m in gold["mentions"]}
    key = {mid: key_of_gold[g] for mid, g in gold_id.items()}
    groups: Dict[str, List[str]] = {}
    for mid, k in key.items():
        if k is not None:
            groups.setdefault(f"gold:{k}", []).append(mid)
    stats: Counter = Counter()
    for c in doc["coreference_clusters"]:
        outside = [x for x in c["mentions"] if x not in gold_id]
        if not outside:
            continue
        votes = Counter(key[x] for x in c["mentions"] if key.get(x) is not None).most_common()
        if votes and (len(votes) == 1 or votes[0][1] > votes[1][1]):
            groups[f"gold:{votes[0][0]}"] = groups.get(f"gold:{votes[0][0]}", []) + outside
            stats["after_region_joined_gold_entity"] += len(outside)
        else:
            groups[f"pred:{c['cluster_id']}"] = outside
            stats["after_region_kept_predicted_cluster"] += len(outside)
    order = {m["mention_id"]: i for i, m in enumerate(doc["mentions"])}
    doc["coreference_clusters"] = [{"cluster_id": f"C{i}", "mentions": sorted(g, key=order.get)}
                                   for i, g in enumerate((g for g in groups.values() if len(g) >= 2), 1)]
    return dict(stats)


# ---------------------------------------------------------------- run
def run_chapter(run: str, gold: Dict[str, Any]) -> Dict[str, Any]:
    doc = {"schema_version": GOLD_SCHEMA_VERSION, "story_id": gold["doc_id"], "text": gold["text"],
           **{k: [] for k in LISTS}}
    meta: Dict[str, Any] = {"run": run, "doc_id": gold["doc_id"], "region_end": region_end(gold)}
    timer = {}

    def stage(name: str, fn: Callable[[Dict[str, Any]], Any]) -> Any:
        t0 = time.time()
        out = fn(doc)
        timer[name] = round(time.time() - t0, 1)
        return out

    stage("release_llm", release_llm)
    gold_id: Dict[str, str] = {}
    if run == "A":
        stage("mentions", mentions)
    else:
        end = meta["region_end"]
        if end < len(gold["text"]):
            stage("mentions", mentions)                 # predicted mentions are needed after the region
        doc["mentions"], gold_id = hybrid_mentions(gold, doc["mentions"])
        meta["mentions_from_gold"], meta["mentions_predicted"] = len(gold_id), len(doc["mentions"]) - len(gold_id)
    stage("coref", coref)
    if run in ("B", "C"):
        meta["coref_added_in_region_removed"] = drop_added_in_region(doc, gold_id, meta["region_end"])
    if run == "C":
        meta["clusters"] = gold_clusters(doc, gold_id, gold)
    for name, fn in (("events", events), ("temporal", temporal), ("release_encoders", release_encoders),
                     ("llm_types", llm_types), ("relations", relations), ("release_llm", release_llm)):
        stage(name, fn)
    errors = schema_errors(doc)
    if errors:
        raise ValueError(f"{gold['doc_id']}: output violates the schema: {errors[:5]}")
    meta["seconds"] = timer
    return {"doc_id": gold["doc_id"], **doc}, meta


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run", choices=["A", "B", "C"])
    ap.add_argument("out_dir")
    ap.add_argument("--cache", required=True)
    ap.add_argument("gold", nargs="+")
    a = ap.parse_args(argv)
    cache = CachedLLM(Path(a.cache))
    relations_module.generate = events_module.generate = cache      # both stages imported generate by name
    out = Path(a.out_dir)
    metas = []
    for path in a.gold:
        gold = json.loads(Path(path).read_text(encoding="utf-8"))
        h0, m0 = cache.hits, cache.misses
        doc, meta = run_chapter(a.run, gold)
        meta.update(llm_cache_hits=cache.hits - h0, llm_cache_misses=cache.misses - m0)
        dst = out / "pred" / f"{gold['doc_id']}.json"
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        metas.append(meta)
        print(json.dumps(meta), flush=True)
    (out / "run_meta.json").write_text(json.dumps(metas, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
