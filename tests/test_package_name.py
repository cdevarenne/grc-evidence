"""The package is grc-evidence (module grc_evidence); the okf_grc alias of 2.0 is gone since 2.1.0."""

import importlib.util
from importlib.metadata import version

from grc_evidence import to_oscal


def test_the_old_module_name_is_gone() -> None:
    assert importlib.util.find_spec("okf_grc") is None


def test_version_reads_new_name() -> None:
    assert version("grc-evidence") == "2.1.0"


def test_prop_ns() -> None:
    assert to_oscal.PROP_NS == "https://github.com/cdevarenne/grc-evidence/ns/oscal"
