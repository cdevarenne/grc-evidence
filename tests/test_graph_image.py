"""The README's bundle picture (`make graph-image`): every concept, the engine's own links, colors by folder."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).parent.parent
spec = importlib.util.spec_from_file_location("graph_image", ROOT / "scripts" / "graph_image.py")
assert spec and spec.loader
graph_image = importlib.util.module_from_spec(spec)
spec.loader.exec_module(graph_image)

from grc_evidence.okf_lib import load_bundle  # noqa: E402


def test_every_concept_is_a_colored_box_and_no_index_is_a_node() -> None:
    bundle = load_bundle(ROOT / "knowledge")
    dot = graph_image.to_dot(bundle)
    assert dot.count("fillcolor=") == len(bundle.concepts)
    assert '"controls/cc8.1" [label="CC8.1 — Change Management", fillcolor="#2f74d0"]' in dot
    assert '"stack/index"' not in dot and "index?" not in dot
    edges = sum(1 for c in bundle.concepts.values() for t in c.links if t in bundle.concepts)
    assert dot.count(" -> ") == edges > 50


def test_folder_and_quotes() -> None:
    assert graph_image.folder("controls/iso42001/a.6") == "controls" and graph_image.folder("ai-inventory") == ""
    assert graph_image._quote('a "b"') == '"a \\"b\\""'
