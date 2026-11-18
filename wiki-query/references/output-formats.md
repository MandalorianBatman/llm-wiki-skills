# Output formats for wiki-query

All generated artifacts live under `outputs/` (not indexed, not part of the wiki). Name
files with the same slug you'd give an analysis page. Content comes only from wiki pages
you read; note the source pages in the artifact.

## Comparison table (in the answer)

Rows = items, columns = shared attributes. One cell, one fact. Put the citation in the
row's first cell or a final "Sources" column, not in every cell. If a cell is unknown in
the wiki, write "—" and mention the gap below the table.

## Marp slide deck → `outputs/slides/<slug>.md`

```markdown
---
marp: true
theme: default
paginate: true
title: <Deck title>
---

# <Deck title>
<one-line framing> · from the <wiki title> wiki, <date>

---

## <Slide headline that states the point>

- 3–5 bullets, each a claim, not a topic
- Cite inline: (vaswani-2017-attention)

<!-- speaker notes: longer explanation, page links -->

---

## Sources
- [[vaswani-2017-attention]] — …
```

One idea per slide; headline states the takeaway. Wikilinks don't render in Marp, so cite
slugs as plain text in slides and keep `[[links]]` in the Sources slide (useful in
Obsidian). Render with the Marp Obsidian plugin or `npx @marp-team/marp-cli <file> --pdf`.

## Chart → `outputs/charts/<slug>.py` + `<slug>.png`

Write the data inline in the script (with a comment naming the wiki page each value came
from) so the chart is reproducible, then run it from the wiki root:

```python
# Data from: [[model-x]], [[model-y]] (wiki pages), originally [[some-source-2025]]
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

labels = ["Model X", "Model Y"]
values = [71.2, 64.8]   # benchmark %, from [[model-x]] / [[model-y]]

fig, ax = plt.subplots(figsize=(7, 4))
ax.bar(labels, values)
ax.set_ylabel("Benchmark score (%)")
ax.set_title("Benchmark score by model")
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
fig.tight_layout()
fig.savefig("outputs/charts/<slug>.png", dpi=200)
```

Label axes with units, title states what's compared, no chart junk. Embed in an analysis
page with `![[<slug>.png]]` if filed (Obsidian finds it by name).

## Obsidian canvas → `outputs/canvas/<slug>.canvas`

JSON Canvas: `nodes` and `edges`. File nodes point at vault-relative paths.

```json
{
  "nodes": [
    {"id": "n1", "type": "file", "file": "wiki/concepts/self-attention.md", "x": 0, "y": 0, "width": 400, "height": 300},
    {"id": "n2", "type": "file", "file": "wiki/entities/transformer.md", "x": 520, "y": 0, "width": 400, "height": 300},
    {"id": "n3", "type": "text", "text": "**Key question**\nWhy does attention scale better than recurrence?", "x": 260, "y": 380, "width": 360, "height": 140}
  ],
  "edges": [
    {"id": "e1", "fromNode": "n1", "fromSide": "right", "toNode": "n2", "toSide": "left", "label": "core mechanism of"}
  ]
}
```

Lay nodes out on a grid (≈520 px apart horizontally, ≈380 vertically); label every edge
with the relationship; keep it under ~25 nodes. Validate with
`python3 -c "import json,sys; json.load(open(sys.argv[1]))" <file>`.

## Dataview (for the user to paste into a note)

When the user wants a live list rather than a one-off answer, give a Dataview query:

```dataview
TABLE kind, length(sources) AS "sources", updated
FROM "wiki/entities"
WHERE contains(tags, "lab")
SORT updated DESC
```
