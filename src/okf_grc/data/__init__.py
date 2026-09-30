"""Files shipped with the engine: pinned tool versions and the scanner bootstrap."""

from importlib.resources import files
from importlib.resources.abc import Traversable


def path(name: str) -> Traversable:
    """A packaged data file, e.g. `path("tools.lock")`."""
    return files(__name__) / name
