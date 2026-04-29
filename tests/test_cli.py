import json
import sys
from pathlib import Path

from typer.testing import CliRunner

from halflist.cli import app

runner = CliRunner()

SERVERS_DIR = Path(__file__).parent / "servers"


def test_cli_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "halflist" in result.output


def test_cli_check_good_server_json() -> None:
    cmd = f"{sys.executable} {SERVERS_DIR / 'good_server.py'}"
    result = runner.invoke(app, ["check", "--stdio", cmd, "--format", "json"])
    assert result.exit_code == 0

    report = json.loads(result.output)
    assert report["score"] > 0
    assert report["version"] == "0.3.0"
    assert report["transport"] == "stdio"
    assert len(report["suites"]) > 0
    assert report["total_failed"] == 0


def test_cli_check_bad_server_json() -> None:
    cmd = f"{sys.executable} {SERVERS_DIR / 'bad_server.py'}"
    result = runner.invoke(app, ["check", "--stdio", cmd, "--format", "json"])

    report = json.loads(result.output)
    assert report["total_warned"] > 0


def test_cli_check_good_server_terminal() -> None:
    cmd = f"{sys.executable} {SERVERS_DIR / 'good_server.py'}"
    result = runner.invoke(app, ["check", "--stdio", cmd])
    assert result.exit_code == 0
    assert "passed" in result.output


def test_cli_check_suite_filter() -> None:
    cmd = f"{sys.executable} {SERVERS_DIR / 'good_server.py'}"
    result = runner.invoke(app, ["check", "--stdio", cmd, "--suite", "handshake", "--format", "json"])
    assert result.exit_code == 0

    report = json.loads(result.output)
    assert len(report["suites"]) == 1
    assert report["suites"][0]["name"] == "handshake"


def test_cli_invalid_format() -> None:
    cmd = f"{sys.executable} {SERVERS_DIR / 'good_server.py'}"
    result = runner.invoke(app, ["check", "--stdio", cmd, "--format", "xml"])
    assert result.exit_code == 3


def test_cli_quiet_flag() -> None:
    cmd = f"{sys.executable} {SERVERS_DIR / 'good_server.py'}"
    result = runner.invoke(app, ["check", "--stdio", cmd, "--quiet", "--format", "json"])
    assert result.exit_code == 0

    report = json.loads(result.output)
    assert report["total_failed"] == 0


def test_cli_json_auto_quiet() -> None:
    cmd = f"{sys.executable} {SERVERS_DIR / 'good_server.py'}"
    result = runner.invoke(app, ["check", "--stdio", cmd, "--format", "json"])
    assert result.exit_code == 0
    output = result.output.strip()
    assert output.startswith("{"), "JSON output should start with { (no stderr noise)"
    report = json.loads(output)
    assert report["score"] > 0
