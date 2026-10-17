"""
Closed-question extraction experiments. Fixed upstream inputs: run C's saved predictions (gold mentions and gold
coreference inside the mention region, the pipeline's own after it). Same model (`llm.MODEL`), the same request body
as `llm.generate` (temperature 0, num_ctx 4096), the same chapter text and the pipeline's 2,000-character chunks.
Production prompts and stages are not touched: the templates below are this experiment's own (PROMPT_VERSION).

    python -m experiments.closed EXPERIMENT OUT_DIR --upstream RUN_C_PRED_DIR

    probe            the production people template, asked about one person at a time: the template's key is the
                     person's name ({"<name>": {property: "verbatim-string", ...}}), the context is the whole chunk
    facts            one closed question per (entity, property): {"<property> of <name>": "verbatim-string"} (status
                     also asks for a status class), the context only the chunk's sentences that mention the entity
    rels-oracle      ORACLE: candidate pairs are the entity pairs of the gold relationships (never the predicate or
                     the evidence); one question per pair and window. Not production performance.
    rels-candidates  candidate pairs: every two entities mentioned in one sentence or in two adjacent sentences
                     (no gold used); same question

An entity is a run-C cluster (or an unclustered mention) whose mentions are mostly characters or organizations
(locations too, as the object of OWNS); it is asked about by its most frequent proper (else nominal) mention text,
and entities with only pronouns are skipped. A relationship window is one sentence holding a mention of both, or two
adjacent sentences holding one each (at most WINDOWS_PER_PAIR per pair, in text order).

Every answer must be copied from the context: a value or evidence not found verbatim (case- and space-insensitive) in
the context is dropped and counted (`invalid`); null, "" and "none" are `none`. Each kept claim records the sentence
it was found in, with chapter offsets. Every request goes through a cache keyed on its full body, with Ollama's token
counts and durations, so a rerun replays without the model.
"""
import argparse
import copy
import hashlib
import json
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import extractor  # noqa: F401  (puts ../backend on sys.path)
from app.contracts.gold import FACT_PROPERTIES
from app.preprocessing import chunk_document, preprocess_chapter
from extractor import llm
from extractor.relations import CHUNK_CHARS, EXAMPLE, EXAMPLES, PEOPLE, SYSTEM, entities, representative

PROMPT_VERSION = "closed-v1"
WINDOWS_PER_PAIR = 6
NONE_STRINGS = {"", "none", "null", "n/a", "na", "unknown", "not stated", "not mentioned"}
LABEL = {"birth_place": "birthplace", "date_of_birth": "date of birth", "origin": "where they come from",
         "eye_color": "eye colour", "hair_color": "hair colour", "species": "species", "age": "age",
         "occupation": "occupation", "title": "title or rank", "status": "condition (alive, dead, injured...)",
         "location": "location"}
STATUS = ["alive", "dead", "missing", "injured", "unconscious", "none"]
MARTA = {"age": "thirty", "occupation": "nurse", "hair_color": "red", "status": "recovering",
         "location": "the farmhouse"}
# Relationship options for an ordered pair (A, B): (predicate, A is the subject), with the phrase the model sees.
REL_OPTIONS: List[Tuple[str, str, bool]] = [
    ("{a} is the father of {b}", "FATHER_OF", True), ("{b} is the father of {a}", "FATHER_OF", False),
    ("{a} is the mother of {b}", "MOTHER_OF", True), ("{b} is the mother of {a}", "MOTHER_OF", False),
    ("{a} is a parent of {b}", "PARENT_OF", True), ("{b} is a parent of {a}", "PARENT_OF", False),
    ("{a} and {b} are siblings", "SIBLING_OF", True), ("{a} and {b} are married", "MARRIED_TO", True),
    ("{a} and {b} are engaged", "ENGAGED_TO", True), ("{a} and {b} are other relatives", "RELATED_TO", True),
    ("{a} and {b} are friends", "FRIEND_OF", True), ("{a} and {b} are enemies", "ENEMY_OF", True),
    ("{a} and {b} are allies", "ALLY_OF", True), ("{a} and {b} know each other", "KNOWS", True),
    ("{a} works for {b}", "WORKS_FOR", True), ("{b} works for {a}", "WORKS_FOR", False),
    ("{a} is a member of {b}", "MEMBER_OF", True), ("{b} is a member of {a}", "MEMBER_OF", False),
    ("{a} owns {b}", "OWNS", True), ("{b} owns {a}", "OWNS", False),
]
LOCATION_OK = {"OWNS"}                    # a location can only be what someone owns


# ---------------------------------------------------------------- metered, cached LLM
def _post_ipv4(path: str, body: Dict[str, Any], timeout: int) -> Dict[str, Any]:
    """`llm._post` to 127.0.0.1 instead of localhost: on this Windows machine "localhost" tries IPv6 (::1) first and
    each request then waits ~2.3 s before the IPv4 connection Ollama listens on. Same server, same request body."""
    import urllib.request
    request = urllib.request.Request(f"{llm.URL.replace('localhost', '127.0.0.1')}/{path}", json.dumps(body).encode(),
                                     {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


class MeteredLLM:
    """The request body of `llm.generate`, cached on that body, with Ollama's token counts and durations kept."""

    def __init__(self, path: Path, post: Callable[[str, Dict[str, Any], int], Dict[str, Any]] = None):
        self.path, self.post = path, post or _post_ipv4
        self.store: Dict[str, Any] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        self.hits = self.misses = 0

    @staticmethod
    def body(system: str, user: str, schema: Any, num_predict: int = 1024, model: str = None) -> Dict[str, Any]:
        return {"model": model or llm.MODEL, "stream": False, "format": schema,
                "options": {"temperature": 0, "num_ctx": llm.NUM_CTX, "num_predict": num_predict},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}

    def __call__(self, system: str, user: str, schema: Any = "json", num_predict: int = 1024) -> Dict[str, Any]:
        body = self.body(system, user, schema, num_predict)
        key = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if key in self.store:
            self.hits += 1
            return self.store[key]
        self.misses += 1
        t0 = time.time()
        reply = self.post("chat", body, 600)
        cut = reply.get("done_reason") == "length"
        entry = {"answer": None if cut else json.loads(reply["message"]["content"]), "cut_off": cut,
                 "prompt_tokens": reply.get("prompt_eval_count"), "output_tokens": reply.get("eval_count"),
                 "seconds": round(reply.get("total_duration", (time.time() - t0) * 1e9) / 1e9, 3)}
        self.store[key] = entry
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.store, ensure_ascii=False), encoding="utf-8")
        return entry


def ask(call: MeteredLLM, template: Dict[str, Any], examples: List[Tuple[str, Dict[str, Any]]], context: str):
    """NuExtract's prompt layout, as in `relations.ask`: template, worked examples, context."""
    shots = "".join(f"## Input:\n{text}\n## Output:\n{json.dumps(out, ensure_ascii=False)}\n" for text, out in examples)
    shots = f"# Examples:\n{shots}" if shots else ""
    return call(SYSTEM, f"# Template:\n{json.dumps(template, indent=4, ensure_ascii=False)}\n{shots}# Context:\n{context}",
                "json")


# ---------------------------------------------------------------- answers and evidence (pure, tested)
def answer_value(x: Any) -> Optional[str]:
    """A copied value, or None for none / null / empty / not a string."""
    if not isinstance(x, str):
        return None
    v = " ".join(x.split()).strip(" .,;:")
    return None if v.casefold() in NONE_STRINGS else v


def locate(value: str, sentences: Iterable[Any]) -> Optional[Tuple[Any, int, int]]:
    """The first sentence containing `value` (case- and whitespace-insensitive), with the value's chapter offsets."""
    pattern = r"\s+".join(map(re.escape, value.split()))
    for s in sentences:
        m = re.search(pattern, s.text, re.IGNORECASE)
        if m:
            return s, s.start + m.start(), s.start + m.end()
    return None


def rel_options(a: str, b: str, a_type: str, b_type: str) -> List[Tuple[str, str, bool]]:
    opts = []
    for phrase, predicate, a_first in REL_OPTIONS:
        if "location" in (a_type, b_type) and predicate not in LOCATION_OK:
            continue
        if predicate == "OWNS" and (b_type if a_first else a_type) != "location" and "location" in (a_type, b_type):
            continue
        opts.append((phrase.format(a=a, b=b), predicate, a_first))
    return opts


def parse_relation(answer: Dict[str, Any], key: str, options: List[Tuple[str, str, bool]]):
    """(predicate, a_is_subject) for the option the model chose, or None for none / anything not an option."""
    chosen = answer.get(key) if isinstance(answer, dict) else None
    chosen = chosen[0] if isinstance(chosen, list) and chosen else chosen
    for phrase, predicate, a_first in options:
        if isinstance(chosen, str) and chosen.strip().casefold() == phrase.casefold():
            return predicate, a_first
    return None


# ---------------------------------------------------------------- upstream entities and windows
class Chapter:
    def __init__(self, upstream: Dict[str, Any]):
        self.doc = upstream
        self.text = upstream["text"]
        document = preprocess_chapter(self.text)
        self.sentences = list(document.iter_sentences())
        self.chunks = list(chunk_document(document, max_chars=CHUNK_CHARS, overlap_sentences=0))
        self.groups = entities(upstream)
        self.group_of = {m["mention_id"]: k for k, ms in self.groups.items() for m in ms}
        self.kind = {k: Counter(m["type"] for m in ms).most_common(1)[0][0] for k, ms in self.groups.items()}
        self.name = {}
        for k, ms in self.groups.items():
            for kind in ("proper", "nominal"):
                texts = Counter(" ".join(m["text"].split()) for m in ms if m["mention_kind"] == kind)
                if texts:
                    self.name[k] = texts.most_common(1)[0][0]
                    break
        self.sent_of = {m["mention_id"]: self.sentence_index(m["start"]) for ms in self.groups.values() for m in ms}

    def sentence_index(self, pos: int) -> int:
        return next(i for i, s in enumerate(self.sentences) if s.start <= pos < s.end or pos < s.start)

    def mentioned(self, key: str) -> List[int]:
        return sorted({self.sent_of[m["mention_id"]] for m in self.groups[key]})

    def fact_entities(self) -> List[str]:
        return [k for k in self.groups if k in self.name and self.kind[k] in ("character", "organization")]

    def chunk_sentences(self, chunk: Any) -> List[Any]:
        return [s for s in self.sentences if chunk.start <= s.start < chunk.end]

    def mention_in(self, key: str, sentence: Any) -> Dict[str, Any]:
        return representative(self.groups[key], sentence)


# ---------------------------------------------------------------- experiments
def run_probe(ch: Chapter, call: MeteredLLM, log: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    facts = []
    example_out = {"Marta Lindqvist": {p: EXAMPLES["people"]["people"][0].get(p) for p in FACT_PROPERTIES}}
    for chunk in ch.chunks:
        here = [k for k in ch.fact_entities() if any(chunk.start <= m["start"] < chunk.end for m in ch.groups[k])]
        for k in here:
            name = ch.name[k]
            # the production people template's fields, keyed by this one person instead of a list of people
            person = {p: v for p, v in PEOPLE["people"][0].items() if p != "name"}
            reply = ask(call, {name: person}, [(EXAMPLE, example_out)], chunk.text)
            got = (reply["answer"] or {}).get(name) if isinstance(reply["answer"], dict) else None
            for prop in FACT_PROPERTIES:
                value = answer_value((got or {}).get(prop) if isinstance(got, dict) else None)
                facts += _keep_fact(ch, k, prop, value, ch.chunk_sentences(chunk), log, "probe")
    return facts


def run_facts(ch: Chapter, call: MeteredLLM, log: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    facts = []
    for chunk in ch.chunks:
        for k in ch.fact_entities():
            window = [ch.sentences[i] for i in ch.mentioned(k) if chunk.start <= ch.sentences[i].start < chunk.end]
            if not window:
                continue
            context, name = "\n".join(s.text for s in window), ch.name[k]
            for prop in FACT_PROPERTIES:
                key, ex_key = f"{LABEL[prop]} of {name}", f"{LABEL[prop]} of Marta Lindqvist"
                if prop == "status":
                    template = {key: "verbatim-string", "status class": STATUS}
                    example = {ex_key: MARTA["status"], "status class": "injured"}
                else:
                    template, example = {key: "verbatim-string"}, {ex_key: MARTA.get(prop)}
                reply = ask(call, template, [(EXAMPLE, example)], context)
                answer = reply["answer"] if isinstance(reply["answer"], dict) else {}
                value = answer_value(answer.get(key))
                kept = _keep_fact(ch, k, prop, value, window, log, "facts")
                if kept and prop == "status":
                    cls = answer.get("status class")
                    cls = cls[0] if isinstance(cls, list) and cls else cls
                    if isinstance(cls, str) and cls.casefold() in STATUS[:-1]:
                        kept[0]["status_value"] = cls.upper()
                facts += kept
    return facts


def _keep_fact(ch: Chapter, k: str, prop: str, value: Optional[str], window: List[Any], log, exp) -> List[Dict]:
    entry = {"experiment": exp, "entity": k, "name": ch.name[k], "property": prop, "value": value}
    if value is None:
        entry["result"] = "none"
        log.append(entry)
        return []
    hit = locate(value, window)
    if hit is None:
        entry["result"] = "invalid"                 # not copied from the context
        log.append(entry)
        return []
    sentence, s, e = hit
    entry.update(result="kept", value=ch.text[s:e], evidence={"start": sentence.start, "end": sentence.end},
                 value_span={"start": s, "end": e}, evidence_text=sentence.text)
    log.append(entry)
    return [{"property": prop, "value": ch.text[s:e], "entity_mention_id": ch.mention_in(k, sentence)["mention_id"],
             "evidence": entry["evidence"], "group": k}]


def pair_windows(ch: Chapter, a: str, b: str) -> List[List[int]]:
    sa, sb = set(ch.mentioned(a)), set(ch.mentioned(b))
    windows = [[i] for i in sorted(sa & sb)]
    windows += [[i, i + 1] for i in range(len(ch.sentences) - 1)
                if ((i in sa and i + 1 in sb) or (i in sb and i + 1 in sa)) and not ({i, i + 1} & (sa & sb))]
    return sorted(windows)[:WINDOWS_PER_PAIR]


def run_rels(ch: Chapter, call: MeteredLLM, pairs: Iterable[Tuple[str, str]], log, exp) -> List[Dict[str, Any]]:
    rels = []
    example = {"How are Tomas and Marta Lindqvist related?": "Tomas and Marta Lindqvist are siblings",
               "evidence": EXAMPLE[:EXAMPLE.index(".") + 1]}
    for a, b in pairs:
        opts = rel_options(ch.name[a], ch.name[b], ch.kind[a], ch.kind[b])
        key = f"How are {ch.name[a]} and {ch.name[b]} related?"
        template = {key: [p for p, _, _ in opts] + ["none"], "evidence": "verbatim-string"}
        for w in pair_windows(ch, a, b):
            window = [ch.sentences[i] for i in w]
            reply = ask(call, template, [(EXAMPLE, example)], "\n".join(s.text for s in window))
            answer = reply["answer"] if isinstance(reply["answer"], dict) else {}
            choice = parse_relation(answer, key, opts)
            entry = {"experiment": exp, "pair": [a, b], "names": [ch.name[a], ch.name[b]], "window": w,
                     "choice": answer.get(key)}
            if choice is None:
                entry["result"] = "none"
                log.append(entry)
                continue
            evidence = answer_value(answer.get("evidence"))
            hit = locate(evidence, window) if evidence else None
            if hit is None:
                entry["result"] = "invalid"            # a relation without evidence copied from the window
                log.append(entry)
                continue
            sentence, s, e = hit
            predicate, a_first = choice
            subj, obj = (a, b) if a_first else (b, a)
            entry.update(result="kept", predicate=predicate, subject=subj, object=obj,
                         evidence={"start": s, "end": e}, evidence_text=ch.text[s:e])
            log.append(entry)
            rels.append({"predicate": predicate, "subject_mention_id": ch.mention_in(subj, sentence)["mention_id"],
                         "object_mention_id": ch.mention_in(obj, sentence)["mention_id"], "evidence": entry["evidence"]})
    return rels


def candidate_pairs(ch: Chapter) -> List[Tuple[str, str]]:
    ok = [k for k in ch.groups if k in ch.name and ch.kind[k] in ("character", "organization", "location")]
    pairs = []
    for i, a in enumerate(ok):
        for b in ok[i + 1:]:
            if "location" in (ch.kind[a], ch.kind[b]) and ch.kind[a] == ch.kind[b]:
                continue
            if pair_windows(ch, a, b):
                pairs.append((a, b))
    return pairs


def oracle_pairs(ch: Chapter, gold: Dict[str, Any], resolve: Callable[[str], Optional[str]]) -> List[Tuple[str, str]]:
    """ORACLE: the groups whose mentions resolve to the two entities of a gold relationship (most mentions wins)."""
    votes: Dict[str, Counter] = {}
    for k, ms in ch.groups.items():
        for m in ms:
            key = resolve(m["mention_id"])
            if key:
                votes.setdefault(key, Counter())[k] += 1
    best = {key: c.most_common(1)[0][0] for key, c in votes.items()}
    pairs = []
    for r in gold["relationships"]:
        a, b = best.get(r["subject_entity_key"]), best.get(r["object_entity_key"])
        if a and b and a != b and a in ch.name and b in ch.name and (a, b) not in pairs and (b, a) not in pairs:
            pairs.append((a, b))
    return pairs


def main(argv: Optional[List[str]] = None) -> int:
    import extractor as _  # noqa: F401
    from app.evaluation.score_v2 import REVIEWED, _Gold, _Resolver
    ap = argparse.ArgumentParser()
    ap.add_argument("experiment", choices=["probe", "facts", "rels-oracle", "rels-candidates"])
    ap.add_argument("out_dir")
    ap.add_argument("--upstream", required=True)
    a = ap.parse_args(argv)
    out = Path(a.out_dir)
    call = MeteredLLM(out / "llm_cache.json")
    gold_dir = Path(__file__).resolve().parents[2] / "gold" / "v2"
    meta, log = [], []
    for path in sorted(gold_dir.rglob("ch*.json")):
        gold = json.loads(path.read_text(encoding="utf-8"))
        if gold["annotation"]["status"] not in REVIEWED:
            continue
        upstream = json.loads((Path(a.upstream) / f"{gold['doc_id']}.json").read_text(encoding="utf-8"))
        ch = Chapter(upstream)
        h0, m0, n0 = call.hits, call.misses, len(log)
        pred = copy.deepcopy(upstream)
        pred["facts"], pred["relationships"] = [], []
        if a.experiment == "probe":
            pred["facts"] = run_probe(ch, call, log)
        elif a.experiment == "facts":
            pred["facts"] = run_facts(ch, call, log)
        else:
            resolver = _Resolver(upstream, _Gold(gold, include_pending=False))
            pairs = (oracle_pairs(ch, gold, lambda mid: resolver(mid)[0]) if a.experiment == "rels-oracle"
                     else candidate_pairs(ch))
            pred["relationships"] = run_rels(ch, call, pairs, log, a.experiment)
        for i, f in enumerate(pred["facts"], 1):
            f["fact_id"] = f"F{i}"
        for i, r in enumerate(pred["relationships"], 1):
            r["relationship_id"] = f"R{i}"
        for entry in log[n0:]:
            entry["doc_id"] = gold["doc_id"]
        dst = out / "pred" / f"{gold['doc_id']}.json"
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(json.dumps(pred, ensure_ascii=False, indent=1), encoding="utf-8")
        mine = log[n0:]
        meta.append({"doc_id": gold["doc_id"], "questions": call.hits + call.misses - h0 - m0,
                     "cache_hits": call.hits - h0, "cache_misses": call.misses - m0,
                     "answers": dict(Counter(e["result"] for e in mine))})
        print(json.dumps(meta[-1]), flush=True)
    entries = list(call.store.values())
    cost = {"requests": len(entries), "prompt_tokens": sum(e["prompt_tokens"] or 0 for e in entries),
            "output_tokens": sum(e["output_tokens"] or 0 for e in entries),
            "model_seconds": round(sum(e["seconds"] or 0 for e in entries), 1),
            "cut_off": sum(bool(e["cut_off"]) for e in entries)}
    (out / "answers.json").write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "run_meta.json").write_text(json.dumps({"experiment": a.experiment, "prompt_version": PROMPT_VERSION,
                                                   "model": llm.MODEL, "upstream": a.upstream, "chapters": meta,
                                                   "cost_all_cached_requests": cost}, indent=1), encoding="utf-8")
    print(json.dumps(cost))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
