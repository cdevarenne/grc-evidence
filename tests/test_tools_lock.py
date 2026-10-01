import re
from pathlib import Path

LOCK = Path(__file__).parent.parent / "src" / "okf_grc" / "data" / "tools.lock"
REQUIRED = {
    "SEMGREP_VERSION", "SEMGREP_PYTHON", "CHECKOV_VERSION", "CHECKOV_PYTHON", "TRIVY_VERSION",
    "CONFTEST_VERSION", "OKF_COMMIT", "OSCAL_VERSION",
}
SHA256 = {
    "TRIVY_SHA256_DARWIN_ARM64", "TRIVY_SHA256_LINUX_X86_64",
    "CONFTEST_SHA256_DARWIN_ARM64", "CONFTEST_SHA256_LINUX_X86_64",
}


def _pins() -> dict[str, str]:
    lines = [ln for ln in LOCK.read_text().splitlines() if ln and not ln.startswith("#")]
    return dict(ln.split("=", 1) for ln in lines)


def test_all_pins_present() -> None:
    assert set(_pins()) == REQUIRED | SHA256


def test_pins_are_exact() -> None:
    pins = _pins()
    assert re.fullmatch(r"[0-9a-f]{40}", pins["OKF_COMMIT"])
    for key in REQUIRED - {"OKF_COMMIT"}:
        assert re.fullmatch(r"\d+\.\d+(\.\d+)?", pins[key]), key


def test_release_assets_are_pinned_by_sha256() -> None:
    pins = _pins()
    for key in SHA256:
        assert re.fullmatch(r"[0-9a-f]{64}", pins[key]), key


LOCKS = LOCK.parent / "locks"
BOOTSTRAP = LOCK.parent / "bootstrap.sh"
PYTHON_SCANNERS = {"semgrep": ("SEMGREP_VERSION", "SEMGREP_PYTHON"), "checkov": ("CHECKOV_VERSION", "CHECKOV_PYTHON")}


def _requirements(name: str) -> list[str]:
    """One entry per package: its pin line plus its --hash lines."""
    text = (LOCKS / name / "requirements.txt").read_text()
    return [block for block in re.split(r"\n(?=\S)", text) if block and not block.startswith("#")]


def test_python_scanners_are_locked_at_the_pinned_version_and_python() -> None:
    pins = _pins()
    for name, (version, python) in PYTHON_SCANNERS.items():
        assert any(block.startswith(f"{name}=={pins[version]} ") for block in _requirements(name)), name
        assert f"--python-version {pins[python]} " in (LOCKS / name / "requirements.txt").read_text(), name


def test_every_locked_package_is_pinned_and_hashed() -> None:
    for name in PYTHON_SCANNERS:
        for block in _requirements(name):
            assert re.match(r"[A-Za-z0-9_.-]+==\S+", block), block.splitlines()[0]
            assert re.search(r"--hash=sha256:[0-9a-f]{64}", block), block.splitlines()[0]


def test_bootstrap_installs_python_scanners_only_with_hash_checking() -> None:
    script = "\n".join(ln for ln in BOOTSTRAP.read_text().splitlines() if not ln.lstrip().startswith("#"))
    assert "--require-hashes" in script and "uv tool install" not in script
    assert "install_locked semgrep" in script and "install_locked checkov" in script
