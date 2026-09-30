import re
from pathlib import Path

LOCK = Path(__file__).parent.parent / "src" / "okf_grc" / "data" / "tools.lock"
REQUIRED = {
    "SEMGREP_VERSION", "CHECKOV_VERSION", "CHECKOV_PYTHON", "TRIVY_VERSION",
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
