"""Files shipped with the engine: pinned tool versions, the scanner bootstrap, the base bundle, and the output schemas."""

from importlib.resources import files
from importlib.resources.abc import Traversable

# Version of the output contract (schemas/*.schema.json): additive changes bump the minor version.
SCHEMA_VERSION = "1.1"  # 1.1: run.json lists untracked scan inputs; mapping.json lists pending suppressions


def path(name: str) -> Traversable:
    """A packaged data file, e.g. `path("tools.lock")`."""
    return files(__name__) / name
