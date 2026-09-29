import json
import sys
from pathlib import Path
from typing import Any

import pytest

from run_scan import (
    CONFTEST_PATTERNS,
    ScanError,
    conftest_inputs,
    dedupe,
    load_pins,
    normalize_checkov,
    normalize_conftest,
    normalize_semgrep,
    normalize_trivy,
    run_tool,
    scan,
    scanner_runs,
)

OUTPUT = Path(__file__).parent / "fixtures" / "scanner_output"


def _load(name: str) -> Any:
    return json.loads((OUTPUT / name).read_text())


def _keys(findings: list[dict]) -> list[tuple[str, str, str, str]]:
    return [(f["tool"], f["rule_id"], f["severity"], f["target"]) for f in findings]


def test_semgrep_strips_config_prefix_and_maps_severity() -> None:
    assert _keys(normalize_semgrep(_load("semgrep.json"), "app")) == [
        ("semgrep", "drf-allowany", "high", "app/widgets/views.py")
    ]


def test_trivy_config_misconfigurations() -> None:
    assert _keys(normalize_trivy(_load("trivy-config.json"), "app")) == [
        ("trivy", "DS-0002", "high", "app/Dockerfile"),
        ("trivy", "DS-0026", "low", "app/Dockerfile"),
        ("trivy", "KSV-0013", "medium", "app/k8s/deployment.yaml"),
    ]


def test_trivy_fs_vulnerabilities() -> None:
    (finding,) = normalize_trivy(_load("trivy-fs.json"), "app")
    assert (finding["rule_id"], finding["severity"], finding["target"]) == (
        "CVE-2023-31047",
        "critical",
        "app/requirements.txt",
    )
    assert finding["message"].startswith("Django 4.2.0: ")


def test_checkov_prefixes_target_and_marks_missing_severity_unknown() -> None:
    assert _keys(normalize_checkov(_load("checkov.json"), "app")) == [
        ("checkov", "CKV_GCP_28", "unknown", "app/infra/main.tf"),
        ("checkov", "CKV_K8S_14", "unknown", "app/k8s/deployment.yaml"),
        ("checkov", "CKV_DOCKER_2", "unknown", "app/Dockerfile"),
    ]


def test_checkov_accepts_single_framework_object() -> None:
    single = _load("checkov.json")[0]
    assert len(normalize_checkov(single, "app")) == 1


def test_checkov_missing_severity_key_normalizes_to_unknown() -> None:
    report = {
        "results": {
            "failed_checks": [
                {
                    "check_id": "CKV_GCP_28",
                    "check_name": "Ensure bucket is not public",
                    "file_path": "/infra/main.tf",
                    "resource": "google_storage_bucket_iam_member.public_read",
                }
            ]
        }
    }
    (finding,) = normalize_checkov(report, "app")
    assert finding["severity"] == "unknown"


def test_conftest_uses_namespace_as_rule_id_and_skips_successes() -> None:
    assert _keys(normalize_conftest(_load("conftest.json"), "app")) == [
        ("conftest", "deny_latest_tag", "high", "app/k8s/deployment.yaml")
    ]


def test_dedupe_collapses_identical_findings_only() -> None:
    a = {"tool": "trivy", "rule_id": "X", "target": "t", "severity": "low", "message": "container a", "tags": []}
    other_resource = {**a, "message": "container b"}
    other_tool = {**a, "tool": "checkov"}
    assert dedupe([a, dict(a), other_resource, other_tool]) == [a, other_resource, other_tool]


def test_conftest_inputs_require_a_file_to_check(tmp_path: Path) -> None:
    (tmp_path / "svc").mkdir()
    (tmp_path / "svc" / "main.py").write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(ScanError, match="conftest: no files under 'svc' match k8s/"):
        conftest_inputs(tmp_path, "svc")


def test_run_tool_missing_binary(tmp_path: Path) -> None:
    with pytest.raises(ScanError, match="not found"):
        run_tool("nope", ["definitely-not-a-scanner-binary"], tmp_path)


def test_run_tool_accepts_exit_1_with_json(tmp_path: Path) -> None:
    argv = [sys.executable, "-c", "import sys; print('[]'); sys.exit(1)"]
    assert run_tool("fake", argv, tmp_path) == []


def test_run_tool_rejects_crash(tmp_path: Path) -> None:
    argv = [sys.executable, "-c", "import sys; sys.stderr.write('boom'); sys.exit(2)"]
    with pytest.raises(ScanError, match="exit 2: boom"):
        run_tool("fake", argv, tmp_path)


def test_run_tool_decodes_utf8_regardless_of_locale(tmp_path: Path) -> None:
    argv = [
        sys.executable,
        "-c",
        "import json, sys; sys.stdout.buffer.write(json.dumps(['é']).encode('utf-8'))",
    ]
    assert run_tool("fake", argv, tmp_path) == ["é"]


def test_checkov_summary_without_results_yields_no_findings() -> None:
    bare = {"passed": 0, "failed": 0, "skipped": 0, "parsing_errors": 0, "resource_count": 0}
    assert normalize_checkov([bare, _load("checkov.json")[0]], "app") == normalize_checkov(_load("checkov.json")[0], "app")


def test_semgrep_errors_fail_the_scan() -> None:
    doc = {**_load("semgrep.json"), "errors": [{"message": "rule parse failure"}, {"message": "later"}]}
    with pytest.raises(ScanError, match="semgrep: .*rule parse failure"):
        normalize_semgrep(doc, "app")


@pytest.mark.parametrize("target", ["-rf", "../outside", "/etc", "app/../../x"])
def test_scan_rejects_targets_outside_the_repo(tmp_path: Path, target: str) -> None:
    with pytest.raises(ScanError, match="--target"):
        scan(tmp_path, target)


def test_scanner_runs_cover_every_tool_with_a_pin() -> None:
    runs = scanner_runs("app", ["app/k8s/deployment.yaml"])
    assert [r.tool for r in runs] == ["semgrep", "trivy", "trivy", "checkov", "conftest"]
    pins = load_pins(Path(__file__).parent.parent / "tools.lock")
    assert all(r.pin in pins for r in runs)
    assert runs[-1].argv[-1] == "app/k8s/deployment.yaml"
    assert [r.in_target for r in runs] == [False, False, False, True, False]


def test_conftest_patterns_include_the_ai_inventory() -> None:
    assert "ai-inventory.yaml" in CONFTEST_PATTERNS


def test_load_pins_skips_comments_and_blank_lines(tmp_path: Path) -> None:
    lock = tmp_path / "tools.lock"
    lock.write_text("# pins\n\nSEMGREP_VERSION=1.0.0\nOKF_COMMIT=abc\n", encoding="utf-8")
    assert load_pins(lock) == {"SEMGREP_VERSION": "1.0.0", "OKF_COMMIT": "abc"}
