# Closed questions with Qwen3.5 9B (2026-10-18)

Follow-up to `docs/closed_questions_2026-10-17.md`. That experiment found that NuExtract finds more claims when
asked closed questions, but rarely answers "none". This one changes only the model and the wording that turns the
same task into instructions. The two models get the same questions, evidence windows, candidate pairs, upstream
input (run C's gold mentions and coreference) and scorer. NuExtract's answers come from its saved cache, not a rerun.
Production code, prompts and gold were not modified.

## Result

Qwen3.5 does answer "none": 82% of relationship questions and 90% of fact questions, against NuExtract's 23% and
86%. With the oracle entity pairs it keeps NuExtract's recall and cuts its wrong answers from 30 to 8.

On realistic inputs it doesn't yet beat production on F1:
- **Relationships:** F1 0.204, against production's 0.207 strict and 0.379 lenient.
- **Facts:** F1 0.18, against production's 0.25.

One post-hoc, gold-free restriction helps a lot: asking only about pairs of named entities. With it, relationships
reach precision 0.31 and F1 0.368 strict, against production's 0.22 and 0.207. That's why the recommendation is to
test Qwen's closed questions in the pipeline for **relationships only**, on named-entity pairs, scored on chapters
the restriction was not chosen on. Not for facts.

## What changed between the two models

- **Model:** `nuextract2-4b` → `qwen3.5:9b`, requested with `"think": false` (otherwise Qwen reasons first). The
  other settings stay the same: temperature 0, `num_ctx` 4096, `num_predict` 1024, the request body of
  `llm.generate`.
- **Prompt:** NuExtract's template-and-context layout becomes `InstructDialect` (prompt version
  `closed-instruct-v1`, in `extractor/experiments/closed.py`):
  - **System prompt:** "Use only what the passage explicitly states. If the passage does not explicitly state the
    answer, answer "none". Do not guess, and do not infer anything from two people simply being mentioned
    together."
  - **Facts:** "What does the passage explicitly state as the <property> of <name>? Copy the exact words from the
    passage. If the passage does not state it about <name>, answer "none"." The status question also asks for a
    class (alive, dead, missing, injured, unconscious or none).
  - **Relationships:** "Which of these relationships between A and B does the passage explicitly state?", followed by
    the same 20 directed phrasings plus "none". The model chooses "none" unless the passage itself states the
    relationship, and copies the words that state it as evidence.
  - **Worked example:** the same one as before (Marta Lindqvist). The answers are constrained by a JSON schema; for
    relationships the schema allows only the offered options or "none".
  - **No gold values, predicates or evidence appear in any prompt.** The oracle condition supplies gold entity pairs
    and is labelled as such.
- **Validation, unchanged:** a value or evidence quote must be found verbatim in the context, or it is dropped as
  `invalid`.

## Relationships: oracle pairs (gold pairs supplied; NOT production performance)

| Run | tp / fp / fn | P | R | F1 strict | F1 lenient |
| --- | --- | --- | --- | --- | --- |
| A0, production | 6 / 21 / 25 | 0.22 | 0.19 | 0.207 | 0.379 |
| NuExtract, closed questions | 16 / 30 / 15 | 0.35 | 0.52 | 0.416 | 0.466 |
| **Qwen3.5, closed questions** | 16 / **8** / 15 | **0.67** | 0.52 | **0.582** | 0.582 |

Errors: NuExtract had 26 wrong predicates; Qwen has 8. Neither has wrong-endpoint or unresolved-endpoint errors,
because the pairs are given.

## Relationships: realistic candidate pairs (no gold)

| Run | tp / fp / fn | P | R | F1 strict | F1 lenient |
| --- | --- | --- | --- | --- | --- |
| A0, production | 6 / 21 / 25 | 0.22 | 0.19 | 0.207 | 0.379 |
| NuExtract, closed questions | 12 / 373 / 19 | 0.03 | 0.39 | 0.058 | 0.068 |
| Qwen3.5, closed questions | 16 / 110 / 15 | 0.13 | 0.52 | 0.204 | 0.204 |
| NuExtract, named-entity pairs only (offline) | 9 / 130 / 22 | 0.06 | 0.29 | 0.106 | 0.108 |
| **Qwen3.5, named-entity pairs only (offline)** | **14 / 31 / 17** | **0.31** | 0.45 | **0.368** | 0.368 |
| Qwen3.5, named pairs and production cue words (offline) | 10 / 16 / 21 | 0.38 | 0.32 | 0.351 | 0.351 |

"Named-entity pairs only" keeps a question only when both entities have a proper-name mention. It uses no gold, but
it was chosen after seeing these results, so it must be confirmed on other chapters.

| Run | Answers kept / none / invalid | Wrong predicate | Wrong endpoint | Unresolved endpoint | Unsupported |
| --- | --- | --- | --- | --- | --- |
| NuExtract | 450 / 156 / 79 | 30 | 61 | 186 | 93 |
| Qwen3.5 | 134 / 424 / 127 | 7 | 22 | 64 | 17 |

Per chapter (strict tp / fp / fn):

| Run | Pride and Prejudice | Oliver Twist | The Invisible Man | Styles |
| --- | --- | --- | --- | --- |
| A0 | 1/4/2 | 0/0/1 | 0/2/4 | 5/15/18 |
| NuExtract | 2/70/1 | 0/36/1 | 1/34/3 | 9/233/14 |
| Qwen3.5 | 1/19/2 | 0/10/1 | 1/11/3 | 14/70/9 |

**Found by Qwen on candidate pairs**, with the evidence it copied:
- Millie WORKS_FOR Mrs. Hall ("Millie, her lymphatic maid")
- Mr. Cavendish OWNS Styles Court ("Styles Court, had been purchased by Mr. Cavendish")
- Mr. Cavendish FATHER_OF John ("…who had married John's father…")
- Lord Abbotsbury FATHER_OF Lady Tadminster ("…the late Lord Abbotsbury's daughter")
- Alfred RELATED_TO Evelyn ("…a second cousin or something of Evie's")
- Mary FRIEND_OF Dr. Bauerstein ("…a great friend of Mary's")
- Hastings WORKS_FOR Lloyd's

**Its errors:**
- **Unresolved endpoints**, an entity the gold leaves null: "Agnes MOTHER_OF 'thirteen children of her own'", a
  rascally solicitor MARRIED_TO.
- **Wrong endpoint:** the surgeon WORKS_FOR Oliver; the gold says the parish ("a parish surgeon who did such matters
  by contract").
- **Supported by the text but not in the gold:** Emily ENGAGED_TO Alfred ("she suddenly announced that she and
  Alfred were engaged!"); the gold records MARRIED_TO.
- **Unsupported:** Cynthia MEMBER_OF the Cavendish family ("Cynthia has been with us nearly two years now").

## Facts (28 gold)

| Run | Raw recall | tp / fp / fn | P | R | F1 |
| --- | --- | --- | --- | --- | --- |
| A0, production | 8/28 | 5 / 7 / 23 | 0.42 | 0.18 | 0.250 |
| NuExtract, closed questions | 16/28 | 12 / 257 / 16 | 0.04 | 0.43 | 0.081 |
| Qwen3.5, closed questions | **20/28** | **16** / 134 / 12 | 0.11 | **0.57** | 0.180 |

| | NuExtract | Qwen3.5 |
| --- | --- | --- |
| Exact value agreement (of raw hits) | 10/16 | 13/20 |
| Evidence valid (of non-none answers) | 280/291 | 167/208 |
| Evidence overlaps gold (true positives) | 11/12 | 12/16 |

Qwen paraphrases more often, so more of its answers fail the verbatim check and are dropped as invalid.

Per chapter (tp / fp / fn):

| Run | Pride and Prejudice | Oliver Twist | The Invisible Man | Styles |
| --- | --- | --- | --- | --- |
| A0 | 0/0/3 | 0/2/5 | 0/0/4 | 5/5/11 |
| NuExtract | 0/41/3 | 3/39/2 | 1/33/3 | 8/144/8 |
| Qwen3.5 | 1/14/2 | 2/30/3 | 3/14/1 | 10/76/6 |

| Property | Gold | NuExtract correct / predicted | Qwen3.5 correct / predicted |
| --- | --- | --- | --- |
| status | 4 | 3 / 27 | 4 / 49 |
| location | 3 | 2 / 75 | 0 / 38 |
| title | 3 | 0 / 32 | 2 / 22 |
| occupation | 10 | 4 / 47 | **6 / 16** |
| origin | 1 | 0 / 31 | 0 / 8 |
| species | 0 | 0 / 19 | 0 / 6 |
| hair_color | 2 | 1 / 3 | 2 / 4 |
| age | 3 | 2 / 24 | **2 / 3** |
| birth_place | 1 | 0 / 7 | 0 / 2 |
| eye_color | 1 | 0 / 4 | 0 / 2 |

**Recovered by Qwen and missed by NuExtract:**
- the surgeon's occupation "surgeon"
- Millie "maid" ("Millie, her lymphatic maid")
- John Cavendish age "forty-five"
- Dr. Bauerstein "specialist"
- Griffin's black hair
- Lady Lucas and Lady Tadminster title "Lady"
- Lord Abbotsbury status "late"

**False positives:** status "more dead than alive" (Griffin), "delicate" (Lawrence); location "the house" (John),
"Tadminster" (the hospital); title "V.A.D" (Cynthia); occupation "Dr" (Bauerstein).

## Cost (RTX 3050 6 GB; Qwen3.5 partly on CPU)

| Run | NuExtract requests / model s | Qwen3.5 requests / model s / wall s |
| --- | --- | --- |
| rels-oracle | 90 / 98 | 90 / 238 / 240 |
| rels-candidates | 685 / 658 | 685 / 1,571 / 1,581 |
| facts | 2,057 / 977 | 2,057 / 2,529 / 2,559 |

Qwen3.5 averages about 2.3 s per question here and NuExtract about 0.7 s. Named-entity pairs need 300 relationship
questions for the four chapters, against 685.

## Recommendation

**Test Qwen3.5 closed questions in the pipeline for relationships, on named-entity candidate pairs. Do not use them
for facts yet.**
- **Why relationships:** precision and F1 support it. Named-entity pairs gave F1 0.368 strict, against production's
  0.207, at precision 0.31 against 0.22, with no gold in the loop. Qwen also uses FATHER_OF and MOTHER_OF correctly,
  which production's vocabulary cannot.
- **What the pipeline test must check:**
  - That the gain holds on chapters the named-pair restriction was not chosen on. The next reviewed chapters are the
    natural test set.
  - Whether production's rule-based relationships, which supply most of its correct ones, add recall on top.
  - That 300 questions at about 2.3 s each is acceptable.
- **Why not facts:** Qwen raises recall (16/28) and precision (0.04 → 0.11), but F1 0.18 is still below
  production's 0.25. Status, location and title produce most of the false positives. Occupation (6/16) and age (2/3)
  look usable, but that is post-hoc on a small sample.
- **Stop the approach?** No: Qwen's abstention fixes most of what made NuExtract unusable.
- **A second model?** Only if the relationship pipeline test fails, or as the next step for facts.

## Limitations

- **The sample is small:** 28 facts and 31 relationships, so one claim moves F1 by about 0.03. Styles holds most of
  both, and its gold was accepted in bulk.
- **The named-pair restriction and the per-property observations are post hoc.**
- **Model placement:** Qwen3.5 ran partly on the CPU; a larger GPU would be faster but should give the same answers.
- **Not tested:** Llama 3.1 8B (tried earlier and ruled out).
- **Gold coverage:** the gold may miss some text-supported claims (Emily ENGAGED_TO Alfred), which would count
  against both models.
- **C: is still nearly full:** free space dropped from 346 MB to 238 MB during the run. This harness writes only to
  D:, so the cause is elsewhere on the machine.

## Reproduce

```
. D:\orion_env\activate.ps1
ollama pull qwen3.5:9b            # into D:\OllamaModels (OLLAMA_MODELS)
cd extractor
python -m experiments.closed rels-oracle     ../runs/2026-10-17_closed_qwen35_9b/rels-oracle     --upstream ../runs/2026-10-17_oracle_v2/C/pred --model qwen3.5:9b --dialect instruct --no-think
python -m experiments.closed rels-candidates ../runs/2026-10-17_closed_qwen35_9b/rels-candidates --upstream ../runs/2026-10-17_oracle_v2/C/pred --model qwen3.5:9b --dialect instruct --no-think
python -m experiments.closed facts           ../runs/2026-10-17_closed_qwen35_9b/facts           --upstream ../runs/2026-10-17_oracle_v2/C/pred --model qwen3.5:9b --dialect instruct --no-think
for e in rels-oracle rels-candidates facts; python -m experiments.analyze ../runs/2026-10-17_closed_qwen35_9b/$e/pred ../runs/2026-10-17_closed_qwen35_9b/$e/analysis
python -m experiments.closed_report ../runs/2026-10-17_closed_qwen35_9b ../runs/2026-10-17_oracle_v2 ../runs/2026-10-17_closed_qwen35_9b/report.json
python -m experiments.closed_compare ../runs/2026-10-17_oracle_v2 ../runs/2026-10-17_closed_qwen35_9b/comparison.md NuExtract=../runs/2026-10-17_closed_v1 Qwen3.5-9B=../runs/2026-10-17_closed_qwen35_9b
```

Every answer is cached, so a rerun replays without the model.

Tests:
- `cd extractor && python -m pytest tests -q`: 46 passed. That includes the instruct dialect's request body,
  `none` handling, option enums, unparseable replies, and that NuExtract's requests are unchanged, so its cache
  still replays. A full replay of rels-oracle reproduced all 90 NuExtract answers.
- `cd backend && PYTHONPATH=. pytest app/tests/ -q`: 283 passed.
