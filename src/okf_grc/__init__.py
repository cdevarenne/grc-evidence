"""Deprecated alias: the package is now grc-evidence and the module grc_evidence.

Importing okf_grc or okf_grc.<name> gives the grc_evidence module of the same name.
The alias stays for one minor release.
"""

import importlib
import importlib.abc
import importlib.machinery
import importlib.util
import sys
import warnings
from collections.abc import Sequence
from types import ModuleType

warnings.warn("okf_grc is renamed to grc_evidence; import grc_evidence instead", DeprecationWarning, stacklevel=2)


class _Alias(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Resolve okf_grc.<name> to the already importable grc_evidence.<name>."""

    def find_spec(
        self, fullname: str, path: Sequence[str] | None, target: ModuleType | None = None
    ) -> importlib.machinery.ModuleSpec | None:
        if not fullname.startswith("okf_grc."):
            return None
        return importlib.util.spec_from_loader(fullname, self)

    def create_module(self, spec: importlib.machinery.ModuleSpec) -> ModuleType:
        return importlib.import_module("grc_evidence" + spec.name.removeprefix("okf_grc"))

    def exec_module(self, module: ModuleType) -> None:
        pass  # the grc_evidence module is already executed


sys.meta_path.insert(0, _Alias())
