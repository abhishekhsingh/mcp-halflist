import json
import sys
from pathlib import Path

from typer.testing import CliRunner

from halflist import __version__
from halflist.cli import app

runner = CliRunner()

SERVERS_DIR = Path(__file__).parent / "servers"


def _good_cmd() -> str:
    return f"{sys.executable} {SERVERS_DIR / 'good_server.py'}"


def test_audit_json() -> None:
    result = runner.invoke(
        app, ["audit", "--stdio", _good_cmd(), "--format", "json", "-n", "2", "-w", "0"]
    )
    assert result.exit_code == 0, result.output

    report = json.loads(result.output)
    assert report["version"] == __version__
    assert report["transport"] == "stdio"
    assert report["score"] > 0
    assert "suites" in report
    assert "benchmarks" in report
    assert len(report["suites"]) == 5
    assert report["benchmarked_count"] == 5
    assert len(report["benchmarks"]) == 5
    assert report["total_failed"] == 0
    assert report["iterations"] == 2
    assert report["connection_ms"] > 0
    assert report["discovery_ms"] >= 0


def test_audit_terminal() -> None:
    result = runner.invoke(
        app, ["audit", "--stdio", _good_cmd(), "-n", "2", "-w", "0"]
    )
    assert result.exit_code == 0
    assert "Connected" in result.output
    assert "passed" in result.output


def test_audit_combined_has_both_sections() -> None:
    result = runner.invoke(
        app, ["audit", "--stdio", _good_cmd(), "--format", "json", "-n", "2", "-w", "0"]
    )
    assert result.exit_code == 0, result.output

    report = json.loads(result.output)
    assert report["suites"][0]["name"] == "handshake"
    assert report["suites"][1]["name"] == "tools"
    assert report["suites"][2]["name"] == "resources"
    assert report["suites"][3]["name"] == "prompts"
    assert report["suites"][4]["name"] == "security"

    tool_names = {b["tool_name"] for b in report["benchmarks"]}
    assert "greet" in tool_names
    assert "add" in tool_names


def test_audit_report_detection() -> None:
    from halflist.report import detect_report_type

    audit_data = {"suites": [], "benchmarks": []}
    assert detect_report_type(audit_data) == "audit"
