# llm-wiki skills

Four agent skills that turn Karpathy's [LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
idea into a repeatable workflow: the agent incrementally compiles your sources into a
persistent, cross-linked markdown wiki instead of re-deriving answers from raw documents
every time.

| Skill | What it does | Writes |
|-------|--------------|--------|
| `wiki-setup`  | Scaffold or repair a wiki, register qmd collections, tailor the `AGENTS.md` schema to your domain | everything (first run), schema |
| `wiki-ingest` | Read a source, discuss takeaways, write a source page, update entity/concept pages with citations, flag contradictions, update index + log, re-index | `wiki/`, `log.md`, new files in `raw/` only when fetching/converting |
| `wiki-query`  | Answer from the wiki with `[[citations]]`; tables, Marp decks, charts, canvases; file good answers back as analysis pages | `outputs/`, optionally `wiki/analyses/`, `log.md` |
| `wiki-lint`   | Script for mechanical checks + judgment pass for contradictions, superseded claims, gaps; fixes with your go-ahead | `outputs/lint/`, fixes in `wiki/`, `log.md` |

Each skill works on its own. They share a **contract**, not code: the folder layout,
`.llm-wiki.yml`, and the wiki's own `AGENTS.md` schema (which wins over skill defaults).
Any wiki laid out this way works with any subset of the skills.

## Requirements

- An agent that supports `SKILL.md` skills and has a shell (Claude Code, Codex, OpenCode…)
- `python3` (scripts use the standard library only), `git`
- [qmd](https://github.com/tobi/qmd): `npm install -g @tobilu/qmd`
- Optional: Obsidian (+ Web Clipper, Dataview, Marp plugins)

## Install

Copy the four folders into your agent's skills directory:

```bash
# Claude Code, all projects
cp -r wiki-setup wiki-ingest wiki-query wiki-lint ~/.claude/skills/
# Claude Code, one project
cp -r wiki-* <project>/.claude/skills/
# Other agents: their skills dir, e.g. ~/.agents/skills/
```

Recommended alongside: qmd's own skill, `qmd skill install --global`.

## Use

```
"Set up an LLM wiki in ~/wikis/ml for my transformer research"     → wiki-setup
"Ingest raw/2026-11-18-attention.md"  /  "ingest https://…"        → wiki-ingest
"Ingest everything new"                                            → wiki-ingest (batch)
"What does the wiki say about KV-cache compression vs. MQA?"       → wiki-query
"Make that a Marp deck"  /  "file that answer"                     → wiki-query
"Lint the wiki"  /  "full lint"                                    → wiki-lint
```

Default mode is **supervised**: ingest shows takeaways and a page plan before writing,
lint asks before fixing, query offers to file answers. Set `mode: autonomous` in
`.llm-wiki.yml`, or say "just do it" for one run.

## The wiki it creates

```
<root>/
├── AGENTS.md        schema: purpose, page types, conventions (CLAUDE.md imports it)
├── .llm-wiki.yml    config: types→folders, qmd collections, mode, auto_commit
├── log.md           append-only: ## [YYYY-MM-DD] ingest | Title
├── raw/             your immutable sources (+ raw/assets/ for images)
├── wiki/            index.md, overview.md, sources/, entities/, concepts/, analyses/
└── outputs/         slides, charts, canvases, lint reports (not indexed)
```

Conventions (all editable in `AGENTS.md`):

- Obsidian `[[wikilinks]]`; kebab-case basenames, unique across the vault.
- Source pages are named like citations — `vaswani-2017-attention` — so
  `([[vaswani-2017-attention]])` after a claim reads as a reference.
- Contradictions are kept and flagged with `> [!warning] Contradiction`, never overwritten.
- Red links (`[[page-that-doesnt-exist-yet]]`) are allowed; lint ranks them as wanted pages.
- Raw files are tracked by `raw:` + `source_hash:` on source pages, so lint/ingest know
  what's pending and what changed since ingest.
- qmd collections `<name>-wiki` and `<name>-raw`, with per-folder contexts.

## Scripts

```bash
python3 wiki-setup/scripts/init_wiki.py <root> --name ml --title "ML Research" --domain "…" [--embed]
python3 wiki-ingest/scripts/pending.py [--root DIR] [--all] [--json]   # what's not ingested yet
python3 wiki-ingest/scripts/pending.py --hash raw/file.md              # source_hash for frontmatter
python3 wiki-lint/scripts/lint.py [--root DIR] [--json] [--out FILE] [--strict]
```

All find the wiki root by walking up from the current directory to `.llm-wiki.yml`.
`lint.py --strict` exits non-zero on errors, so it can be a pre-commit hook.

## Notes

- qmd collections are machine-local. After cloning a wiki elsewhere (or moving it), run
  `wiki-setup` again on the folder: it repairs missing pieces and re-registers qmd.
- `qmd embed` downloads local models on first run and is slow on CPU; BM25 (`qmd search`)
  works without it, and the skills fall back to it.
- Git commits are scoped to the wiki folder (`git add -A -- .`), so a wiki inside a bigger
  repo won't sweep up unrelated changes.
