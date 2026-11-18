#!/usr/bin/env python3
"""Deterministic health checks for an llm-wiki (Karpathy pattern).

Covers the mechanical half of linting so the agent can spend its judgment on the semantic
half (contradictions, superseded claims, gaps). Read-only: never modifies the wiki.

Usage:
  lint.py [--root DIR] [--json] [--out FILE] [--strict] [--max-mentions N]

Checks
  error  frontmatter      missing frontmatter / required keys / bad dates / unknown type
  error  type-folder      page's type doesn't match the folder it lives in
  error  duplicate-name   two notes share a basename (wikilinks become ambiguous)
  error  likely-typo      unresolved [[link]] that closely matches an existing page
  error  missing-raw      source page whose raw: file doesn't exist
  error  log-format       malformed "## [date] op | title" header in log.md
  warn   orphan           page with no inbound links from other content pages
  warn   not-in-index     page missing from index.md
  warn   index-dead-link  index.md links to a page that doesn't exist
  warn   unsourced        non-source page that cites no source page
  warn   uncited-backlink source page links to a page that doesn't cite it back (possible missed update)
  warn   pending-raw      raw file not yet ingested (or needs a markdown conversion)
  warn   changed-raw      raw file changed since ingest (source_hash mismatch)
  warn   overview-drift   N+ sources ingested since overview.md was last updated
  info   wanted-page      red link: [[target]] with no page yet, by number of referring pages
  info   unlinked-mention page mentions another page's title/alias without linking it
  info   stub             page body under 60 words
  info   open-question    > [!question] callouts (gap-analysis input)
  info   contradiction    > [!warning] Contradiction callouts (check they're still open)
  info   index-size       index.md is large enough to split
"""
from __future__ import annotations

import argparse
import datetime as dt
import difflib
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

VAULT_SKIP = {".git", ".obsidian", ".trash", ".qmd", "node_modules"}
SPECIAL_TYPES = {"index", "overview"}
REQUIRED = ("title", "type", "created", "updated")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
LOG_HDR = re.compile(r"^## \[(\d{4}-\d{2}-\d{2})\] (setup|ingest|query|lint|schema|note) \| .+$")
LINK_RE = re.compile(r"(!?)\[\[([^\[\]\n]+?)\]\]")
FENCE_RE = re.compile(r"(^|\n)(```|~~~).*?(\n\2[^\n]*|\Z)", re.S)
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
MDLINK_RE = re.compile(r"\[[^\]\n]*\]\([^)\n]*\)")
URL_RE = re.compile(r"https?://\S+")
CALLOUT_Q = re.compile(r"^>\s*\[!question\]", re.M | re.I)
CALLOUT_C = re.compile(r"^>\s*\[!warning\][^\n]*contradict", re.M | re.I)
STUB_WORDS = 60


# ---------------------------------------------------------------- helpers

def find_root(start: Path) -> Path | None:
    for d in [start, *start.parents]:
        if (d / ".llm-wiki.yml").is_file():
            return d
    return None


def read_flat_yaml(path: Path) -> dict[str, str]:
    cfg: dict[str, str] = {}
    if not path.exists():
        return cfg
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split(" #", 1)[0].rstrip()
        if not line or line.lstrip().startswith("#") or ":" not in line or line.startswith(" "):
            continue
        k, v = line.split(":", 1)
        cfg[k.strip()] = v.strip().strip('"').strip("'")
    return cfg


def _scalar(v: str):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    if v.startswith("[") and v.endswith("]") and not v.startswith("[["):
        inner = v[1:-1].strip()
        if not inner:
            return []
        return [_scalar(x) for x in re.findall(r'"[^"]*"|\'[^\']*\'|[^,]+', inner) if x.strip()]
    return v


def parse_frontmatter(text: str) -> tuple[dict | None, str, str]:
    """Returns (frontmatter or None, raw frontmatter text, body)."""
    if not text.startswith("---"):
        return None, "", text
    m = re.match(r"^---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(\r?\n|$)", text, re.S)
    if not m:
        return None, "", text
    fm: dict = {}
    key = None
    for line in m.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith((" ", "\t")):
            item = line.strip()
            if key and item.startswith("- "):
                if not isinstance(fm.get(key), list):
                    fm[key] = []
                fm[key].append(_scalar(item[2:]))
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            key = k.strip()
            fm[key] = _scalar(v) if v.strip() else ""
    return fm, m.group(1), text[m.end():]


def short_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def mask_code(text: str) -> str:
    text = FENCE_RE.sub(lambda m: m.group(1) + " " * (len(m.group(0)) - len(m.group(1))), text)
    return INLINE_CODE_RE.sub(lambda m: " " * len(m.group(0)), text)


def link_target(raw: str) -> str:
    t = raw.split("|", 1)[0]
    t = re.split(r"[#^]", t, maxsplit=1)[0]
    return t.strip()


def parse_date(v) -> dt.date | None:
    if isinstance(v, str) and DATE_RE.match(v.strip()):
        try:
            return dt.date.fromisoformat(v.strip())
        except ValueError:
            return None
    return None


def as_list(v) -> list:
    if v is None or v == "":
        return []
    return v if isinstance(v, list) else [v]


# ---------------------------------------------------------------- model

@dataclass
class Page:
    path: Path
    rel: str                 # root-relative posix path
    stem: str
    fm: dict | None
    fm_text: str
    body: str
    type: str = ""
    links: list[str] = field(default_factory=list)       # resolved rel paths (md pages + files)
    unresolved: list[str] = field(default_factory=list)  # raw targets

    @property
    def title(self) -> str:
        return str((self.fm or {}).get("title") or self.stem)


class Vault:
    def __init__(self, root: Path):
        self.root = root
        self.cfg = read_flat_yaml(root / ".llm-wiki.yml")
        self.wiki_dir = root / self.cfg.get("wiki_dir", "wiki")
        self.raw_dir = root / self.cfg.get("raw_dir", "raw")
        self.log_file = root / self.cfg.get("log_file", "log.md")
        self.types: dict[str, str] = {}
        for part in self.cfg.get("types", "source=sources, entity=entities, concept=concepts, analysis=analyses").split(","):
            if "=" in part:
                t, folder = part.split("=", 1)
                self.types[t.strip()] = folder.strip().strip("/")
        self.folder_type = {v: k for k, v in self.types.items()}

        # every file in the vault, for link resolution
        self.files: list[str] = []
        for f in root.rglob("*"):
            if f.is_file() and not any(p in VAULT_SKIP for p in f.relative_to(root).parts):
                self.files.append(f.relative_to(root).as_posix())
        self.by_name: dict[str, list[str]] = defaultdict(list)   # lowercased basename (md: stem) -> rels
        for rel in self.files:
            name = Path(rel).name
            key = name[:-3] if name.lower().endswith(".md") else name
            self.by_name[key.lower()].append(rel)
        self.file_set = {r.lower(): r for r in self.files}

        self.pages: dict[str, Page] = {}
        for f in sorted(self.wiki_dir.rglob("*.md")):
            if any(p in VAULT_SKIP for p in f.relative_to(root).parts):
                continue
            try:
                text = f.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            fm, fm_text, body = parse_frontmatter(text)
            rel = f.relative_to(root).as_posix()
            p = Page(f, rel, f.stem, fm, fm_text, body, type=str((fm or {}).get("type", "")))
            for _, target in LINK_RE.findall(mask_code(fm_text + "\n" + body)):
                t = link_target(target)
                if not t:
                    continue
                res = self.resolve(t)
                if res:
                    p.links.append(res)
                else:
                    p.unresolved.append(t)
            self.pages[rel] = p

    def resolve(self, t: str) -> str | None:
        t = t.strip().lstrip("/")
        low = t.lower()
        if "/" in t:
            for cand in (low, low + ".md"):
                if cand in self.file_set:
                    return self.file_set[cand]
            for rel in self.files:  # partial path, Obsidian-style
                r = rel.lower()
                if r.endswith("/" + low) or r.endswith("/" + low + ".md"):
                    return rel
            return None
        key = low[:-3] if low.endswith(".md") else low
        hits = self.by_name.get(key)
        if hits:
            md = [h for h in hits if h.lower().endswith(".md")] or hits
            wiki_prefix = self.wiki_dir.relative_to(self.root).as_posix() + "/"
            md.sort(key=lambda h: (not h.startswith(wiki_prefix), h.count("/"), h))
            return md[0]
        return None

    def content_pages(self) -> list[Page]:
        return [p for p in self.pages.values() if p.type not in SPECIAL_TYPES and p.stem not in ("index", "overview")]

    def is_index_page(self, p: Page) -> bool:
        return p.type == "index" or p.stem == "index" or p.rel.startswith(
            (self.wiki_dir / "indexes").relative_to(self.root).as_posix() + "/")


# ---------------------------------------------------------------- checks

def run_checks(v: Vault, max_mentions: int) -> dict:
    F: list[dict] = []

    def add(sev, check, msg, page=None, **extra):
        d = {"severity": sev, "check": check, "message": msg}
        if page:
            d["page"] = page
        d.update(extra)
        F.append(d)

    root = v.root
    wiki_rel = v.wiki_dir.relative_to(root).as_posix()
    known_types = set(v.types) | SPECIAL_TYPES

    # --- frontmatter / type-folder
    for p in v.pages.values():
        if p.fm is None:
            add("error", "frontmatter", "no YAML frontmatter", p.rel)
            continue
        missing = [k for k in REQUIRED if not p.fm.get(k)]
        if missing:
            add("error", "frontmatter", f"missing required keys: {', '.join(missing)}", p.rel)
        for k in ("created", "updated", "ingested", "published"):
            val = p.fm.get(k)
            if val and k != "published" and not parse_date(val):
                add("error", "frontmatter", f"{k} is not YYYY-MM-DD: {val!r}", p.rel)
        if p.type and p.type not in known_types:
            add("error", "frontmatter", f"unknown type '{p.type}' (known: {', '.join(sorted(known_types))})", p.rel)
        sub = Path(p.rel).relative_to(wiki_rel).parts
        folder = sub[0] if len(sub) > 1 else ""
        if folder != "indexes" and p.type in v.types and v.types[p.type] != folder:
            add("error", "type-folder", f"type '{p.type}' belongs in {wiki_rel}/{v.types[p.type]}/, "
                f"but the page is in {wiki_rel}/{folder + '/' if folder else ''}", p.rel)
        elif folder in v.folder_type and p.type and p.type not in v.types:
            add("error", "type-folder", f"lives in {folder}/ (type '{v.folder_type[folder]}') but type is '{p.type}'", p.rel)
        if p.type == "source":
            raw = p.fm.get("raw")
            if not raw:
                add("error", "frontmatter", "source page has no raw: path", p.rel)
            elif not (root / link_target(str(raw).strip("[]"))).exists():
                add("error", "missing-raw", f"raw file not found: {raw}", p.rel)

    # --- duplicate basenames (markdown, vault-wide)
    for key, rels in v.by_name.items():
        mds = [r for r in rels if r.lower().endswith(".md")]
        if len(mds) > 1:
            add("error", "duplicate-name", f"basename '{key}' used by: {', '.join(mds)}")

    # --- unresolved links: typos vs wanted pages
    wanted: dict[str, set[str]] = defaultdict(set)
    for p in v.pages.values():
        for t in p.unresolved:
            if v.is_index_page(p):
                add("warn", "index-dead-link", f"[[{t}]] in the index points to no page", p.rel, target=t)
            else:
                wanted[t].add(p.rel)
    page_keys = [k for k, rels in v.by_name.items() if any(r.lower().endswith(".md") for r in rels)]
    wanted_list = []
    for t, refs in wanted.items():
        base = Path(t).name.lower()
        base = base[:-3] if base.endswith(".md") else base
        close = difflib.get_close_matches(base, page_keys, n=1, cutoff=0.85)
        if close:
            for r in sorted(refs):
                add("error", "likely-typo", f"[[{t}]] doesn't resolve — did you mean [[{close[0]}]]?", r,
                    target=t, suggestion=close[0])
        else:
            wanted_list.append((t, sorted(refs)))
    wanted_list.sort(key=lambda x: (-len(x[1]), x[0]))
    for t, refs in wanted_list:
        add("info", "wanted-page", f"[[{t}]] has no page — referenced by {len(refs)} page(s)",
            target=t, refs=refs, count=len(refs))

    # --- inbound links / orphans / index coverage
    inbound: dict[str, set[str]] = defaultdict(set)
    index_linked: set[str] = set()
    for p in v.pages.values():
        for tgt in p.links:
            if tgt == p.rel:
                continue
            if v.is_index_page(p):
                index_linked.add(tgt)
            else:
                inbound[tgt].add(p.rel)
    for p in v.content_pages():
        if v.is_index_page(p):
            continue
        if not inbound.get(p.rel):
            add("warn", "orphan", "no inbound links from other pages" +
                (" (only listed in the index)" if p.rel in index_linked else ""), p.rel)
        if p.rel not in index_linked:
            add("warn", "not-in-index", "not linked from index.md", p.rel)

    # --- citations
    source_rels = {p.rel for p in v.pages.values() if p.type == "source"}
    for p in v.content_pages():
        if p.type == "source" or v.is_index_page(p):
            continue
        if not (set(p.links) & source_rels):
            add("warn", "unsourced", "cites no source page (inline or in sources:)", p.rel)
    for s in (v.pages[r] for r in source_rels):
        for tgt in set(s.links):
            t = v.pages.get(tgt)
            if not t or t.type in ("source",) or t.type in SPECIAL_TYPES:
                continue
            if s.rel not in t.links:
                add("warn", "uncited-backlink",
                    f"[[{s.stem}]] links here but this page doesn't cite it — may be missing what it says",
                    t.rel, source=s.rel)

    # --- stubs, callouts
    for p in v.content_pages():
        words = len(re.findall(r"\w+", re.sub(r"^#.*$", "", mask_code(p.body), flags=re.M)))
        if words < STUB_WORDS:
            add("info", "stub", f"only {words} words", p.rel, words=words)
    for p in v.pages.values():
        for m in CALLOUT_Q.finditer(p.body):
            line = p.body[m.start():].split("\n", 2)
            text = " ".join(l.lstrip("> ").strip() for l in line[:2])
            text = re.sub(r"^\[!question\][-+]?\s*", "", text, flags=re.I).strip()
            add("info", "open-question", text[:160], p.rel)
        n = len(CALLOUT_C.findall(p.body))
        if n:
            add("info", "contradiction", f"{n} contradiction callout(s) — still unresolved?", p.rel, count=n)

    # --- overview drift
    ov = next((p for p in v.pages.values() if p.type == "overview" or p.stem == "overview"), None)
    threshold = int(v.cfg.get("overview_drift_threshold", "5") or 5)
    if ov and ov.fm:
        ov_upd = parse_date(ov.fm.get("updated"))
        if ov_upd:
            newer = [p.rel for p in v.pages.values() if p.type == "source" and p.fm and
                     (parse_date(p.fm.get("ingested")) or parse_date(p.fm.get("created")) or dt.date.min) > ov_upd]
            if len(newer) >= threshold:
                add("warn", "overview-drift", f"{len(newer)} sources ingested since overview.md was updated ({ov_upd})",
                    ov.rel, sources=newer)

    # --- raw: pending / changed
    referenced: dict[str, str] = {}
    for p in v.pages.values():
        if p.type != "source" or not p.fm:
            continue
        for k in ("raw", "original"):
            val = p.fm.get(k)
            if val and isinstance(val, str):
                referenced[link_target(val.strip("[]")).lstrip("./")] = (p.fm.get("source_hash", "") if k == "raw" else "")
    converted = {}
    raw_files = []
    if v.raw_dir.is_dir():
        for f in sorted(v.raw_dir.rglob("*")):
            relr = f.relative_to(v.raw_dir).parts
            if not f.is_file() or f.name.startswith(".") or "assets" in relr[:-1] or any(x in VAULT_SKIP for x in relr):
                continue
            raw_files.append(f)
            if f.suffix.lower() == ".md":
                fm, _, _ = parse_frontmatter(f.read_text(encoding="utf-8", errors="replace"))
                src = (fm or {}).get("converted_from")
                if isinstance(src, str) and src:
                    cand = (root / src) if src.startswith(v.raw_dir.name + "/") else (f.parent / src)
                    converted[f.relative_to(root).as_posix()] = cand.resolve().relative_to(root.resolve()).as_posix() \
                        if cand.resolve().is_relative_to(root.resolve()) else ""
    for f in raw_files:
        r = f.relative_to(root).as_posix()
        if r in referenced:
            rec = referenced[r]
            if rec and rec != short_hash(f):
                add("warn", "changed-raw", f"{r} changed since ingest (re-ingest it)", None, raw=r)
            continue
        if f.suffix.lower() != ".md":
            sib = f.with_suffix(".md")
            if sib.exists() or r in converted.values():
                continue
            add("warn", "pending-raw", f"{r} not ingested — needs a markdown conversion first", None, raw=r)
            continue
        if converted.get(r) and converted[r] in referenced:
            continue
        add("warn", "pending-raw", f"{r} not ingested", None, raw=r)

    # --- log
    last = {}
    if v.log_file.exists():
        for i, line in enumerate(v.log_file.read_text(encoding="utf-8").splitlines(), 1):
            if line.startswith("## "):
                m = LOG_HDR.match(line)
                if not m:
                    add("error", "log-format", f"line {i}: {line[:80]!r} — expected '## [YYYY-MM-DD] op | title'",
                        v.log_file.relative_to(root).as_posix())
                else:
                    last[m.group(2)] = m.group(1)
    else:
        add("error", "log-format", "log.md not found")

    # --- index size
    idx = next((p for p in v.pages.values() if p.stem == "index" and p.type in ("index", "")), None)
    if idx:
        n = idx.body.count("\n")
        if n > 400:
            add("info", "index-size", f"index.md has {n} lines — consider splitting into wiki/indexes/<type>.md",
                idx.rel)

    # --- unlinked mentions
    names: dict[str, str] = {}
    for p in v.content_pages():
        cands = [p.title] + [str(a) for a in as_list((p.fm or {}).get("aliases"))]
        for c in cands:
            c = c.strip()
            if len(c) >= 4 and not c.isdigit():
                names.setdefault(c.lower(), p.rel)
    mentions = []
    if names:
        pattern = re.compile(r"(?<![\w-])(" + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
                             + r")(?![\w-])", re.I)
        for p in v.content_pages():
            text = mask_code(p.body)
            text = LINK_RE.sub(lambda m: " " * len(m.group(0)), text)
            text = MDLINK_RE.sub(lambda m: " " * len(m.group(0)), text)
            text = URL_RE.sub(lambda m: " " * len(m.group(0)), text)
            seen = set()
            linked = set(p.links)
            for m in pattern.finditer(text):
                tgt = names[m.group(1).lower()]
                if tgt == p.rel or tgt in linked or tgt in seen:
                    continue
                seen.add(tgt)
                mentions.append((p.rel, m.group(1), tgt))
    by_target = Counter(t for _, _, t in mentions)
    mentions.sort(key=lambda x: (-by_target[x[2]], x[0]))
    for page, text, tgt in mentions[:max_mentions]:
        add("info", "unlinked-mention", f"mentions '{text}' without linking [[{Path(tgt).stem}]]", page, target=tgt)
    if len(mentions) > max_mentions:
        add("info", "unlinked-mention", f"… {len(mentions) - max_mentions} more not shown (raise --max-mentions)")

    # --- changed since last lint (scope for the semantic pass)
    since = parse_date(last.get("lint", "")) if last.get("lint") else None
    changed = sorted(p.rel for p in v.pages.values()
                     if p.fm and since and (parse_date(p.fm.get("updated")) or dt.date.min) >= since) if since \
        else sorted(p.rel for p in v.content_pages())

    counts = Counter(p.type or "?" for p in v.pages.values())
    return {
        "root": str(root),
        "generated": dt.date.today().isoformat(),
        "stats": {
            "pages": len(v.pages),
            "by_type": dict(sorted(counts.items())),
            "raw_files": len(raw_files),
            "links": sum(len(p.links) for p in v.pages.values()),
            "last": last,
        },
        "summary": dict(Counter(f["severity"] for f in F)),
        "findings": F,
        "changed_since_last_lint": changed,
        "last_lint": last.get("lint"),
    }


# ---------------------------------------------------------------- report

def to_markdown(r: dict) -> str:
    out = []
    s = r["stats"]
    out.append(f"# Lint report — {r['generated']}\n")
    out.append(f"`{r['root']}` · {s['pages']} pages ({', '.join(f'{k} {n}' for k, n in s['by_type'].items())})"
               f" · {s['raw_files']} raw files · {s['links']} links")
    last = s["last"]
    if last:
        out.append("Last: " + ", ".join(f"{k} {d}" for k, d in sorted(last.items())))
    sm = r["summary"]
    out.append(f"\n**{sm.get('error', 0)} errors · {sm.get('warn', 0)} warnings · {sm.get('info', 0)} info**\n")
    order = {"error": 0, "warn": 1, "info": 2}
    groups: dict[tuple, list] = defaultdict(list)
    for f in r["findings"]:
        groups[(order[f["severity"]], f["severity"], f["check"])].append(f)
    for (_, sev, check), items in sorted(groups.items()):
        out.append(f"## {sev} · {check} ({len(items)})")
        for f in items[:60]:
            where = f"`{f['page']}` — " if f.get("page") else ""
            out.append(f"- {where}{f['message']}")
        if len(items) > 60:
            out.append(f"- … {len(items) - 60} more (use --json)")
        out.append("")
    scope = r["changed_since_last_lint"]
    label = f"since last lint ({r['last_lint']})" if r["last_lint"] else "(no previous lint — everything)"
    out.append(f"## Semantic-pass scope: {len(scope)} page(s) changed {label}")
    for p in scope[:40]:
        out.append(f"- `{p}`")
    if len(scope) > 40:
        out.append(f"- … {len(scope) - 40} more")
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root")
    ap.add_argument("--json", action="store_true", help="print JSON instead of markdown")
    ap.add_argument("--out", help="also write the markdown report to this file")
    ap.add_argument("--strict", action="store_true", help="exit 1 if any errors (for hooks/CI)")
    ap.add_argument("--max-mentions", type=int, default=40)
    args = ap.parse_args()

    root = Path(args.root).resolve() if args.root else find_root(Path.cwd().resolve())
    if not root or not (root / ".llm-wiki.yml").is_file():
        print("No .llm-wiki.yml found (pass --root or run wiki-setup first).", file=sys.stderr)
        return 2
    result = run_checks(Vault(root), args.max_mentions)
    md = to_markdown(result)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(md, encoding="utf-8")
    print(json.dumps(result, indent=2) if args.json else md)
    return 1 if args.strict and result["summary"].get("error") else 0


if __name__ == "__main__":
    sys.exit(main())
