# Orion gold annotations

Gold v2 lives in `v2/<work_id>/`: one `chNN.json` per chapter, valid against
[`orion_gold_v2.schema.json`](../orion_gold_v2.schema.json). The rules for drafting and reviewing are in
[`docs/gold_v2_guidelines.md`](../docs/gold_v2_guidelines.md).

| Work | Chapters | Status |
| --- | --- | --- |
| Pride and Prejudice | 1, 3, 22, 46, 61 | ch01: reviewed (pilot, 2026-10-16). Others: Claude's draft, pending review |
| Oliver Twist | 1, 8, 47, 50, 51 | Claude's draft, pending review |
| The Invisible Man | 1, 7, 17, 20, 28 | Claude's draft, pending review |
| The Mysterious Affair at Styles | 1, 3, 6, 12, 13 | Claude's draft, pending review |

Every chapter has its text, characters, quotes with speakers, and the mentions PDNC marks inside quotes (imported,
`review.origin` `pdnc`). A drafted chapter adds Claude's mentions (exhaustive over the region in
`annotation.layers.mentions`, about the first 2,000 words), entities, facts and relationships (exhaustive over the
whole chapter), all `review.status` `pending`. Where the draft disagrees with a PDNC mention, that PDNC item is
re-opened as `pending` with the drafter's proposal in `review.note`; each chapter's `annotation.notes` lists those
and the other readings that need a reviewer's eye. Only items whose `review.status` is `accepted` or `corrected` are
gold.

## Files per work

- `work.json`: title, author, PDNC folder, chapters, and fixes to PDNC's character list (keys, merged duplicates,
  wrong aliases, `name_map`). Read its `notes` for what was changed and why.
- `chNN.json`: the chapter document. Edit it when reviewing.
- `chNN.issues.txt`: what the converter could not import, such as a quote crossing a chapter boundary.

## Rebuilding the PDNC import

Run from `backend/`. Download each novel's `novel_text.txt`, `quotation_info.csv` and `character_info.csv` from PDNC
commit `e507a27b89a85c1e9710a897ad0b3f5a9ad73dc4` (folder names are in each `work.json`), then:

```bash
PYTHONPATH=. python -m app.evaluation pdnc ../gold/v2/pride_and_prejudice/work.json \
    --pdnc-dir PATH/TO/PrideAndPrejudice --revision e507a27b89a85c1e9710a897ad0b3f5a9ad73dc4

# The Invisible Man: PDNC replaced every non-ASCII character (apostrophes too) with a space; restore them
PYTHONPATH=. python -m app.evaluation pdnc ../gold/v2/the_invisible_man/work.json \
    --pdnc-dir PATH/TO/TheInvisibleMan --revision e507a27b89a85c1e9710a897ad0b3f5a9ad73dc4 \
    --reference-text PATH/TO/pg5230.txt          # https://www.gutenberg.org/cache/epub/5230/pg5230.txt

# Styles: PDNC replaced each non-ASCII character with one space per UTF-8 byte (work.json reference_text.mode
# "bytes"); restoring moves every span to the restored text
PYTHONPATH=. python -m app.evaluation pdnc ../gold/v2/the_mysterious_affair_at_styles/work.json     --pdnc-dir PATH/TO/TheMysteriousAffairAtStyles --revision e507a27b89a85c1e9710a897ad0b3f5a9ad73dc4     --reference-text PATH/TO/pg863.txt           # https://www.gutenberg.org/cache/epub/863/pg863.txt

PYTHONPATH=. python -m app.evaluation validate-v2 ../gold/v2
```

The converter never overwrites an existing `chNN.json` unless given `--force`, which would discard its drafts and
reviews.

## Scoring

Run from `backend/`, with predictions written as `PRED_DIR/<work_id>/chNN.json` (the extractor's document shape):

```bash
PYTHONPATH=. python -m app.evaluation score-v2 ../gold/v2 --pred-dir PRED_DIR [--json OUT.json]
```

By default only `reviewed` or `adjudicated` chapters are scored, on `accepted` or `corrected` items; pending items
are ignored (a prediction matching one is neither right nor wrong). `--include-pending` counts pending items too, for
building and debugging the scorer only: its output is marked PROVISIONAL and is never reported as an evaluation
result (guidelines §1). Metrics are per layer; `backend/app/evaluation/score_v2.py` defines each one.

## Sources and attribution

Texts are public domain. Quotes, speakers, addressees, character lists and in-quote mentions come from the Project
Dialogism Novel Corpus, licensed CC-BY 4.0:

> Vishnubhotla, K., Hammond, A., and Hirst, G. (2022). The Project Dialogism Novel Corpus: A Dataset for Quotation
> Attribution in Literary Texts. *Proceedings of LREC 2022.*
> <https://github.com/Priya22/project-dialogism-novel-corpus>

Changes made to PDNC's data are listed in each `work.json` and in the converter (`backend/app/evaluation/pdnc.py`):
spans trimmed of edge whitespace, characters restored in The Invisible Man and The Mysterious Affair at Styles,
character-list fixes.

The v1 gold (`extractor/data/gold/`) remains in place until the extractor and scorer move to v2.
