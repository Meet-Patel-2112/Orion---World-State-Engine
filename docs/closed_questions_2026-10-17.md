# Closed-question extraction with NuExtract (2026-10-17)

Follow-up to `docs/oracle_experiments_2026-10-17.md`. Run C's gold mentions and coreference are the fixed upstream
input. The model, request settings, chapter text and scorer are unchanged. Production prompts, stages and gold were
not modified.

## Result

Asking NuExtract closed questions raises recall a lot, but precision collapses. Recall rises from 8 to 16 of 28 raw
facts, and, given the right pairs, from 6 to 16 of 31 relationships. NuExtract recognizes facts and relationships
when they are there, but it rarely answers `none` when they are not.
- **Targeted fact questions:** 12 facts found and 257 false positives (F1 0.08), against production's 5 found and 7
  false positives (F1 0.25).
- **Realistic relationship questions:** 12 found and 373 false positives (F1 0.06), against production's 6 and 21
  (F1 0.21).

No deterministic filter tried brings precision above about 10%. **Recommendation:** keep the closed-question framing
and test another model that can abstain, on the same questions, before any further prompt work.

## Experiments

| Run | What is asked | Context | Questions |
| --- | --- | --- | --- |
| probe | The production people template's fields, keyed by one person's name | The whole 2,000-character chunk (the production context) | 185 |
| facts | One property of one entity: `{"<property> of <name>": "verbatim-string"}`; status also asks for a class | Only the chunk's sentences that mention the entity | 2,057 |
| rels-oracle (**oracle**) | "How are A and B related?": a choice of 20 directed phrasings of the v2 predicates, or "none", plus an evidence quote | One sentence with both, or two adjacent sentences, up to 6 per pair | 90 |
| rels-candidates | The same question | The same windows | 685 |

- **Entities** are run-C clusters, named by their most frequent proper mention text.
- **rels-oracle pairs** are the entity pairs of the gold relationships, with no predicate or evidence given. This is a
  ceiling for the question, **not production performance**.
- **rels-candidates pairs** are every two named entities mentioned in one sentence or two adjacent sentences. No gold
  is used.
- **Every value and every evidence quote must be copied from the context.** One that isn't is dropped and counted
  `invalid`; null, "" and "none" count as `none`. Each kept claim records its sentence and offsets.

## Facts (28 gold)

| Run | Raw recall | Scored tp / fp / fn | P | R | F1 |
| --- | --- | --- | --- | --- | --- |
| A0, production | 8/28 | 5 / 7 / 23 | 0.42 | 0.18 | 0.25 |
| C, gold upstream, production LLM | 8/28 | 5 / 7 / 23 | 0.42 | 0.18 | 0.25 |
| probe | 9/28 | 5 / 35 / 23 | 0.13 | 0.18 | 0.15 |
| facts | **16/28** | **12** / 257 / 16 | 0.04 | **0.43** | 0.08 |

Raw recall means an answer for the right entity whose value contains, or is contained in, the gold value. It uses
the same definition as the 8/28 in the oracle report.

Value and evidence quality for the targeted fact questions:
- **Exact value agreement:** 10 of the 16 raw hits. The other six are near misses, such as "medical gentleman" for
  "surgeon" or "jest cut his arm with a scythe" for INJURED.
- **Evidence validity:** 280 of 291 non-none answers were copied from the context.
- **Evidence overlap:** the evidence sentence overlaps the gold evidence for 11 of the 12 true positives.

For the probe: exact value agreement 5/9, evidence validity 44/44, evidence overlap 4/5.

| Chapter | A0 tp/fp/fn | probe | facts | Raw recall: probe / facts |
| --- | --- | --- | --- | --- |
| Pride and Prejudice | 0/0/3 | 1/1/2 | 0/41/3 | 1/3, 1/3 |
| Oliver Twist | 0/2/5 | 1/7/4 | 3/39/2 | 1/5, 5/5 |
| The Invisible Man | 0/0/4 | 0/2/4 | 1/33/3 | 1/4, 2/4 |
| Styles | 5/5/11 | 3/25/13 | 8/144/8 | 6/16, 8/16 |

**Recovered, missed by production** (value, then the evidence sentence):
- `old_sally` occupation "nurse": "…interposed the nurse, hastily depositing in her pocket a green glass bottle…"
- `agnes_fleming` status "died": "She imprinted her cold white lips passionately on its forehead; … fell back—and
  died."
- `agnes_fleming` location "the street": "She was found lying in the street."
- `emily_inglethorp` age "seventy": "She certainly could not be a day less than seventy now."
- `john_cavendish` occupation "country squire"; `lawrence_cavendish` "doctor"; `alfred_inglethorp` "secretary";
  `arthur_hastings` status "wounded" ("here's our wounded hero!"); `cynthia_murdoch` hair "auburn".

**False positives.** NuExtract gives the asked-about person a value of the right kind from anywhere in the window:
- `arthur_hastings` hair "auburn": "…I admired the great loose waves of her auburn hair". The window includes "I",
  so the question was about Hastings; the hair is Cynthia's.
- `mr_bennet` age "three and twenty": from Mrs. Bennet's talk of daughters.
- `lloyds` location "before the war": "No, before the war I was in Lloyd's."
- `john_cavendish` origin "Styles": "I had often stayed at Styles, his mother's place."
- Lady Tadminster origin "the late Lord Abbotsbury's daughter".

| Property | Predicted | Correct | Gold | Precision |
| --- | --- | --- | --- | --- |
| location | 75 | 2 | 3 | 0.03 |
| occupation | 47 | 4 | 10 | 0.09 |
| title | 32 | 0 | 3 | 0.00 |
| origin | 31 | 0 | 1 | 0.00 |
| status | 27 | 3 | 4 | 0.11 |
| age | 24 | 2 | 3 | 0.08 |
| species | 19 | 0 | 0 | 0.00 |
| birth_place | 7 | 0 | 1 | 0.00 |
| eye_color | 4 | 0 | 1 | 0.00 |
| hair_color | 3 | 1 | 2 | 0.33 |

## Relationships (31 gold)

Counts are strict tp / fp / fn; parentage-lenient counts are in brackets.

| Run | Strict | Strict F1 | Lenient | Lenient F1 |
| --- | --- | --- | --- | --- |
| A0, production | 6 / 21 / 25 | 0.21 | (11 / 16 / 20) | 0.38 |
| C, gold upstream (diagnostic resolver) | 7 / 20 / 24 | 0.24 | (12 / 15 / 19) | 0.41 |
| **rels-oracle (ORACLE pairs)** | **16 / 30 / 15** | 0.42 | (17 / 25 / 14) | 0.47 |
| rels-candidates | 12 / 373 / 19 | 0.06 | (14 / 367 / 17) | 0.07 |
| rels-candidates, production cue filter (offline) | 8 / 138 / 23 | 0.09 | (9 / 136 / 22) | 0.10 |
| rels-candidates, named entities only (offline) | 9 / 130 / 22 | 0.11 | (9 / 127 / 22) | 0.11 |

| Chapter | A0 | rels-oracle | rels-candidates |
| --- | --- | --- | --- |
| Pride and Prejudice | 1/4/2 | 2/4/1 | 2/70/1 |
| Oliver Twist | 0/0/1 | 0/1/1 | 0/36/1 |
| The Invisible Man | 0/2/4 | 2/5/2 | 1/34/3 |
| Styles | 5/15/18 | 12/20/11 | 9/233/14 |

Evidence validity: oracle 64 of 69 relation answers, candidates 450 of 529.

The candidate run's 373 false positives break down as:
- 186 unresolved: an endpoint is an entity the gold leaves null, such as "A gentleman" or "his coachman".
- 93 between real entities but not in the gold.
- 61 wrong endpoint.
- 30 wrong predicate.

By predicate: OWNS 91, RELATED_TO 63, PARENT_OF 56, MOTHER_OF 49, MARRIED_TO 32.

**Recovered with oracle pairs, missed by production:**
- `mr_cavendish` OWNS `styles_court`: "Their country-place, Styles Court, had been purchased by Mr. Cavendish…"
- `alfred_inglethorp` WORKS_FOR `emily_inglethorp`: "…took him on as secretary…"
- `cynthia_murdoch` WORKS_FOR `red_cross_hospital`: "She works in the Red Cross Hospital at Tadminster…"
- `alfred_inglethorp` RELATED_TO `evelyn_howard`: "…a second cousin or something of Evie's…"
- `mrs_halls_sister` MOTHER_OF `tom`: "There was my sister's son, Tom…"
- `lord_abbotsbury` FATHER_OF `lady_tadminster`: "…she was the late Lord Abbotsbury's daughter…". Strict here, where production
  only matched leniently.

**Wrong answers.** Each pair is asked once per window, and other windows produce other relations:
- Oracle pairs:
  - `the_surgeon` PARENT_OF `the_parish`
  - `mrs_hall` MOTHER_OF `tom`; she is his aunt
  - `mr_cavendish` FATHER_OF `emily_inglethorp`; she is his wife
  - `millie` RELATED_TO `mrs_hall`; Millie is her maid
- Candidate pairs:
  - John OWNS the smoking-room ("John beckoned us both into the smoking-room")
  - Oliver PARENT_OF the surgeon
  - Lady Tadminster MOTHER_OF Lord Abbotsbury

## Cost (NuExtract 2.0 4B, RTX 3050)

| Run | Requests | Prompt tokens | Output tokens | Model seconds |
| --- | --- | --- | --- | --- |
| probe | 185 | 138,974 | 12,332 | 264 |
| facts | 2,057 | 503,921 | 25,046 | 977 |
| rels-oracle | 90 | 41,214 | 5,116 | 98 |
| rels-candidates | 685 | 288,269 | 39,089 | 658 |

Production asks 50 questions for the four chapters. On this machine `localhost` added about 2.3 s per request
(Windows tries IPv6 `::1` first; Ollama listens on IPv4). The harness was switched to `127.0.0.1` partway through;
the request body is unchanged. Production's `llm.URL` has the same delay, about 2 minutes per baseline run, and
switching it to `127.0.0.1` is a separate one-line fix.

## Recommendation

**Keep the closed-question framing and test another model on the same questions.**
- **Why closed questions:** they double raw fact recall (8 → 16/28). With the right pairs, NuExtract recognizes 16 of
  31 relationships, against 6–7.
- **Why not this model:** the gap is abstention, not recognition. NuExtract fills a value whenever the context has
  something of the right kind, and picks a relation for almost any pair.
  - Facts: 4% precision.
  - Relationships: 3% precision, and no more than about 6% after cue-word or named-entity filtering.
- **Why not prompt tuning first:** NuExtract takes a template and examples, not instructions. Even with oracle pairs,
  26 of its 46 answers were wrong predicates. A prompt change is cheap, but unlikely to close a tenfold precision
  gap.
- **Which model:** an instruction-following model that can answer "none". `llama3.1:8b-instruct-q4_K_M` is already
  installed on this machine (4.9 GB, fits the 6 GB GPU on its own).
  - The harness, questions, windows, caching and scoring stay as they are; only the model and the prompt wording
    change.
  - Order: rels-oracle and rels-candidates first (775 questions), then the facts questions.
  - It is worth pursuing only if precision rises well above production's (0.42 facts, 0.22 relationships) while
    recall holds.

**Not shown:** that another model will do better, or that per-pair aggregation (one answer per pair) would be
enough. Both are the next measurements.

## Limitations

- **The sample is small:** 28 facts and 31 relationships. Styles carries most of both, and its gold was accepted in
  bulk.
- **Answer matching:** raw recall uses substring containment, so "about forty" and "forty" both count, and exact
  agreement is reported separately.
- **Single pass:** a single answer per question at temperature 0; there is no sampling variance to report.
- **The window rule:** up to 6 windows per pair, in text order. It shapes both the false-positive count and the
  candidate run's cost.
- **Offline filters:** the cue-word and named-entity filters were applied after the run. They are diagnostics, not
  tuned.

## Reproduce

```
. D:\orion_env\activate.ps1
cd extractor
python -m experiments.closed probe           ../runs/2026-10-17_closed_v1/probe           --upstream ../runs/2026-10-17_oracle_v2/C/pred
python -m experiments.closed facts           ../runs/2026-10-17_closed_v1/facts           --upstream ../runs/2026-10-17_oracle_v2/C/pred
python -m experiments.closed rels-oracle     ../runs/2026-10-17_closed_v1/rels-oracle     --upstream ../runs/2026-10-17_oracle_v2/C/pred
python -m experiments.closed rels-candidates ../runs/2026-10-17_closed_v1/rels-candidates --upstream ../runs/2026-10-17_oracle_v2/C/pred
for e in probe facts rels-oracle rels-candidates; python -m experiments.analyze ../runs/2026-10-17_closed_v1/$e/pred ../runs/2026-10-17_closed_v1/$e/analysis
python -m experiments.closed_report ../runs/2026-10-17_closed_v1 ../runs/2026-10-17_oracle_v2 ../runs/2026-10-17_closed_v1/report.json
```

Every model answer is cached, so a rerun replays without the model.

Tests:
- `cd extractor && python -m pytest tests -q`: 42 passed, including 7 in `tests/test_closed.py` for caching, cost
  recording, cut-off replies, `none` handling, evidence offsets, invalid values and relation direction.
- `cd backend && PYTHONPATH=. pytest app/tests/ -q`: 283 passed.
