"""The README's picture of the knowledge bundle: Graphviz DOT, one box per concept, colored by folder.

`make graph-image` pipes it into Graphviz's `sfdp`. The links are the engine's own (no `index.md` targets).
The interactive view is `make render` (okflib view).
"""

from __future__ import annotations

import sys
from pathlib import Path

from grc_evidence.okf_lib import Bundle, load_bundle

# Folder colors, as in okflib view's legend where it has one: controls blue, policies orange, stack green.
COLORS = {
    "controls": "#2f74d0", "policies": "#e8663a", "stack": "#1aaf6c", "scanners": "#8e5bd0",
    "crosswalk": "#13a3a3", "suppressions": "#b07d10",
}
OTHER = "#7a8591"
# levels=0: sfdp's multilevel step fails an assertion on this graph (Graphviz 15.1.1, Multilevel.c:184).
GRAPH = 'graph [overlap=prism, splines=true, sep="+8", levels=0, fontname="Helvetica", bgcolor="white", dpi=110];'
NODE = 'node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=10, fontcolor="white", penwidth=0];'
EDGE = 'edge [color="#9aa5b1", arrowsize=0.6];'


def _quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def folder(concept_id: str) -> str:
    """The top-level folder of a concept id, or "" for a concept at the bundle root."""
    return concept_id.split("/", 1)[0] if "/" in concept_id else ""


def to_dot(bundle: Bundle) -> str:
    """The bundle as a DOT digraph, with a legend of the folders it uses."""
    lines = ["digraph okf {", f"  {GRAPH}", f"  {NODE}", f"  {EDGE}"]
    for cid, concept in sorted(bundle.concepts.items()):
        color = COLORS.get(folder(cid), OTHER)
        lines.append(f"  {_quote(cid)} [label={_quote(concept.title)}, fillcolor={_quote(color)}];")
    for cid, concept in sorted(bundle.concepts.items()):
        lines += [f"  {_quote(cid)} -> {_quote(target)};" for target in concept.links if target in bundle.concepts]
    used = sorted({folder(cid) for cid in bundle.concepts} & set(COLORS))
    legend = " | ".join(f'<font color="{COLORS[name]}">■</font> {name}' for name in used)
    legend += f' | <font color="{OTHER}">■</font> other'
    lines.append(f"  legend [shape=plaintext, style=\"\", fontsize=16, fontcolor=\"#333333\", label=<{legend}>];")
    lines.append("}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.stdout.write(to_dot(load_bundle(Path(sys.argv[1] if len(sys.argv) > 1 else "knowledge"))))
