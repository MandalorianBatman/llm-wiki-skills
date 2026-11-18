---
name: wiki-setup
description: Create (or repair) a persistent, LLM-maintained markdown wiki following Karpathy's llm-wiki pattern — raw/ sources, an agent-owned wiki/ of cross-linked pages, an AGENTS.md schema, index.md, log.md, and qmd search collections. Use when the user wants to start a knowledge base, research wiki, second brain or "LLM wiki", set one up for a new topic, adopt an existing notes folder, tailor the wiki's schema, or re-register a cloned wiki with qmd on a new machine.
---

# wiki-setup

Scaffold a wiki the other skills (`wiki-ingest`, `wiki-query`, `wiki-lint`) can work on,
then tailor its schema to the user's domain. The layout is the contract between the
skills; the schema (`AGENTS.md`) is where this particular wiki's conventions live.

```
<root>/
├── AGENTS.md  CLAUDE.md (@AGENTS.md)  .llm-wiki.yml  log.md  .gitignore
├── raw/            immutable sources (+ raw/assets/)
├── wiki/           index.md  overview.md  sources/  entities/  concepts/  analyses/
└── outputs/        generated slides, charts, canvases, lint reports
```

## 1. Check prerequisites

Run `python3 --version`, `git --version`, `qmd --version`. qmd is expected; if it is
missing, continue with `--no-qmd` and tell the user to `npm install -g @tobilu/qmd` and
re-run setup later (setup is idempotent).

If the target folder already has `.llm-wiki.yml`, this is a **repair**: skip the interview,
run the script (step 3) to recreate missing files and re-register qmd collections, then
report what changed. This is also the step to run after cloning a wiki onto a new machine,
because qmd collections are machine-local.

## 2. Interview (short)

Ask in one message, offering a default for each so the user can just say "defaults":

1. **Location** — default `./<name>` (or the current folder if it's empty).
2. **Name** — short slug, used for qmd collection names (`<name>-wiki`, `<name>-raw`).
3. **Purpose & scope** — what the wiki is for, what's out of scope, what questions it
   should answer. One paragraph is plenty.
4. **Sources** — what will go in raw/ (papers, articles, transcripts, book chapters, journal
   entries, Slack exports…). This shapes page types.
5. **Page types** — propose a set fitted to the domain instead of asking open-ended.
   Defaults are `source / entity / concept / analysis`. Examples:
   - research topic: defaults, maybe `entity.kind` = person | lab | model | dataset
   - book companion: `source` (chapters), `character`, `place`, `theme`, `analysis`
   - personal health / self-tracking: `source` (logs, articles), `metric`, `intervention`,
     `concept`, `analysis`
   - company / team wiki: `source` (meetings, docs), `person`, `project`, `decision`,
     `concept`, `analysis`
6. **Embed now?** — `qmd embed` downloads local models (~hundreds of MB) the first time
   and is slow on CPU. BM25 search works without it. Default: no, run later.

If the user already gave these details, don't re-ask. In autonomous mode, take defaults
and state them.

If the target folder already contains the user's markdown notes, ask before touching
them: either leave them where they are and create the wiki next to them, or treat them as
raw sources (the user moves or copies them into `raw/`). Never move user files yourself
without a yes.

## 3. Scaffold

```bash
python3 <this-skill-dir>/scripts/init_wiki.py <root> \
  --name <slug> --title "<Title>" --domain "<purpose paragraph>" \
  --mode supervised            # or autonomous
  # optional: --embed  --no-git  --no-qmd
```

The script creates missing dirs/files from `templates/`, never overwrites existing ones,
initialises git (staging only the wiki folder), registers the two qmd collections with
contexts (`qmd collection add … --mask "**/*.md"`, `qmd context add …`) and runs
`qmd update`. Read its output; fix any `[error]`/`[warn]` lines before moving on.

## 4. Tailor the schema

Edit `<root>/AGENTS.md` with what you learned — this is the important part:

- **Purpose**: replace the placeholder with the user's purpose and scope.
- **Page types**: if the domain needs different types, for each new type create
  `wiki/<folder>/`, add `type=folder` to `types:` in `.llm-wiki.yml`, add a subsection
  under "Page types" (frontmatter + body skeleton), and add a `## <Type>` section to
  `wiki/index.md`. Remove default types the user doesn't want the same way. Keep `source`.
- **Domain rules**: write down any preferences the user stated (what deserves a page,
  how to treat secondary sources, units, naming of people, etc.).
- **Tag vocabulary**: seed 5–10 tags if the domain suggests them.
- Mirror the purpose into the "Scope" section of `wiki/overview.md`.

Show the user a short summary of the schema decisions (not the whole file) and adjust
if they push back. Append a `schema` entry to `log.md` if you changed anything beyond the
Purpose paragraph.

## 5. Obsidian and capture tips (tell the user once)

- Open `<root>` as an Obsidian vault. Settings → Files & links: "Use [[Wikilinks]]" on,
  "New link format" = shortest path, "Default location for new attachments" =
  `raw/assets`. Bind a hotkey to "Download attachments for current file" to pull a clipped
  article's images local.
- Obsidian Web Clipper: save clips straight into `raw/`.
- Graph view shows hubs and orphans; Dataview can query the frontmatter; Marp renders
  decks from `outputs/slides/`.
- Optional: expose qmd to the agent as MCP (`qmd mcp`) — the skills use the CLI either way.

## 6. Verify and hand off

- `ls -R <root> | head -40` and `qmd collection list` look right.
- `qmd search "overview" -c <name>-wiki -n 1` returns the overview page.
- If `auto_commit: true` and you edited the schema, commit:
  `git -C <root> add -A -- . && git -C <root> commit -m "schema: tailor for <domain>" -- .`

Finish with: where the wiki is, the qmd collection names, the mode, and the next step —
"drop a source into `raw/` (or give me a URL/file) and ask me to ingest it."

## Notes

- Never put the wiki's own content into raw/ or vice versa; raw is the user's, wiki is yours.
- One wiki per root. Several wikis can coexist; their qmd collections are prefixed by name.
- Keep the top-level folder names (`raw/`, `wiki/`, `outputs/`); type folders inside
  `wiki/` are free to change via `types:`.
- If the wiki folder moves, qmd still points at the old path: run
  `qmd collection remove <name>-wiki && qmd collection remove <name>-raw`, then re-run the
  script (and `qmd embed`).
