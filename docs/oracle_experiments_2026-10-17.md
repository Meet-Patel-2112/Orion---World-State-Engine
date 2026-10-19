# Oracle experiments on the first gold v2 baseline (2026-10-17)

Where do the extractor's facts and relationships get lost? Gold annotations were swapped in for the mention and
coreference stages, one at a time, with everything else held fixed, on the four reviewed chapter-1 files (947
mentions, 28 facts, 31 relationships). Gold annotations were not modified, pending items were not scored, and
production code and prompts were not changed.

## Result in one paragraph

With NuExtract's answers held identical across runs, gold mentions and gold coreference change fact recall by 0 and
relationship recall by +1 (diagnostic resolver; −4 under the official scorer, for a reason explained below). The
measured bottleneck is the LLM step's recall. NuExtract's raw answers, before any filtering, contain 8 of the 28 gold
facts and 3 of the 31 gold relationships. Of the 6 relationships found, 3 come from the possessive-role rules, not
the LLM. The next smallest test is an LLM-stage-only experiment on gold mentions and coreference that replaces the
two open templates with closed questions over candidates. That test has not been run yet.

## Runs

| Run | Mentions | Coreference | LLM (NuExtract) | What reran |
| --- | --- | --- | --- | --- |
| A0 | GLiNER2 | BookNLP + link + merge | live | the frozen baseline (`predict-v2`), not rerun |
| A | GLiNER2 | BookNLP + link + merge | live, answers cached | every stage, through the harness |
| B | gold inside the mention region | predicted, then non-gold mentions it adds inside the region removed | cache replay (50/50 hits) | every stage except the mention stage inside the region |
| C | as B | gold entity keys inside the region; a later mention joins the gold entity its predicted cluster votes for | cache replay (50/50 hits) | every stage except mentions and coreference inside the region |
| M | A0's predictions with predicates mapped to v2 | | | nothing: a rewrite of A0's files |

- **A reproduces A0 exactly** (identical mentions, clusters, facts and relationships in all four chapters), so the
  harness adds no drift.
- **The mention region:** it covers the whole chapter except in Styles ch01, where it ends at character 11,526 of
  22,873. After it, B and C keep predicted mentions (131 in Styles) and C keeps predicted links (302 mentions joined
  a gold entity by vote, 83 kept a predicted cluster). The after-region claim outcomes are the same in A and C.
- **The LLM is held fixed.** Every call is keyed on the full request (system prompt, prompt, schema, length, model).
  Run A filled the cache; B and C replayed all 50 calls with no misses, so NuExtract's output is identical across
  A, B and C.

## Scores (official `score-v2`, reviewed gold only)

| Run | Mention F1 exact / overlap | B³ F1 (linked) | Linking | Facts tp/fp/fn, F1 | Relationships tp/fp/fn, F1 | Lenient tp/fp/fn, F1 |
| --- | --- | --- | --- | --- | --- | --- |
| A0 | 0.746 / 0.850 | 0.579 (0.702) | 0.901 | 5/7/23, 0.250 | 6/21/25, 0.207 | 11/16/20, 0.379 |
| A | 0.746 / 0.850 | 0.579 (0.702) | 0.901 | 5/7/23, 0.250 | 6/21/25, 0.207 | 11/16/20, 0.379 |
| B | 0.987 / 0.987 | 0.658 (0.665) | 0.932 | 5/7/23, 0.250 | 2/29/29, 0.065 | 3/28/28, 0.097 |
| C | 0.987 / 0.987 | 0.986 (1.000) | 1.000 | 5/7/23, 0.250 | 2/26/29, 0.068 | 3/25/28, 0.102 |
| M | = A0 | = A0 | = A0 | = A0 | 6/21/25, 0.207 | 11/16/20, 0.379 |

B's mention precision is 0.973, not 1.0, because the relations stage's possessive-role rule (`role_pairs`) still
creates mentions after injection.

### Why B and C lose relationships under the official scorer

`role_pairs` expects GLiNER-style spans ("wife"). The v2 gold spans include the determiner ("his wife", with "his"
nested). Given gold spans, `role_pairs` finds no holder mention without the possessor, so it creates a bare "wife"
mention. The scorer's one-to-one alignment has already matched "his wife" to its gold copy, so the new mention names
no entity. 18 relationship endpoints in B are such nested, unresolved mentions; in A there is 1. This is a clash
between the extractor's span convention and the gold's, not evidence that gold mentions hurt.

### Diagnostic resolver (not an official score)

`experiments/claims.py:ContainmentResolver` gives a mention the official resolver leaves unresolved the entity of the
smallest gold mention that strictly contains it. It is applied identically to every run:

| Run | Facts tp/fp/fn, F1 | Relationships tp/fp/fn, F1 | Lenient tp/fp/fn, F1 |
| --- | --- | --- | --- |
| A | 5/7/23, 0.250 | 6/21/25, 0.207 | 11/16/20, 0.379 |
| B | 5/7/23, 0.250 | 7/21/24, 0.237 | 12/16/19, 0.407 |
| C | 5/7/23, 0.250 | 7/20/24, 0.241 | 12/15/19, 0.414 |

Measured effect, with LLM output fixed: gold mentions add 1 relationship, gold coreference adds 0 more, and facts are
unchanged.

## Predicate mapping (run M)

- **Vocabularies:** v1 has 12 predicates; v2 has 14. They share 11. CHILD_OF is v1-only; FATHER_OF, MOTHER_OF and
  ENGAGED_TO are v2-only.
- **The deterministic mapping:** shared predicates map to themselves, and CHILD_OF(a, b) → PARENT_OF(b, a).
  PARENT_OF → FATHER_OF or MOTHER_OF is **not mapped**, because it needs the parent's gender.
- **Predicted:** PARENT_OF 14, MARRIED_TO 10, SIBLING_OF 4, FRIEND_OF 2, and no CHILD_OF, so the mapping changes no
  prediction and the scores are identical to A0.
- **Gold:** WORKS_FOR 6, MARRIED_TO 6, FATHER_OF 4, RELATED_TO 4, MOTHER_OF 2, SIBLING_OF 2, OWNS 2, FRIEND_OF 2,
  KNOWS 2, MEMBER_OF 1.
- **The strict-vs-lenient gap (6 → 11) is five PARENT_OF predictions whose gold counterpart is FATHER_OF or
  MOTHER_OF.** For example, "John's father PARENT_OF John" (Styles), "Lord Abbotsbury PARENT_OF Lady Tadminster"
  (Styles) and "Mr. Bennet PARENT_OF daughters" (P&P). These are unmappable, not wrong. Because the extractor's
  vocabulary has no FATHER_OF or MOTHER_OF, its strict relationship recall can never exceed 25/31 (0.81).

## Error breakdown

### Facts (run A; B and C are identical)

| Gold facts (28) | Count | In NuExtract's raw answer? |
| --- | --- | --- |
| Found | 5 | yes, all 5 |
| Missed: entity detected, no fact produced | 19 | 18 no, 1 yes |
| Missed: wrong value for the entity | 3 | 1 no, 2 yes |
| Missed: entity never detected | 1 | no |

20 of the 28 gold facts (71%) never appear in NuExtract's raw answer. 3 were in the raw answer but lost in the code:
- `evelyn_howard` age: raw "forty", gold "about forty". This is a value mismatch, not a filter problem.
- `dr_bauerstein` occupation: the raw value ("London specialist; a very clever man—one of the greatest living
  experts on poisons…") exceeds the 40-character cap. The title rule then supplied "doctor" from "Dr.", which isn't
  the gold value ("specialist").
- `cynthia_murdoch` hair colour "auburn": in the raw answer but never recorded. The answer's name didn't ground to a
  mention.

Recall by property: occupation 2/10, age 2/3, eye colour 1/1; status 0/4, title 0/3, location 0/3, hair colour 0/2,
birth place 0/1, origin 0/1.

Predicted facts (12): 5 correct, 2 wrong values (above), 5 false positives:
- Oliver status "orphan" and location "workhouse"
- Lawrence status "delicate youth"
- John location "Styles", and John Cavendish location "Styles St. Mary"

Representative misses (never in the raw answer), with their gold evidence:
- Oliver Twist: `the_surgeon` occupation "surgeon" ("by the parish surgeon"), `old_sally` occupation "nurse"
  ("interposed the nurse"), `agnes_fleming` status DEAD ("fell back and died").
- P&P: `charles_bingley` origin "the north of England" ("…a young man of large fortune from the north of England").

The Oliver Twist raw answers show the pattern. NuExtract lists the people but fills no property: `{'name': 'parish
surgeon'}`, `{'name': 'the nurse'}`, `{'name': 'young woman'}`. Its only relationship answer is "Oliver child_of a
workhouse".

### Relationships (run A, official scorer)

| Gold relationships (31) | Count | In NuExtract's raw answer? |
| --- | --- | --- |
| Found (strict) | 6 | 3 yes; 3 came from the possessive-role rules |
| Found, lenient only (PARENT_OF vs FATHER_OF / MOTHER_OF) | 5 | 4 no (rules), 1 other relation |
| Missed: no prediction | 11 | no |
| Missed: an entity never detected | 6 | no |
| Missed: wrong predicate | 3 | no |

27 of the 31 gold relationships never appear in the raw answer. With gold mentions and coreference (C, diagnostic),
"entity never detected" drops from 6 to 3, but those relationships are still missed because nothing produced them.

Representative misses:
- `millie` WORKS_FOR `mrs_hall` ("Millie, her lymphatic maid")
- `the_surgeon` WORKS_FOR `the_parish` ("a parish surgeon who did such matters by contract")
- `mr_cavendish` OWNS `styles_court` ("Styles Court, had been purchased by Mr. Cavendish")
- `mrs_halls_sister` MOTHER_OF `tom` and `mrs_hall` RELATED_TO `tom` ("There was my sister's son, Tom")

Predicted relationships (27): 6 correct, 5 lenient only, 5 wrong endpoint, 3 wrong predicate, 5 unresolved, 3 false
positives.
- **Wrong endpoint, mostly coreference errors:**
  - "sister PARENT_OF Tom" resolves to Tom–Tom
  - "her MARRIED_TO husband" resolves to Alfred–Alfred
  - "John Cavendish MARRIED_TO wife" resolves the wife to Emily
  - "Mrs. Inglethorp MARRIED_TO Mr. Hastings"
- **Wrong predicate:**
  - "John MARRIED_TO Hastings" (gold KNOWS)
  - "step-mother PARENT_OF Their" (gold RELATED_TO)
  - "my FRIEND_OF children" (Mr. Bennet and the daughters)
- **Unresolved:** an endpoint that is a role noun created by `role_pairs`, such as "father", "brother", "husband" or
  "sisters".
- **False positives:** "stranger SIBLING_OF sister" (Griffin–Tom) and "mother PARENT_OF Hastings".

### Fields the extractor cannot express

- 12 gold facts and 15 gold relationships carry `claimed_by`. Matching ignores the claimant, so these don't cause
  misses. But the extractor emits no claimant, so attribution accuracy is untestable: the 11/11 in the baseline only
  shows that the matched claims are narration.
- No assertion values are emitted. All gold claims in this sample are `asserted`.
- The 6 FATHER_OF / MOTHER_OF relationships are covered under predicate mapping above.
- The extractor emits no quotes, so quote recall is 0 by construction.

## Decision

1. **Predicate mapping:** no effect. The only remaining gap is PARENT_OF vs FATHER_OF / MOTHER_OF, which needs gender
   and is out of scope for a mapping.
2. **Mentions and coreference are not the dominant bottleneck for claims on this sample.** With LLM output fixed,
   making both perfect moves facts by 0 and relationships by +1 (diagnostic).
3. **The dominant measured bottleneck is the LLM extraction step's recall.** NuExtract's raw answers contain 8/28 gold
   facts and 3/31 gold relationships. The code's filters lose 3 facts and no relationships that the model did state.
4. **Secondary findings:**
   - The possessive-role rules produce most correct relationships, but their endpoints are wrong when coreference
     merges the wrong mentions.
   - Their span convention conflicts with v2 gold spans.
   - The extractor cannot express FATHER_OF / MOTHER_OF or `claimed_by`.

**Next smallest intervention to test:** an LLM-stage-only experiment that keeps run C's inputs (gold mentions and
coreference) and everything else fixed, and replaces the two open templates ("people", "relationships") with closed
questions over candidates:
- **For facts:** per character mentioned in a sentence, "What does this sentence state as X's occupation (or age,
  status…)? Copy the words, or answer none."
- **For relationships:** per pair of entities in one sentence, "Which of these relations does the sentence state
  between A and B?", with "none" allowed.

Score its raw recall against the same 28 facts and 31 relationships, and its precision, before touching production.
A cheaper first probe of the same hypothesis is the people template asked for one named person at a time. The
Oliver Twist answers suggest the many-people template is what comes back with empty fields.

What this does not show: that another prompt or model would recover the missing claims. That is the next experiment.

## Limitations

- **The sample is small:** 28 facts and 31 relationships, so a difference of one claim moves F1 by about 0.03.
- **The gold:** Styles ch01 and most Invisible Man ch01 layers were accepted in bulk (see the chapter notes), and no
  double review (§9) has been done yet.
- **Styles is a hybrid:** after its mention region, B and C use predicted mentions. The after-region outcomes are the
  same in A and C, so this doesn't drive the comparison.
- **The containment resolver is a diagnostic,** reported beside the official scores and never in place of them.
- **The raw-answer matching:** an answer's name counts for an entity when the pipeline's `name_key` matches the
  entity's name, an alias, or one of its gold mention texts in the chunk. A paraphrased name would be missed. A
  spot-check of Oliver Twist confirmed those chapters' `raw_none` results.
- **Single run:** one run at temperature 0. Events and temporal output were produced but not scored.

## Reproduce

All outputs are in `runs/2026-10-17_oracle_v2/` (gitignored). The frozen baseline is `A0_baseline/` (read-only, with
`SHA256SUMS` and `MANIFEST.md`). Each run has `pred/`, `analysis/` and `run_meta.json`; the cache is `llm_cache.json`.

```
. D:\orion_env\activate.ps1
cd extractor
python -m experiments.oracle A ../runs/2026-10-17_oracle_v2/A --cache ../runs/2026-10-17_oracle_v2/llm_cache.json ../gold/v2/{pride_and_prejudice,oliver_twist,the_invisible_man,the_mysterious_affair_at_styles}/ch01.json
#   then the same with B and C (cache replay)
python -m experiments.analyze ../runs/2026-10-17_oracle_v2/A/pred ../runs/2026-10-17_oracle_v2/A/analysis
python -m experiments.analyze ../runs/2026-10-17_oracle_v2/A0_baseline/pred ../runs/2026-10-17_oracle_v2/M_predicate_map --map-predicates
python -m experiments.analyze ../runs/2026-10-17_oracle_v2/C/pred ../runs/2026-10-17_oracle_v2/containment_C --containment
python -m experiments.llm_raw ../runs/2026-10-17_oracle_v2/llm_cache.json ../runs/2026-10-17_oracle_v2/llm_raw.json
```

Tests:
- `cd extractor && python -m pytest tests -q`: 35 passed, including 6 for the harness in `tests/test_oracle.py`.
- `cd backend && PYTHONPATH=. pytest app/tests/ -q`: 283 passed.
