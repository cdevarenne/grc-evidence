"""The package is grc-evidence (module grc_evidence); okf_grc stays as a deprecated alias for one minor release."""

import importlib
import sys
from importlib.metadata import version

import pytest

from grc_evidence import to_oscal


def test_old_import_warns_and_aliases() -> None:
    for name in [m for m in sys.modules if m == "okf_grc" or m.startswith("okf_grc.")]:
        del sys.modules[name]
    with pytest.warns(DeprecationWarning, match="grc_evidence"):
        old = importlib.import_module("okf_grc.config")
    import grc_evidence.config as new

    assert old is new


def test_version_reads_new_name() -> None:
    assert version("grc-evidence") == "2.1.0"


def test_prop_ns() -> None:
    assert to_oscal.PROP_NS == "https://github.com/cdevarenne/grc-evidence/ns/oscal"
