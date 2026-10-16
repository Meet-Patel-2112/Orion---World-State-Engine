# Orion Gold v2: Annotation Guidelines

Version 2.0 · 2026-10-12 · Schema: [`orion_gold_v2.schema.json`](../orion_gold_v2.schema.json) · Replaces the
conventions implied by v1 (see [`gold_schema_assessment.md`](gold_schema_assessment.md) for why).

These rules are for everyone who drafts or reviews gold: the Claude drafting pass and the team reviewers. When two
people would annotate a passage differently, the rule here decides. If no rule decides, add one here before going on,
and say so in the review note.

---

## 1. What makes an item gold

- Every item carries a `review` record. An item is **gold** only when `review.status` is `accepted` or `corrected`.
  `pending` items are drafts and are never scored.
- A reviewer either accepts an item, corrects it in place (and sets `corrected`), or deletes it. Rejected items are
  deleted, not kept.
- A document's `annotation.status` moves `draft` → `in_review` → `reviewed` (every item checked by one person) →
  `adjudicated` (checked by two people, disagreements settled).
- **Reviewing includes recall.** Reading the chapter for anything missing is part of the review, not optional. A
  layer marked `exhaustive` promises that nothing is missing.
- About 20% of chapters are reviewed by two people independently, so agreement can be measured (§9).

## 2. Documents, works and entity keys

- One document is one chapter of one work: `doc_id` is `<work_id>/ch<NN>`, chapters numbered by position in the
  book (1, 2, 3, …), even when the book restarts its numbering in each volume (Pride and Prejudice does).
- `text` is the chapter exactly as annotated, from its heading to the next chapter's heading. Every offset is a
  character offset into `text`.
- **`entity_key` is the backbone of v2.** It is the same string for the same entity in every chapter of a work, which
  is what lets the gold test identity across chapters.
  - Lowercase snake_case of the fullest proper name: `elizabeth_bennet`, `jack_dawkins`, `griffin`.
  - Keep a key once it is chosen, even if a later chapter reveals a fuller name. Record the new name in `aliases`.
  - A character revealed to be someone already known is the same key from the start. "The stranger" in The Invisible
    Man is `griffin` in chapter 1, although the reader learns the name later. Gold records the truth of the story, so
    that identity resolution can be scored.
  - **Provisional entities.** When a reference needs a key but its identity isn't settled (it may prove to be a
    known place or person, or stay an abstract reference), give it its own key with `provisional: true`:
    `neighbourhood` in Pride and Prejudice chapter 1 may be Meryton, Longbourn, or neither. Never merge it into a
    known entity on a guess. When a later chapter establishes the identity, merge across the whole work: replace the
    provisional key with the known one in every chapter, move its names to `aliases`, and run `validate-v2` on the
    work so the cross-chapter check catches anything missed.
  - For PDNC works, keys come from PDNC's character list (`external_ids.pdnc` keeps its id).
- `entities` lists every entity this chapter refers to, with `name` (fullest proper name in the work), `type`, and
  `aliases` (every other name or fixed description the work uses anywhere: `Lizzy`, `Eliza`, `the Artful Dodger`).

## 3. Layer coverage

`annotation.layers` says how completely each layer was annotated. Scorers depend on it, so set it honestly.

| Coverage | Meaning | How it is scored |
| --- | --- | --- |
| `exhaustive` | Every instance inside `region` (or the whole chapter) is annotated | Precision and recall |
| `partial` | Some instances are annotated | Recall only |
| `none` | Not annotated | Not scored |

Batch 1 (§10) uses: quotes, facts and relationships **exhaustive** over the whole chapter; mentions **exhaustive in
a region** of about the first 2,000 words; events and temporal layers **none** for now.

## 4. Mentions and coreference

A mention is a stretch of text that refers to an entity. Each one is linked to its entity through `entity_key`.

**What to mark** (inside the mentions region):

- Every reference to a **character**: names (`Mr. Darcy`), descriptions (`the young man`, `his wife`), pronouns
  (`he`, `her`, `himself`), and the narrator's `I` / `me` / `my`.
- References to **locations, organizations and objects** that the story treats as particular things (`Netherfield
  Park`, `the workhouse`, `the Coach and Horses`, `the letter` when it matters to the plot).
- Skip generic and non-referring uses: `one` in "one must", `it` in "it was raining", `a man` in "no man would",
  and general claims such as the opening of Pride and Prejudice ("a single man in possession of a good fortune"),
  which is about wealthy unmarried men in general, not about Bingley.
- Skip predicate nominals: in "Bingley is a single man of large fortune", only `Bingley` is a mention. A
  description of what an entity is tells us something about it; it isn't another reference to it. If the product
  needs descriptions, attributes or generic statements, they get a layer of their own, so this layer stays
  references only.

**Span boundaries** (the most common source of disagreement):

- Mark the full noun phrase with its determiner and pre-modifiers: `the tall young man`, `his eldest daughter`.
- Leave out relative clauses and trailing prepositional phrases: `the man [who came yesterday]` is `the man`;
  `the master [of the workhouse]` is `the master`.
- Titles belong to the name: `Mr. Bennet`, `Sir William Lucas`, `Dr. Kemp`.
- A possessive marks the possessor: in `Mr. Bennet's daughter`, mark both `Mr. Bennet` (that entity) and
  `Mr. Bennet's daughter` (the daughter). Nested mentions are allowed.
- The same holds for possessive determiners: `his`, `her`, `my`, `your`, `our`, `their` are mentions of the
  possessor. In `his wife`, mark `his` (Mr. Bennet) and `his wife` (Mrs. Bennet). Mark them also when the larger
  phrase is not a mention: `her` in "the business of her life". PDNC's imported mentions follow this rule, so
  imported and drafted mentions agree.
- A vocative or full form of address is one mention with the name nested inside it: `My dear Mr. Bennet` and
  `Mr. Bennet`. The `my` of an endearment (`my dear`) is part of the fixed form and is not marked as the speaker.
- A name used as a modifier is a mention of its own entity, nested: in `the Netherfield party`, mark `the
  Netherfield party` (the group) and `Netherfield` (the place).
- A partitive that picks out one particular person is a mention of that person, with the group nested: in "his
  having slighted one of her daughters" (Elizabeth), mark `one of her daughters` (Elizabeth), `her daughters` (the
  group) and `her`. A partitive that picks out no one in particular ("if he marries one of them") is not a mention;
  mark only the group inside it.
- No leading or trailing whitespace or punctuation inside a span.

**Fields:**

- `type`: `character` (people, animals that act, and groups of people, such as `the Bennets`, which get their own
  key, e.g. `bennet_family`); `location` (places, buildings, rooms); `organization` (bodies that act: the parish
  board, the police); `object` (physical things); `other`.
- `mention_kind`: `proper` (a name, with or without title), `nominal` (a description), `pronominal` (a pronoun).
- `entity_key`: the entity referred to. `null` when the mention refers to something that isn't an entity: a thing
  mentioned once and never again (`a passing carriage`), or a plural for a set that has no entity of its own (`us`
  in "impossible for us to visit him", `they` for Sir William and Lady Lucas together). Don't invent a group entity
  to avoid a null. Equally, don't leave a plural unresolved just because it is plural: when it refers to an
  established group entity and the context supports it, link it (`them` for the daughters is `bennet_daughters`).
  - A subset of a group is not the group: `the others` (the daughters other than Lizzy) and `her sisters` are
    `null`, not `bennet_daughters`.
  - A plural naming two or more established entities (`they` for Sir William and Lady Lucas) is `null` with a
    review note. A mention holds one entity key; never pick one of the people. Multi-entity mentions are a known
    limitation of v2, to be added only if the product needs them.

## 5. Quotes

- A quote is direct speech or thought in quotation marks. `spans` cover the words without the marks, one span per
  piece when narration interrupts.
- Letters, notes and other written text reproduced in the chapter are not quotes, as in PDNC (Lydia's letter in
  Pride and Prejudice chapter 61). Facts and relationships stated in them still count, with `claimed_by` set to the
  writer.
- `speaker_entity_key`: who speaks. Use `null` only if a careful reader cannot tell.
- `addressee_entity_keys`: who is spoken to, possibly several; empty if unclear.
- `quote_type`: `explicit` (the speaker is named in the speech tag), `anaphoric` (pronoun or description: `she
  said`, `cried his wife`), `implicit` (no tag).
- For PDNC works, quotes are imported from PDNC (`origin: pdnc`) and only spot-checked (§9).

## 6. Facts

A fact is a property of an entity that the chapter states. Annotate one item per distinct `(entity, property, value,
assertion)` in the chapter. If it is stated twice, use the clearest statement as evidence.

**Properties.** Only these; anything else is not a fact in v2.

| Property | Mark | Don't mark |
| --- | --- | --- |
| `age` | A stated age: `one-and-twenty`, `nine years old`; set `age_years` | "young", "elderly" (no number) |
| `date_of_birth` | A stated birth date or year | |
| `birth_place` | Where the entity was born | Where they grew up (`origin`) |
| `origin` | Where they come from: home town, country, family seat | Where they are now (`location`) |
| `eye_color`, `hair_color` | The color words: `dark`, `fine eyes` is not a color | |
| `species` | For non-human characters | Humans (default) |
| `occupation` | A job or trade: `clergyman`, `surgeon`, `beadle`, `chemist` | Roles in a relationship (`wife`, `friend`), social rank (`gentleman`) |
| `title` | A rank or honorific that carries status: `Sir`, `Lady`, `Colonel`, `Captain`, `Dr.` | `Mr.`, `Mrs.`, `Miss` (say nothing) |
| `status` | Alive, dead, missing, injured, unconscious; set `status_value` | Mood or health in general (`ill`, unless injured) |
| `location` | Where the entity is at that point in the chapter; one item per change | Places merely mentioned or visited in a quote |

**Fields:**

- `value`: the text's own words, as short as possible without losing meaning (`one-and-twenty`, not `she is
  one-and-twenty`). Set `value_span` when the value occurs verbatim.
- `evidence`: the shortest stretch, usually one sentence, that states the fact. Must contain `value_span`.
- `status_value`: `ALIVE`, `DEAD`, `MISSING`, `INJURED`, `UNCONSCIOUS`, or `OTHER`. Required for `status`. A death
  stated as an event ("she died") is also a `status` fact `DEAD`.
- `age_years`: the age as a number when the text gives one (`one-and-twenty` → 21, `about fifty` → 50).

## 7. Relationships

A relationship is a lasting tie between two entities that the chapter states or that a role noun makes explicit
(`his wife`, `my nephew`, `her master`). One item per distinct `(subject, predicate, object, assertion)` in the
chapter.

| Predicate | Direction | Mark when | Don't mark |
| --- | --- | --- | --- |
| `FATHER_OF`, `MOTHER_OF` | parent → child | The text says which parent | |
| `PARENT_OF` | parent → child | Parenthood stated, parent unknown or a couple named together | When `FATHER_OF` / `MOTHER_OF` applies |
| `SIBLING_OF` | either | Brothers, sisters, half-siblings | Step-siblings (`RELATED_TO`) |
| `MARRIED_TO` | either | Married at that point in the story | Engaged (`ENGAGED_TO`) |
| `ENGAGED_TO` | either | Engaged, including secret engagements | Courting, admiration |
| `RELATED_TO` | either | Other family: cousin, aunt, uncle, in-law, step-relation | |
| `FRIEND_OF` | either | Called friends, or a friendship is plainly described | Being polite in one scene |
| `ENEMY_OF` | either | Stated hostility or rivalry that lasts | One argument |
| `ALLY_OF` | either | Working together toward a goal | Friends (`FRIEND_OF`) |
| `KNOWS` | either | Acquaintance stated (`an old acquaintance`, `had met him before`) and no more specific predicate applies | Two characters who merely talk in a scene |
| `WORKS_FOR` | employee → employer | Servant, employee, apprentice, curate under a patron | |
| `MEMBER_OF` | member → organization | Membership of an organization or group | |
| `OWNS` | owner → thing | Ownership of a place or object | |

- **Evidence** is required: the shortest stretch that states the tie. Inferring a tie across the chapter ("they must
  be sisters") is not enough; the tie must be stated somewhere in this chapter.
- **Don't infer a tie from names, titles or co-occurrence.** "Sir William and Lady Lucas are determined to go"
  establishes two titled people, not a marriage; leave `MARRIED_TO` out until a chapter states it. There is no
  "probably true" state: `hypothetical` describes the text (a character wondering), never the annotator's guess.
- **Group ties stay group ties.** When the chapter states a tie to a group ("to get her daughters married"),
  annotate it to the group entity (`mrs_bennet MOTHER_OF bennet_daughters`). Don't expand it into one relationship
  per member because the members are known from elsewhere in the book: an individual tie needs its own evidence, in
  the chapter where it is stated. This is an annotation policy, not a claim that individual parentage is unknown in
  the novel. Which characters belong to a group is membership, not parentage, and is not annotated in batch 1.
- Write directed predicates in their fixed direction: there is no `CHILD_OF`, and `A WORKS_FOR B` means A is the
  employee.
- A tie that changes inside the chapter gets both items: `ENGAGED_TO` with its evidence, then `MARRIED_TO` with its
  own.

## 8. Assertion and who says it

These fields keep lies, rumours, hearsay, dreams and denials from becoming contradictions.

- `assertion` is how the text presents the statement:
  - `asserted`: stated as true in the story;
  - `negated`: stated as not true ("he was not her brother");
  - `hypothetical`: wished, feared, supposed, dreamt, asked, or conditional ("if he were dead…", "perhaps she is his
    daughter").
- `claimed_by` is the **immediate claimant**: the character whose speech, thought or letter contains the
  statement. Unset when the narrator states it.
- `source_entity_key` is the **reported source**: the character the claimant names as the origin of the
  information, when the text names one. "Mrs. Long says that Netherfield is taken by a young man of large fortune
  from the north of England", spoken by Mrs. Bennet, has `claimed_by: mrs_bennet` and `source_entity_key:
  mrs_long`. Unset when the claimant speaks for themselves or names no source ("they say…"). Narration reporting a
  rumour about a named character's words ("Mrs. Long had told everyone that…") has a source and no claimant.
- Neither field says what is **true in the story**. Gold records who says what, and on whose word. Whether a claim
  holds is settled by the story's own evidence and by the consistency rules, never by the annotator.
- Narration in a first-person story (Hastings in Styles) is the narrator: leave `claimed_by` unset.
- Testimony at an inquest is claimed by the witness, even when it later proves false. That is exactly the case the
  consistency rules must not flag.

## 9. Review workflow

1. **Draft.** Claude drafts each chapter: entities, mentions in the region, facts and relationships, each with
   evidence and `review: {origin: "claude_draft", status: "pending"}`. PDNC quotes and characters are imported
   (`origin: "pdnc"`).
2. **Validate.** The validator rejects any document with a span outside the text, a mention whose `text` differs from
   its span, evidence that doesn't contain its `value_span`, an unknown `entity_key`, or a `status` fact without
   `status_value`.
3. **Review.** A team member checks every item against §4–§8, then reads the chapter for anything missing. Each item
   ends as `accepted`, `corrected`, or deleted.
4. **Double review.** About 20% of chapters (at least one per work) are reviewed independently by a second person.
   Agreement is the F1 between the two versions per layer. Below 0.8 on facts or relationships, the guideline in
   question is clarified here before more chapters are reviewed.
5. **Spot-check PDNC.** For each PDNC chapter, check 20 quotes for span and speaker. PDNC's own spans sometimes
   include a stray space or newline at an edge; the converter trims them.

## 10. Batch 1

Four public-domain novels from the Project Dialogism Novel Corpus (PDNC, CC-BY 4.0), five chapters each, about
320,000 characters in total.

| Work | Chapters (by position) | Why it is here |
| --- | --- | --- |
| Pride and Prejudice | 1, 3, 22, 46, 61 | Families, father vs mother, engagements becoming marriages, heavy aliasing |
| Oliver Twist | 1, 8, 47, 50, 51 | Aliases (the Artful Dodger is Jack Dawkins), deaths, parentage revealed late |
| The Invisible Man | 1, 7, 17, 20, 28 | Identity revealed late ("the stranger" is Griffin), deaths, third person |
| The Mysterious Affair at Styles | 1, 3, 6, 12, 13 | A death, false testimony and lies: the control case for `claimed_by` |

Source notes:

- Text and annotations come from PDNC at commit `e507a27b89a85c1e9710a897ad0b3f5a9ad73dc4`.
- PDNC's text of The Invisible Man has every apostrophe replaced by a space (`didn t`, `Kemp s`). The converter
  restores them from the Project Gutenberg edition; each restored apostrophe replaces one space, so offsets do not
  move.
- The current gold story ("Accounts From a Lonely Broadcast Station") and "Left Right Game" are copyrighted Reddit
  posts. They should not be the basis of new gold.

**Attribution (CC-BY 4.0):** Vishnubhotla, K., Hammond, A., and Hirst, G. (2022). *The Project Dialogism Novel
Corpus: A Dataset for Quotation Attribution in Literary Texts.* LREC 2022.
<https://github.com/Priya22/project-dialogism-novel-corpus>

Conventions for mention spans follow the spirit of LitBank (Bamman et al., 2019, 2020), whose data is not used for
scoring because BookNLP is trained on it.

## 11. Changes from v1

| v1 | v2 | Why |
| --- | --- | --- |
| Facts and relationships point at one mention | Point at an `entity_key`, with a required `evidence` span | A correct prediction tied to a different mention of the same person no longer scores as wrong |
| No completeness information | `annotation.layers` coverage per layer | Unmarked but real mentions stop counting as false positives |
| `PARENT_OF`, `CHILD_OF` | `FATHER_OF`, `MOTHER_OF`, `PARENT_OF`; no `CHILD_OF`; new `ENGAGED_TO` | REQ-25; one direction per tie; engagements change into marriages |
| Free-text `status` | `status_value` enum | REQ-26 |
| No quotes | `quotes` with speaker and addressees | REQ-26, REQ-37 |
| No assertion | `assertion`, `claimed_by` (immediate claimant), `source_entity_key` (reported source) | Lies, rumours, hearsay and dreams must not become contradictions |
| No way to mark unsettled identity | `provisional` on entities | Unidentified places and people get a key now and are merged once the text settles them |
| Clusters per chapter | `entity_key` across chapters | Identity across chapters can be scored |
| Temporal type `other` | Removed | Every v1 expression was `other`, which carried no information |
| No provenance | `review` per item, `annotation.status` | Drafts and gold are told apart |
