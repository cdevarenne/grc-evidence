"""Files shipped with the engine: pinned tool versions, the scanner bootstrap, the base bundle, and the output schemas."""

from importlib.resources import files
from importlib.resources.abc import Traversable

# Version of the output contract (schemas/*.schema.json): additive changes bump the minor version.
SCHEMA_VERSION = "1.3"  # 1.1: run.json lists untracked scan inputs; mapping.json lists pending suppressions
# 1.2: tool `github` and its targets `github:<owner>/<name>[#n]`; run.json hashes the optional collect/ outputs
# 1.3: mapping.json pending_suppressions give a reason; a suppression not verified by a person is pending


def path(name: str) -> Traversable:
    """A packaged data file, e.g. `path("tools.lock")`."""
    return files(__name__) / name
