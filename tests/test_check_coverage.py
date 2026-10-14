"""Exercise the coverage gate through its command-line interface."""

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_coverage.py"


@pytest.mark.parametrize(
    ("line_rate", "branch_rate", "branches_valid", "exit_code"),
    [
        ("0.70", "0.60", "10", 0),
        ("0.69", "0.90", "10", 1),
        ("0.90", "0.59", "10", 1),
        ("0.90", "1", "0", 0),
    ],
    ids=["pass-at-boundaries", "line-fail", "branch-fail", "no-branches"],
)
def test_coverage_gate(tmp_path, line_rate, branch_rate, branches_valid, exit_code):
    report = tmp_path / "coverage.xml"
    report.write_text(
        f'<coverage line-rate="{line_rate}" branch-rate="{branch_rate}" '
        f'branches-valid="{branches_valid}"/>',
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(report)], check=False, capture_output=True, text=True
    )
    assert result.returncode == exit_code
    assert "Line coverage:" in result.stdout
    assert "Branch coverage:" in result.stdout
    assert ("PASSED" if exit_code == 0 else "FAILED") in result.stdout


def test_custom_thresholds(tmp_path):
    report = tmp_path / "coverage.xml"
    report.write_text('<coverage line-rate="0.80" branch-rate="0.70"/>', encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(report),
            "--line-threshold",
            "85",
            "--branch-threshold",
            "75",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "85.00%" in result.stdout
    assert "75.00%" in result.stdout


@pytest.mark.parametrize(
    "contents",
    ["not XML", '<coverage branch-rate="0.80"/>', '<coverage line-rate="nan" branch-rate="1"/>'],
)
def test_invalid_report_fails_closed(tmp_path, contents):
    report = tmp_path / "coverage.xml"
    report.write_text(contents, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(report)], check=False, capture_output=True, text=True
    )
    assert result.returncode != 0
    assert "Cannot read coverage report:" in result.stderr
