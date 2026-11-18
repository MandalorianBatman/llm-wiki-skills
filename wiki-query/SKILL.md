---
name: wiki-query
description: Answer questions from an LLM-maintained markdown wiki (Karpathy llm-wiki pattern) — read index.md, search with qmd, read the relevant pages, and answer with [[wikilink]] citations; optionally produce a comparison table, Marp slide deck, matplotlib chart or Obsidian canvas, and file valuable answers back into the wiki as analysis pages. Use when the user asks what their wiki/knowledge base/notes say about something, wants a comparison or synthesis across sources, or says "ask the wiki", "query", "what do we know about".
---

# wiki-query

Answer from the compiled wiki, not from scratch. The wiki is the primary source; raw
sources are for verification; your background knowledge is labelled as such.

## 0. Orient

1. **Find the root**: nearest folder (cwd upward) with `.llm-wiki.yml`, or the path the user
   gave. `d=$PWD; while [ "$d" != / ] && [ ! -f "$d/.llm-wiki.yml" ]; do d=$(dirname "$d"); done; echo "$d"`
   No config → you can still answer from any markdown folder with qmd/grep, but skip the
   filing and logging steps and mention `wiki-setup`.
2. Read `AGENTS.md` (conventions win over this skill) and `.llm-wiki.yml` (collections,
   `mode`, `log_queries`, `auto_commit`).
3. **Read `wiki/index.md` first.** At small-to-moderate size it's often enough to pick the
   pages; it also shows what the wiki does *not* cover.

## 1. Find the pages

Combine the index with qmd. Write the structured query fields yourself:

```bash
# conceptual / paraphrased questions
qmd query $'intent: <the actual question, and what to avoid>\nlex: <names, terms, aliases>\nvec: <the idea in source-like words>\nhyde: <what the ideal page would say>' -c <wiki-collection> -n 10
# exact names, titles, rare terms
qmd search "<term>" -c <wiki-collection> -n 10
```

- If `qmd query` is slow or fails (models/GPU), use `qmd search` with good lexical terms.
- If qmd MCP tools are available, the `query` / `get` / `multi_get` tools are equivalent.
- Snippets are leads, not evidence. Read the pages in full: `qmd multi-get "#a,#b,#c"
  --format md`, `qmd get "#id:120:40"` for a slice, or open the file directly.
- Follow `[[links]]` one hop from the key pages when the question spans relationships.
- Go to raw sources (`-c <raw-collection>`, or the `raw:` path on a source page) only to
  verify a specific claim, recover a detail the wiki summarised away, or resolve a
  contradiction.

## 2. Answer

- Lead with the answer. Then the supporting points.
- Cite wiki pages inline as `[[page]]`; for key factual claims cite the source page the
  wiki page cites, e.g. `… (see [[self-attention]], from [[vaswani-2017-attention]])`.
- Surface what the wiki flags: `> [!warning] Contradiction` callouts, open questions,
  single-source claims, stale dates.
- Separate clearly: what the wiki says / what you infer from it / outside knowledge (mark
  it "not in the wiki").
- Say plainly when the wiki doesn't cover something, and name the sources that would fill
  the gap. Don't fill gaps with web results silently — if the user wants web research,
  save findings into raw/ and run them through `wiki-ingest`, so the wiki stays sourced.

## 3. Pick the output form

Default is a markdown answer in the chat. Use another form when the question calls for it
or the user asks (details and templates in `references/output-formats.md`):

| Need | Form | Where |
|------|------|-------|
| compare 3+ things on shared attributes | markdown table | in the answer |
| present / teach | Marp deck | `outputs/slides/<slug>.md` |
| numbers over time / across items | matplotlib chart (+ script) | `outputs/charts/<slug>.png` + `.py` |
| map of relationships | Obsidian canvas | `outputs/canvas/<slug>.canvas` |

Generated artifacts go to `outputs/`, never into `wiki/`. Their content must come from the
wiki pages you read, with sources noted.

## 4. File it back (compounding)

A good answer is new knowledge: a comparison, a synthesis across several pages, a
resolved contradiction, a new connection. File it so future queries build on it.

- **Worth filing** if it draws on ≥2 pages and says something no single page says, or the
  user will likely ask again. Not worth filing: lookups a single page already answers.
- **Supervised**: end the answer with one line — "File this as [[<slug>]] in analyses/?" —
  and file only on yes. **Autonomous**: file worth-filing answers and say so.
- **Filing**:
  1. Write `wiki/analyses/<slug>.md` (type `analysis`, `question:` in frontmatter, `sources:`
     = the source pages underlying it). Sections: Question, Answer, Evidence, Caveats &
     gaps, Sources consulted. Keep the citations.
  2. Add a "See also [[<slug>]]" line (or a sentence in context) to the 1–3 most relevant
     entity/concept pages; bump their `updated`.
  3. If it resolves a contradiction or changes the big picture, update those pages /
     `overview.md` too — with citations to source pages, not to the analysis alone.
  4. Add it to `index.md` under Analyses.
  5. `qmd update`; commit if `auto_commit: true`:
     `git -C <root> add -A -- . && git -C <root> commit -q -m "query: <short question>" -- .`

## 5. Log

If `log_queries: true` (default), append to `log.md`:

```markdown
## [YYYY-MM-DD] query | <question, shortened>
- answered from: [[a]], [[b]], [[c]]
- filed: [[slug]]                   # if filed
- gaps: <what the wiki couldn't answer>   # if any
```

Gaps logged here feed `wiki-lint`'s suggestions for sources to find. Keep entries for
trivial lookups to the header line plus `answered from`. A log-only change doesn't need
its own commit; it rides along with the next one.
