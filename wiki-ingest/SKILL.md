---
name: wiki-ingest
description: Ingest a new source into an LLM-maintained markdown wiki (Karpathy llm-wiki pattern) — read it, discuss takeaways, write a source summary page, update or create entity and concept pages with citations, flag contradictions, revise the overview, update index.md and log.md, and re-index qmd. Use when the user drops a file into raw/, pastes a URL, PDF, transcript or notes and says "ingest", "add this to the wiki", "process this source", "file this", or asks to process pending/new sources (single or batch).
---

# wiki-ingest

Compile one source into the wiki so the knowledge is integrated once and kept current —
not re-derived at query time. A single source typically touches 5–15 pages.

## 0. Orient

1. **Find the root**: the nearest folder (cwd upward) containing `.llm-wiki.yml`, or the
   path the user gave.
   `d=$PWD; while [ "$d" != / ] && [ ! -f "$d/.llm-wiki.yml" ]; do d=$(dirname "$d"); done; echo "$d"`
   No config found → this isn't a set-up wiki. Offer the `wiki-setup` skill; don't
   improvise a layout.
2. **Read `AGENTS.md`** (the schema) and `.llm-wiki.yml` (`mode`, `types`, qmd collection
   names, `auto_commit`). The schema's conventions override anything in this skill.
3. **Read `wiki/index.md`** so you know what already exists.
4. **Mode**: `supervised` (default) → discuss before writing (step 3). `autonomous`, or the
   user says "just do it" / "batch" → skip the pause and report afterwards.

## 1. Pick the source(s)

- **User named a file in raw/** → use it.
- **User gave a URL** → fetch it, convert to clean markdown, save as
  `raw/YYYY-MM-DD-<slug>.md` with frontmatter (`title`, `url`, `author`, `published`,
  `fetched`). This and markdown conversions are the only writes you ever make to raw/.
- **User pasted text** (notes, transcript) → save it to `raw/YYYY-MM-DD-<slug>.md` first.
  Everything ingested lives in raw/.
- **PDF / HTML / other** → write a markdown conversion next to it (same stem, `.md`,
  frontmatter `converted_from: <file name>`), e.g. `pdftotext -layout x.pdf -` or your PDF
  reader. qmd only indexes markdown.
- **"Ingest new stuff" / no source named** → run
  `python3 <this-skill-dir>/scripts/pending.py --root <root>` and list what's pending or
  changed. Supervised: confirm which to ingest and in what order. More than one source →
  see Batch below.

Re-ingest of a **changed** source (pending.py lists it under "changed"): diff it against
what the source page says, update affected pages, bump `source_hash`, and log it as
`ingest | <title> (re-ingest)`.

## 2. Read the source

- Read it fully. Long sources: read in chunks; very long ones (books, long reports) are
  ingested per chapter/part, one source page each, linked from a parent source page.
- Images: read the text first, then open the images that carry information (figures,
  tables, diagrams) separately with your image-capable reader. Local images should be in
  `raw/assets/`; mention any remote-only images that matter.
- Note: core claims, numbers, names, dates, definitions, methods, the author's stance,
  and anything surprising.

## 3. Connect to the wiki — and discuss (supervised)

Find what the wiki already says about each important entity/concept in the source:

```bash
qmd search "<exact name or term>" -c <wiki-collection> -n 5          # names, titles
qmd query $'intent: <what you are checking>\nlex: <terms>\nvec: <paraphrase>' -c <wiki-collection> -n 8
qmd multi-get "#id1,#id2" --format md                                # read hits in full
```

Also check index.md for near-duplicate pages (different name, same thing). Then classify
what the source does relative to the wiki: **new**, **confirms**, **extends**,
**contradicts**, **supersedes**.

In supervised mode, stop here and send the user something like:

```
**<Source title>** — <author>, <year> · <kind, length>
Key takeaways
1. …  (3–7, specific)
Against the wiki
- Contradicts [[page]]: wiki says X, this says Y
- Extends [[page]] with …
- New: <entity/concept> (no page yet)
Plan
- create: sources/<slug>, concepts/<a>, entities/<b>
- update: [[c]] (add …), [[overview]] (thesis shifts on …)
Anything to emphasise, skip or correct before I write it up?
```

Wait for the reply; fold the user's emphasis into what you write. If they state a lasting
preference ("don't make pages for minor characters"), offer to record it under
"Domain rules" in AGENTS.md.

## 4. Write the pages

Follow the page types, frontmatter and conventions in AGENTS.md. Defaults if the schema is
silent:

1. **Source page** `wiki/sources/<author-year-short-title>.md` — faithful and specific;
   TL;DR, key takeaways, notes by section, `## Connections` (each touched page + what this
   source adds), contradictions & open questions. Frontmatter includes `raw:` (the file you
   read), `source_hash:` (`python3 <this-skill-dir>/scripts/pending.py --hash <raw file>`),
   `ingested:` today. Check the slug doesn't collide with any basename in `wiki/` or `raw/`.
2. **Entity and concept pages** — for each important one:
   - Exists → integrate the new information into the right sections, rewriting for
     coherence (synthesis, not a paragraph per source). Cite inline
     `([[source-slug]])`, add the source to `sources:` and `## Sources`, bump `updated`.
   - Doesn't exist → create it when it is central to this source, or already mentioned
     (as a red link or plain text) elsewhere in the wiki. Otherwise just link it as a red
     link `[[future-page]]`; lint promotes red links once they recur.
   - Never invent facts to fill a template section; leave it out or add a
     `> [!question]` callout.
3. **Contradictions** — keep both claims, cite both, add a `> [!warning] Contradiction`
   callout on the affected page(s), and list it on the source page. If the new source
   clearly supersedes, move the old claim under `## History` with "superseded by
   [[new-source]]".
4. **Overview** — update `wiki/overview.md` only if the big picture moved (new thread,
   thesis changed, major open question answered or raised). Cite the source.
5. **Cross-links** — add `[[links]]` where existing pages mention newly created pages
   (search for the name with `qmd search` to find them).

## 5. Bookkeeping (same change)

- **index.md**: add a line for every new page under its type's section; refresh the
  summary / source count / updated date for pages you changed.
  `- [[slug]] — one-line summary · N sources · updated YYYY-MM-DD`
- **log.md**: append

  ```markdown
  ## [YYYY-MM-DD] ingest | <Source title>
  - source: [[source-slug]]
  - created: [[a]], [[b]]
  - updated: [[c]], [[overview]], [[index]]
  - notes: <contradictions flagged, open questions, anything skipped>
  ```

- **Re-index**: `qmd update` (fast, BM25). Then `qmd embed` — it is incremental; if it's
  slow or fails, say so and move on (BM25 still works).
- **Commit** (if `auto_commit: true` and the root is a git repo):
  `git -C <root> add -A -- . && git -C <root> commit -q -m "ingest: <title>" -- .`

## 6. Report

Short: what the source added, pages created/updated (as links), contradictions flagged,
open questions it raised, and a natural next step (a related source to find, a question
worth asking, or the next pending file).

## Batch ingest

For several sources (e.g. everything pending.py lists):

- Supervised: confirm the list and order once, then process each source fully (steps 2–5)
  *one at a time*, without pausing per source unless one contradicts the wiki in a way
  that needs the user's call. Report per source in one line, then a combined summary.
- Process sources oldest-first (by `published`), so newer sources correctly supersede.
- One log entry and one commit per source, so each is reviewable and revertable.
- Run `qmd update` after each source (the next one's search depends on it); run
  `qmd embed` once at the end.

## Quality bar

- Specific beats generic: numbers with units and dates, names, mechanisms.
- Attribute claims ("X reports…"), especially contested or single-source ones.
- Keep source pages faithful to the source; keep synthesis on entity/concept pages.
- Short quotes only, with location; never paste long passages.
- Prefer updating an existing page over creating a near-duplicate.
- Every claim you add to an entity/concept page is cited.
