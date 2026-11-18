---
name: wiki-lint
description: Health-check an LLM-maintained markdown wiki (Karpathy llm-wiki pattern) — run deterministic checks (broken/typo links, orphans, index coverage, frontmatter, duplicate names, unsourced pages, un-ingested or changed raw sources, log format), then a judgment pass for contradictions, superseded claims, missing pages and cross-references, thin pages and data gaps; report, fix with the user's go-ahead, and suggest new questions and sources. Use when the user says "lint", "health check", "clean up the wiki", "find contradictions", "what's missing", or periodically after several ingests.
---

# wiki-lint

Keep the wiki healthy as it grows. Two halves: a script for everything mechanical, then
your judgment for everything semantic. Lint never changes raw/.

## 0. Orient

1. **Find the root**: nearest folder (cwd upward) with `.llm-wiki.yml`, or the user's path.
   `d=$PWD; while [ "$d" != / ] && [ ! -f "$d/.llm-wiki.yml" ]; do d=$(dirname "$d"); done; echo "$d"`
   No config → offer `wiki-setup` (it can adopt an existing folder).
2. Read `AGENTS.md` (conventions win) and `.llm-wiki.yml` (`mode`, `types`, collections).
3. **Scope**: default is *recent* — pages changed since the last lint (the script lists
   them). "Full lint" / "deep lint" / first lint ever → all pages. A named topic → pages
   about that topic.

## 1. Structural pass (script)

```bash
python3 <this-skill-dir>/scripts/lint.py --root <root>            # markdown report
python3 <this-skill-dir>/scripts/lint.py --root <root> --json     # same, structured
```

It's read-only and checks: frontmatter & type/folder, duplicate basenames, unresolved
links (split into likely typos vs. wanted "red link" pages ranked by references), orphans,
index coverage, unsourced pages, `uncited-backlink` (a source links to a page that doesn't
cite it — often a missed update), stubs, open-question and contradiction callouts, overview
drift, pending/changed raw sources, log header format, index size, and unlinked mentions
of page titles/aliases. It ends with the semantic-pass scope.

## 2. Semantic pass (you)

Work through the in-scope pages, prioritising pages flagged `uncited-backlink`,
`contradiction`, `overview-drift`, and the most-linked hubs. Read pages in full
(`qmd multi-get "#a,#b" --format md` or open the files). For each check, use qmd to pull
the other pages that talk about the same thing:

```bash
qmd query $'intent: find every page making claims about <X>\nlex: <names, aliases>\nvec: <claim paraphrase>' -c <wiki-collection> -n 10
```

Look for:

1. **Contradictions** not yet flagged — two pages (or a page and its sources) disagreeing
   on a fact, number, date or causal claim. Check existing `[!warning] Contradiction`
   callouts: is one now resolved by a newer source?
2. **Superseded claims** — a claim cited to an older source when a newer source page on
   the same topic says otherwise. Compare `published`/`ingested` dates.
3. **Missed updates** — for each `uncited-backlink`, read the source page's notes on that
   entity/concept and check whether the target page reflects them.
4. **Missing pages** — wanted pages referenced by 2+ pages; important terms that recur in
   plain text across pages; entities that only exist inside a source page.
5. **Missing cross-references** — the script's unlinked mentions, plus related pages that
   should point at each other (same topic, no link either way).
6. **Near-duplicates** — two pages for the same thing under different names (check
   index.md and qmd results for similar titles). Propose a merge.
7. **Thin or stale pages** — stubs that sources could flesh out; pages whose `updated` is
   much older than the newest related source.
8. **Overview drift** — does `overview.md` still describe the wiki's current thesis and
   open questions?
9. **Data gaps** — open-question callouts, `gaps:` lines from `query` log entries, and
   questions the wiki can't answer. For each, name the kind of source that would fill it
   (and a web search query, if useful).
10. **Schema drift** — pages repeatedly breaking an AGENTS.md convention may mean the
    convention should change; suggest it rather than mass-editing.

Never resolve a contradiction by picking a side without evidence: cite the sources, and
when it's a judgment call, ask.

## 3. Report

Write the report to `outputs/lint/YYYY-MM-DD.md` (pass `--out` to the script for the
structural half, then append your semantic findings) and give the user a short summary,
grouped as:

- **Safe fixes** (mechanical, no judgment): missing index lines, typo links with a clear
  match, frontmatter repairs, adding links for unlinked mentions (first mention per page),
  `uncited-backlink` where the source plainly supports adding the citation.
- **Needs your call**: contradictions, superseded claims, merges/renames, new pages,
  deletions, overview rewrite, schema changes.
- **Suggestions**: questions worth asking, sources to look for, pages worth expanding.

## 4. Fix

- **Supervised** (default): ask which groups to apply ("safe fixes all / pick / none", then
  each judgment item). **Autonomous**: apply safe fixes, then ask only about judgment items.
- Rules while fixing:
  - New or expanded pages may only use information already in the wiki's sources (read
    the source pages / raw files). Anything that needs new information becomes a "sources
    to find" suggestion — or, if the user wants, fetch it into raw/ and run `wiki-ingest`.
  - Merge = move content into the surviving page, update every link to the old slug
    (`qmd search "<old-slug>"` and grep for `[[old-slug`), delete the old page only after
    the user confirms, update index.md.
  - Bump `updated` on every page you change; keep `sources:` in sync with citations.
  - Never edit raw/. A changed raw file is handled by re-ingesting it.
- Re-run `lint.py` to confirm the fixed checks are clear; `qmd update` (and `qmd embed`).

## 5. Log and commit

```markdown
## [YYYY-MM-DD] lint | <scope: recent|full|topic>
- report: outputs/lint/YYYY-MM-DD.md
- found: <n> errors, <n> warnings; <n> contradictions, <n> gaps
- fixed: <what was applied>
- open: <what's waiting on the user / sources to find>
```

Commit if `auto_commit: true`:
`git -C <root> add -A -- . && git -C <root> commit -q -m "lint: <scope> — <n> fixes" -- .`

## Tips

- Lint after every ~5–10 ingests, or when the script shows overview drift.
- `lint.py --strict` exits non-zero on errors, so it can run as a git pre-commit hook.
- Big wiki: lint by type or folder per session (`entities/` today, `concepts/` next time)
  rather than everything at once.
