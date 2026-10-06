"""Names for people in outputs (Spec H §5.4): the GitHub login, or a pseudonym when outputs are republished.

A pseudonym is `p-` plus the first 10 hex characters of HMAC-SHA256(salt, login). The salt comes from the
environment and is never written to an output, so a pseudonym cannot be reversed without it.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from collections.abc import Mapping

from grc_evidence.config import Config, ConfigError

GHOST = "ghost"  # a missing login, and GitHub's placeholder for a deleted account: not a person


def pseudonym(login: str, salt: bytes) -> str:
    """The pseudonym of `login`; GitHub logins do not depend on case."""
    return "p-" + hmac.new(salt, login.lower().encode(), hashlib.sha256).hexdigest()[:10]


class Namer:
    """Names logins in `real` or `pseudonymous` mode."""

    def __init__(self, mode: str, salt: bytes | None) -> None:
        if mode == "pseudonymous" and not salt:
            raise ValueError("pseudonymous mode needs a salt")
        self._mode, self._salt = mode, salt

    def __repr__(self) -> str:
        return f"Namer({self._mode!r})"

    def name(self, login: str | None) -> str:
        if login is None or login == GHOST:
            return GHOST
        if self._mode == "pseudonymous" and self._salt:
            return pseudonym(login, self._salt)
        return login


def namer_from_config(config: Config, environ: Mapping[str, str] = os.environ) -> Namer:
    """The namer `grc.yaml` asks for; pseudonymous mode stops when the salt variable is unset or empty."""
    if config.people != "pseudonymous":
        return Namer("real", None)
    if not (salt := environ.get(config.people_salt_env)):
        raise ConfigError(f"people: pseudonymous needs {config.people_salt_env}")
    return Namer("pseudonymous", salt.encode())
