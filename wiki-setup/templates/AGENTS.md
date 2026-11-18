# {{TITLE}} — wiki schema

This file is the **schema** for this wiki: what it is for, how it is laid out, and the
conventions every agent follows when reading or writing it. The user and the agent
co-evolve it. When a convention changes, edit this file and append a `schema` entry to
`log.md`.

The `wiki-setup`, `wiki-ingest`, `wiki-query` and `wiki-lint` skills hold the full
procedures. **This file wins on conventions** — if a skill's default disagrees with
something written here, follow this file.

## Purpose

{{DOMAIN}}

<!-- Keep this short: what the wiki is for, what is in and out of scope, and the
questions it should eventually be able to answer. -->

## The three layers

| Layer   | Path         | Owner | Rule |
|---------|--------------|-------|------|
| Raw     | `raw/`       | user  | Immutable source of truth. Read it, never edit, rename or delete it. The only writes allowed: saving a newly fetched source, and adding a markdown conversion next to a non-markdown source. |
| Wiki    | `wiki/`      | agent | The agent writes and maintains every page. The user reads, browses and asks questions. |
| Schema  | `AGENTS.md`  | both  | Changed only with the user's agreement. |

`outputs/` holds generated artifacts (slide decks, charts, canvases, lint reports). It is
not part of the knowledge base and is not indexed.

## Layout

```
.
├── AGENTS.md            # this schema (CLAUDE.md imports it)
├── .llm-wiki.yml        # machine config: qmd collections, mode, page types
├── log.md               # append-only operations log
├── raw/                 # immutable sources (+ raw/assets/ for images)
├── wiki/
│   ├── index.md         # catalog of every page — read first
│   ├── overview.md      # the evolving big-picture synthesis
│   ├── sources/         # one summary page per ingested source
│   ├── entities/        # people, organisations, products, places, works
│   ├── concepts/        # ideas, methods, themes, debates
│   └── analyses/        # filed query answers, comparisons, deep dives
└── outputs/             # slides, charts, canvases, lint reports
```

Page types map to folders in `.llm-wiki.yml` (`types:`). To add a type (e.g. `character`
→ `characters/`), add the folder, add it to `types:`, describe it below, and add an
index section for it.

## Page types

Every page in `wiki/` starts with YAML frontmatter. `title`, `type`, `created` and
`updated` are required on every page. Dates are `YYYY-MM-DD`. Change `updated` whenever
you change a page's content.

### source — `wiki/sources/`

One page per ingested raw source. Faithful, specific summary of what *that source* says.

```yaml
---
title: "Attention Is All You Need"
type: source
raw: "raw/2026-11-18-attention-is-all-you-need.md"   # path of the file you read
source_hash: 3f2a9c1b7d4e   # first 12 hex chars of sha256(raw file) at ingest
url: https://arxiv.org/abs/1706.03762                 # if any
author: Vaswani et al.
published: 2017-06-12
ingested: 2026-11-18
tags: [transformers]
created: 2026-11-18
updated: 2026-11-18
---
```

Body: `# Title`, a one-paragraph TL;DR, `## Key takeaways`, `## Notes` (by section of the
source, with specifics: numbers, names, dates), `## Connections` (the wiki pages this source
touched, each with one line on what it adds), `## Contradictions & open questions`.

Slug: `<author-or-org>-<year>-<short-title>`, e.g. `vaswani-2017-attention`. It doubles as
a readable citation: `([[vaswani-2017-attention]])`.

### entity — `wiki/entities/`

A specific thing with a name: person, organisation, product, place, dataset, work.

```yaml
---
title: "OpenAI"
type: entity
kind: organisation          # person | organisation | product | place | dataset | work | …
aliases: ["OpenAI Inc."]
tags: []
sources: ["[[source-slug-a]]", "[[source-slug-b]]"]
created: 2026-11-18
updated: 2026-11-18
---
```

Body: `# Name`, one line saying what it is, `## Summary`, `## Key facts` (each cited),
`## Relationships` (links to other pages), optional `## Timeline`, `## Open questions`,
`## Sources`.

### concept — `wiki/concepts/`

An idea, method, theme, claim or debate.

Frontmatter as for entity, without `kind`. Body: `# Name`, a one-to-two sentence
definition, `## Explanation`, `## Evidence & claims` (cited, attributed), `## Disagreements`
(if any), `## Related`, `## Sources`.

### analysis — `wiki/analyses/`

A query answer worth keeping: comparison, synthesis, deep dive.

Frontmatter adds `question: "…"`. Body: `# Title`, `## Question`, `## Answer`,
`## Evidence`, `## Caveats & gaps`, `## Sources consulted`.

### overview — `wiki/overview.md`

The one page that says what the wiki currently believes: main threads, current thesis,
biggest open questions, where the evidence is thin. Revise it when a source shifts the
big picture, not on every ingest.

## Writing conventions

- **Filenames**: kebab-case ASCII slug + `.md`. Basenames must be unique across the whole
  vault (`wiki/` *and* `raw/`), because `[[wikilinks]]` resolve by name. Check before
  creating a page.
- **Titles**: frontmatter `title` is the human-readable name; the first heading repeats it.
- **Links**: Obsidian wikilinks — `[[slug]]` or `[[slug|display text]]`. Link the first
  mention of any page-worthy entity or concept in each section. Link raw files by path:
  `[[raw/2026-11-18-some-article]]`. A link to a page that does not exist yet (a "red
  link") is allowed and means "this deserves a page"; lint tracks them.
- **Citations**: every non-obvious claim on entity, concept and analysis pages cites the
  source page(s) inline — `…was introduced in 2017 ([[vaswani-2017-attention]]).` Keep the
  `sources:` frontmatter and the `## Sources` section in sync with what the page cites.
- **Synthesis, not stacking**: entity and concept pages integrate what all sources say into
  one coherent account. Don't append a paragraph per source.
- **Attribution**: separate what a source claims from what is established —
  "The authors report…", "According to [[x]]…".
- **Contradictions**: never silently overwrite. Keep both claims, cite both, and flag it:

  ```markdown
  > [!warning] Contradiction
  > [[source-a]] says X. [[source-b]] (newer) says Y.
  ```

  When a newer source clearly supersedes an older claim, move the old claim to a
  `## History` section with "superseded by [[source-b]]".
- **Open questions**: mark them with `> [!question]` callouts. Lint collects them.
- **Quotes**: short and only when the wording matters, with location (section/page).
  Summarise everything else.
- **Images**: live in `raw/assets/`; embed with `![[file.png]]`.
- **Tags**: lowercase kebab-case, from the vocabulary below. Add a tag here before using
  it.

## index.md

The catalog of every page in `wiki/`, grouped by type, one line per page:

```markdown
## Concepts
- [[self-attention]] — mechanism letting each token weigh every other token · 3 sources · updated 2026-11-18
```

Source lines end with `· <author>, <year> · ingested <date>`. Read `index.md` first for
every query. Update it in the same change as any page you add, rename or remove. When it
passes ~400 lines, split it into `wiki/indexes/<type>.md` hub pages and keep `index.md`
as the top-level map.

## log.md

Append-only, oldest first. Every operation adds an entry whose header line has exactly
this shape (so `grep "^## \[" log.md | tail -5` works):

```markdown
## [2026-11-18] ingest | Attention Is All You Need
- source: [[vaswani-2017-attention]]
- created: [[self-attention]], [[transformer]]
- updated: [[overview]], [[index]]
- notes: contradiction with [[rnn]] flagged
```

Operations: `setup`, `ingest`, `query`, `lint`, `schema`, `note`.

## Search (qmd)

- Wiki pages: collection `{{WIKI_COLLECTION}}` · raw sources: collection `{{RAW_COLLECTION}}`
- Exact names/terms: `qmd search "term" -c {{WIKI_COLLECTION}} -n 10`
- Concepts/paraphrase: `qmd query $'intent: …\nlex: …\nvec: …' -c {{WIKI_COLLECTION}}`
- Read hits in full: `qmd get "#docid"`, `qmd multi-get "#a,#b" --format md`
- After writing pages: `qmd update` (BM25, instant), then `qmd embed` (vectors)
- If vector search or reranking fails, fall back to `qmd search`.

## Operating mode

`mode` in `.llm-wiki.yml` is `{{MODE}}`.

- `supervised`: ingest discusses takeaways and a page plan before writing; lint reports and
  asks before fixing; query offers to file answers.
- `autonomous`: ingest writes straight away and reports after; lint applies safe fixes and
  asks only about judgment calls; query files substantial answers automatically.

The user can override per request ("just do it", "batch ingest", "check with me first").

## Domain rules

<!-- Grows over time. Record decisions the user makes, e.g.
- Don't create pages for people mentioned only once.
- Prefer primary sources; mark secondary reporting as such.
- Track numbers with units and the date they were true. -->

## Tag vocabulary

<!-- e.g. method, dataset, benchmark, open-question -->
