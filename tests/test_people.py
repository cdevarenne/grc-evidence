"""Names for people in outputs: real logins, or pseudonyms p-<HMAC> when outputs are republished (Spec H §5.4)."""

import re
from dataclasses import replace

import pytest

from grc_evidence.config import Config, ConfigError
from grc_evidence.people import Namer, namer_from_config, pseudonym


def test_pseudonym_shape() -> None:
    p = pseudonym("octocat", b"s")
    assert re.fullmatch(r"p-[0-9a-f]{10}", p) and p == pseudonym("octocat", b"s")
    assert p != pseudonym("octocat", b"t")
    assert p == pseudonym("OctoCat", b"s")  # GitHub logins do not depend on case


def test_real_mode_identity() -> None:
    assert Namer("real", None).name("octocat") == "octocat"


def test_ghost() -> None:
    assert Namer("pseudonymous", b"s").name(None) == "ghost"
    assert Namer("real", None).name(None) == "ghost"
    assert Namer("pseudonymous", b"s").name("ghost") == "ghost"  # GitHub's placeholder for a deleted account


def test_pseudonymous_mode_names() -> None:
    assert Namer("pseudonymous", b"s").name("octocat") == pseudonym("octocat", b"s")


def test_missing_salt_raises() -> None:
    config = replace(Config(), people="pseudonymous", people_salt_env="DEMO_SALT")
    with pytest.raises(ConfigError, match="people: pseudonymous needs DEMO_SALT"):
        namer_from_config(config, {})
    with pytest.raises(ConfigError, match="DEMO_SALT"):
        namer_from_config(config, {"DEMO_SALT": ""})
    with pytest.raises(ValueError):
        Namer("pseudonymous", None)


def test_namer_from_config() -> None:
    assert namer_from_config(Config(), {}).name("octocat") == "octocat"
    config = replace(Config(), people="pseudonymous")
    assert namer_from_config(config, {"GRC_PEOPLE_SALT": "s"}).name("octocat") == pseudonym("octocat", b"s")


def test_salt_not_in_repr() -> None:
    assert "s3cret" not in repr(Namer("pseudonymous", b"s3cret"))
