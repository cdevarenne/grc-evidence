"""The base of every error the engine raises on bad input or a failed tool, which `grc` prints without a traceback."""


class GrcError(Exception):
    """A problem the person running `grc` can fix: bad config, bundle, or contract file, or a failed scanner or model call."""
