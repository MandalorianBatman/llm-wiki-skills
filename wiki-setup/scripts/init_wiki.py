#!/usr/bin/env python3
"""Scaffold (or repair) an LLM wiki in the Karpathy llm-wiki layout.

Idempotent: existing files are never overwritten, missing pieces are created, and qmd
collections are registered if absent. Safe to re-run on a new machine after cloning.

Usage:
  init_wiki.py <root> [--name slug] [--title "Title"] [--domain "purpose text"]
               [--mode supervised|autonomous] [--no-git] [--no-qmd] [--embed]
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATES = HERE.parent / "templates"

DIRS = [
    "raw",
    "raw/assets",
    "wiki/sources",
    "wiki/entities",
    "wiki/concepts",
    "wiki/analyses",
    "outputs",
]
KEEP = ["raw/assets", "wiki/sources", "wiki/entities", "wiki/concepts", "wiki/analyses", "outputs"]

# template file -> destination (relative to root)
FILES = {
    "AGENTS.md": "AGENTS.md",
    "CLAUDE.md": "CLAUDE.md",
    "llm-wiki.yml": ".llm-wiki.yml",
    "gitignore": ".gitignore",
    "log.md": "log.md",
    "index.md": "wiki/index.md",
    "overview.md": "wiki/overview.md",
}

QMD_CONTEXTS = {
    "": "LLM-maintained wiki ({title}). Compiled, cross-linked pages; read index.md first.",
    "sources": "Source summary pages: one per ingested raw source, with provenance frontmatter.",
    "entities": "Entity pages: people, organisations, products, places, works. Cited synthesis.",
    "concepts": "Concept pages: ideas, methods, themes, debates. Cited synthesis.",
    "analyses": "Filed query answers, comparisons and deep dives.",
}


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "wiki"


def read_flat_yaml(path: Path) -> dict[str, str]:
    cfg: dict[str, str] = {}
    if not path.exists():
        return cfg
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split(" #", 1)[0].rstrip()
        if not line or line.lstrip().startswith("#") or ":" not in line:
            continue
        k, v = line.split(":", 1)
        cfg[k.strip()] = v.strip().strip('"').strip("'")
    return cfg


def run(cmd: list[str], cwd: Path | None = None, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=check)


def say(kind: str, msg: str) -> None:
    print(f"[{kind}] {msg}")


def render(text: str, subs: dict[str, str]) -> str:
    for k, v in subs.items():
        text = text.replace("{{" + k + "}}", v)
    return text


def setup_git(root: Path, created_any: bool) -> None:
    if not shutil.which("git"):
        say("skip", "git not found — wiki is not versioned")
        return
    inside = run(["git", "rev-parse", "--is-inside-work-tree"], cwd=root)
    if inside.returncode != 0:
        run(["git", "init", "-q"], cwd=root, check=True)
        say("git", "initialised repository")
    if not created_any:
        return
    # Stage only this folder: the wiki may live inside a larger repo.
    run(["git", "add", "-A", "--", "."], cwd=root)
    c = run(["git", "commit", "-q", "-m", "setup: scaffold llm wiki", "--", "."], cwd=root)
    if c.returncode == 0:
        say("git", "committed scaffold")
    else:
        say("warn", "git commit failed (set user.name/user.email?): " + (c.stderr.strip() or c.stdout.strip())[:200])


def qmd_collection_path(name: str) -> str | None:
    r = run(["qmd", "collection", "show", name])
    if r.returncode != 0:
        return None
    m = re.search(r"^\s*Path:\s*(.+)$", r.stdout, re.M)
    return m.group(1).strip() if m else ""


def setup_qmd(root: Path, cfg: dict[str, str], title: str, embed: bool) -> None:
    if not shutil.which("qmd"):
        say("skip", "qmd not on PATH — install with `npm install -g @tobilu/qmd`, then re-run setup")
        return
    wiki_dir = (root / cfg.get("wiki_dir", "wiki")).resolve()
    raw_dir = (root / cfg.get("raw_dir", "raw")).resolve()
    pairs = [(cfg["qmd_wiki_collection"], wiki_dir), (cfg["qmd_raw_collection"], raw_dir)]
    for name, path in pairs:
        existing = qmd_collection_path(name)
        if existing is None:
            r = run(["qmd", "collection", "add", str(path), "--name", name, "--mask", "**/*.md"])
            if r.returncode == 0:
                say("qmd", f"added collection {name} -> {path}")
            else:
                say("error", f"qmd collection add {name} failed: {(r.stderr or r.stdout).strip()[:300]}")
                continue
        elif existing and Path(existing).resolve() != path:
            say("warn", f"collection {name} points at {existing}, not {path}. Fix with: "
                        f"qmd collection remove {name} && re-run this script")
            continue
        else:
            say("ok", f"collection {name} already registered")

    wc = cfg["qmd_wiki_collection"]
    for sub, text in QMD_CONTEXTS.items():
        target = f"qmd://{wc}/{sub}" if sub else f"qmd://{wc}"
        run(["qmd", "context", "add", target, text.format(title=title)])
    run(["qmd", "context", "add", f"qmd://{cfg['qmd_raw_collection']}",
         f"Raw, immutable source documents for the {title} wiki. Prefer the wiki pages; "
         "use these to verify claims or recover detail."])
    say("qmd", "contexts set")

    r = run(["qmd", "update"])
    say("qmd", "index updated" if r.returncode == 0 else f"qmd update failed: {r.stderr.strip()[:200]}")
    if embed:
        say("qmd", "embedding (first run downloads local models; can take a while on CPU)…")
        r = subprocess.run(["qmd", "embed"])
        say("qmd", "embeddings done" if r.returncode == 0 else "qmd embed failed — BM25 search still works")
    else:
        say("next", "run `qmd embed` when convenient to enable vector search (BM25 works now)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--name", help="short slug, used for qmd collection names (default: folder name)")
    ap.add_argument("--title", help="human title (default: from name)")
    ap.add_argument("--domain", default="", help="one-paragraph purpose / scope for AGENTS.md")
    ap.add_argument("--mode", choices=["supervised", "autonomous"], default="supervised")
    ap.add_argument("--no-git", action="store_true")
    ap.add_argument("--no-qmd", action="store_true")
    ap.add_argument("--embed", action="store_true", help="run `qmd embed` now")
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    cfg_path = root / ".llm-wiki.yml"
    existing_cfg = read_flat_yaml(cfg_path)

    name = slugify(args.name or existing_cfg.get("name") or root.name)
    title = args.title or existing_cfg.get("title") or name.replace("-", " ").title()
    today = dt.date.today().isoformat()
    domain = args.domain.strip() or "TODO: describe what this wiki is for, its scope, and the questions it should answer."
    subs = {
        "NAME": name,
        "TITLE": title,
        "DOMAIN": domain,
        "DATE": today,
        "MODE": existing_cfg.get("mode", args.mode),
        "WIKI_COLLECTION": existing_cfg.get("qmd_wiki_collection", f"{name}-wiki"),
        "RAW_COLLECTION": existing_cfg.get("qmd_raw_collection", f"{name}-raw"),
    }

    say("root", str(root))
    if existing_cfg:
        say("mode", "existing wiki found — repairing missing pieces only")

    created_any = False
    for d in DIRS:
        p = root / d
        if not p.exists():
            p.mkdir(parents=True)
            created_any = True
    for d in KEEP:
        keep = root / d / ".gitkeep"
        if not any((root / d).iterdir()):
            keep.touch()

    for tpl, dest in FILES.items():
        dst = root / dest
        if dst.exists():
            say("skip", f"{dest} exists")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(render((TEMPLATES / tpl).read_text(encoding="utf-8"), subs), encoding="utf-8")
        say("create", dest)
        created_any = True

    cfg = read_flat_yaml(cfg_path)

    if not args.no_git:
        setup_git(root, created_any)
    if not args.no_qmd:
        setup_qmd(root, cfg, title, args.embed)

    print()
    print(f"Wiki '{title}' ready at {root}")
    print(f"  qmd collections: {cfg.get('qmd_wiki_collection')} (wiki/), {cfg.get('qmd_raw_collection')} (raw/)")
    print("  next: tailor AGENTS.md (Purpose, page types, domain rules), then drop a source in raw/ and ingest it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
