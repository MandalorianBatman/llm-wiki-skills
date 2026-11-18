#!/usr/bin/env python3
"""List raw sources that still need ingesting (or changed since they were ingested).

Usage:
  pending.py [--root DIR] [--all] [--json]
  pending.py --hash FILE          # print the 12-char source_hash for a raw file

A raw file counts as ingested when some wiki page with `type: source` names it in its
`raw:` (or `original:`) frontmatter. A non-markdown file (PDF, HTML…) counts as covered
when its markdown conversion is ingested — either a sibling with the same stem, or a .md
whose frontmatter says `converted_from: <that file>`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

SKIP_DIRS = {"assets", ".obsidian", ".trash", ".git"}


# ---------- config / frontmatter helpers (kept dependency-free) ----------

def find_root(start: Path) -> Path | None:
    for d in [start, *start.parents]:
        if (d / ".llm-wiki.yml").is_file():
            return d
    return None


def read_flat_yaml(path: Path) -> dict[str, str]:
    cfg: dict[str, str] = {}
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
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        if not inner:
            return []
        return [_scalar(x) for x in re.findall(r'"[^"]*"|\'[^\']*\'|[^,]+', inner) if x.strip()]
    return v


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Minimal YAML frontmatter parser: scalars, inline lists, '- item' lists."""
    if not text.startswith("---"):
        return {}, text
    m = re.match(r"^---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(\r?\n|$)", text, re.S)
    if not m:
        return {}, text
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
    return fm, text[m.end():]


def short_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


# ---------- main logic ----------

def norm(root: Path, p: str) -> str:
    p = str(p).strip().strip("[]")  # tolerate "[[raw/x.md]]"
    p = p.split("|", 1)[0]
    return Path(p).as_posix().lstrip("./") if not Path(p).is_absolute() else Path(p).resolve().relative_to(root).as_posix()


def scan(root: Path) -> dict:
    cfg = read_flat_yaml(root / ".llm-wiki.yml")
    wiki_dir = root / cfg.get("wiki_dir", "wiki")
    raw_dir = root / cfg.get("raw_dir", "raw")

    referenced: dict[str, dict] = {}  # raw relpath -> {page, hash}
    for page in sorted(wiki_dir.rglob("*.md")):
        try:
            fm, _ = parse_frontmatter(page.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, OSError):
            continue
        if fm.get("type") != "source":
            continue
        rel_page = page.relative_to(root).as_posix()
        for key in ("raw", "original"):
            val = fm.get(key)
            if not val or isinstance(val, list):
                continue
            try:
                rp = norm(root, val)
            except ValueError:
                continue
            referenced[rp] = {"page": rel_page, "hash": fm.get("source_hash", "") if key == "raw" else ""}

    raw_files: list[Path] = []
    if raw_dir.is_dir():
        for f in sorted(raw_dir.rglob("*")):
            if not f.is_file() or f.name.startswith(".") or f.name == ".gitkeep":
                continue
            if any(part in SKIP_DIRS for part in f.relative_to(raw_dir).parts[:-1]):
                continue
            raw_files.append(f)

    rel = {f: f.relative_to(root).as_posix() for f in raw_files}
    converted_from: dict[str, str] = {}
    for f in raw_files:
        if f.suffix.lower() == ".md":
            try:
                fm, _ = parse_frontmatter(f.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, OSError):
                continue
            src = fm.get("converted_from")
            if src and isinstance(src, str):
                cand = (f.parent / src) if not src.startswith(raw_dir.name + "/") else (root / src)
                try:
                    converted_from[rel[f]] = cand.resolve().relative_to(root).as_posix()
                except ValueError:
                    pass

    pending, changed, ingested = [], [], []
    for f in raw_files:
        r = rel[f]
        if r in referenced:
            ref = referenced[r]
            cur = short_hash(f)
            entry = {"raw": r, "page": ref["page"], "hash": cur}
            if ref["hash"] and ref["hash"] != cur:
                entry["recorded_hash"] = ref["hash"]
                changed.append(entry)
            else:
                ingested.append(entry)
            continue
        # covered via its markdown conversion?
        if f.suffix.lower() != ".md":
            sib = f.with_suffix(".md")
            sib_rel = sib.relative_to(root).as_posix() if sib.exists() else None
            conv = [m for m, o in converted_from.items() if o == r]
            if (sib_rel and sib_rel in referenced) or any(c in referenced for c in conv):
                continue
            if sib_rel or conv:
                continue  # its .md conversion will be listed itself
            pending.append({"raw": r, "size": f.stat().st_size, "note": "non-markdown: convert to .md first"})
            continue
        orig = converted_from.get(r)
        if orig and orig in referenced:
            continue
        pending.append({"raw": r, "size": f.stat().st_size, "hash": short_hash(f)})

    missing = [{"page": v["page"], "raw": k} for k, v in referenced.items() if not (root / k).exists()]
    return {"root": str(root), "pending": pending, "changed": changed, "missing_raw": missing,
            "ingested": ingested}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root")
    ap.add_argument("--all", action="store_true", help="also list already-ingested sources")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--hash", metavar="FILE", help="print source_hash for FILE and exit")
    args = ap.parse_args()

    if args.hash:
        print(short_hash(Path(args.hash)))
        return 0

    root = Path(args.root).resolve() if args.root else find_root(Path.cwd().resolve())
    if not root or not (root / ".llm-wiki.yml").is_file():
        print("No .llm-wiki.yml found (pass --root or run wiki-setup first).", file=sys.stderr)
        return 2

    res = scan(root)
    if not args.all:
        res.pop("ingested")
    if args.json:
        print(json.dumps(res, indent=2))
        return 0

    print(f"wiki: {root}")
    print(f"pending: {len(res['pending'])}")
    for p in res["pending"]:
        extra = p.get("note") or f"{p['size']} bytes  hash {p['hash']}"
        print(f"  - {p['raw']}  ({extra})")
    if res["changed"]:
        print(f"changed since ingest: {len(res['changed'])}")
        for c in res["changed"]:
            print(f"  - {c['raw']}  -> {c['page']}  (recorded {c['recorded_hash']}, now {c['hash']})")
    if res["missing_raw"]:
        print(f"source pages whose raw file is missing: {len(res['missing_raw'])}")
        for m in res["missing_raw"]:
            print(f"  - {m['page']}  -> {m['raw']}")
    if args.all:
        print(f"ingested: {len(res['ingested'])}")
        for i in res["ingested"]:
            print(f"  - {i['raw']}  -> {i['page']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
