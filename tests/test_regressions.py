"""Regression tests for fixes made after the v1.0.0 release."""

import json
import re
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from halflist import __version__
from halflist.cli import _maybe_setup_pkce, _resolve_headers, app
from tests.conftest import strip_ansi

runner = CliRunner()

SERVERS_DIR = Path(__file__).parent / "servers"


def _cmd(name: str) -> str:
    return f"{sys.executable} {SERVERS_DIR / name}"


# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------


def test_version_is_semver_and_reported() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in strip_ansi(result.output)


# ---------------------------------------------------------------------------
# Rich markup injection from server-controlled text
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("command", ["check", "audit"])
def test_markup_like_server_text_does_not_crash(command: str) -> None:
    result = runner.invoke(app, [command, "--stdio", _cmd("markup_server.py"), "-v", "-q"])
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert result.exit_code in (0, 1)
    out = strip_ansi(result.output)
    assert "markup[/x]server" in out
    assert "list[/y]tool" in out


def test_markup_like_tool_name_in_bench_table() -> None:
    result = runner.invoke(
        app,
        ["bench", "--stdio", _cmd("markup_server.py"), "--all", "-n", "2", "-w", "0", "-q"],
    )
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert result.exit_code == 0
    out = strip_ansi(result.output)
    assert "list[/y]tool" in out


def test_markup_like_connection_error_does_not_crash() -> None:
    result = runner.invoke(app, ["check", "--stdio", "/nonexistent/[/z]cmd", "-q"])
    assert result.exit_code == 2
    assert "Connection failed" in strip_ansi(result.output)


# ---------------------------------------------------------------------------
# Authorization header is case-insensitive
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["Authorization", "authorization", "AUTHORIZATION"])
def test_explicit_authorization_header_skips_pkce(name: str) -> None:
    provider, callback = _maybe_setup_pkce(
        "http://localhost:9/mcp",
        {name: "Bearer abc"},
        no_auth=False,
        no_browser=True,
        clear_tokens=False,
        callback_port=None,
        oauth_scope=None,
    )
    assert provider is None
    assert callback is None


async def test_oauth_token_replaces_lowercase_authorization_header(
    oauth_server: dict[str, str],
) -> None:
    from rich.console import Console

    headers = await _resolve_headers(
        ["authorization: Bearer manual"],
        oauth_server["url"],
        oauth_server["client_id"],
        oauth_server["client_secret"],
        None,
        Console(quiet=True),
    )
    assert headers is not None
    auth_keys = [k for k in headers if k.lower() == "authorization"]
    assert auth_keys == ["Authorization"]
    assert headers["Authorization"].startswith("Bearer mock-token-")


# ---------------------------------------------------------------------------
# --pin-file
# ---------------------------------------------------------------------------


def _security_checks(output: str) -> dict[str, dict]:
    report = json.loads(output)
    suite = next(s for s in report["suites"] if s["name"] == "security")
    return {c["name"]: c for c in suite["checks"]}


def test_pin_file_roundtrip_passes(tmp_path: Path) -> None:
    pin = tmp_path / "pins" / "good.json"
    pin.parent.mkdir()
    pinned = runner.invoke(app, ["pin", "--stdio", _cmd("good_server.py"), "-o", str(pin), "-q"])
    assert pinned.exit_code == 0
    assert pin.is_file()

    result = runner.invoke(
        app,
        [
            "check",
            "--stdio",
            _cmd("good_server.py"),
            "--suite",
            "security",
            "--format",
            "json",
            "--pin-file",
            str(pin),
        ],
    )
    assert result.exit_code == 0
    assert _security_checks(result.output)["Tool pin verification"]["status"] == "PASS"


def test_pin_file_detects_changed_tool(tmp_path: Path) -> None:
    pin = tmp_path / "good.json"
    runner.invoke(app, ["pin", "--stdio", _cmd("good_server.py"), "-o", str(pin), "-q"])
    data = json.loads(pin.read_text())
    first = next(iter(data["tool_hashes"]))
    data["tool_hashes"][first] = "0" * 64
    pin.write_text(json.dumps(data))

    result = runner.invoke(
        app,
        [
            "check",
            "--stdio",
            _cmd("good_server.py"),
            "--suite",
            "security",
            "--format",
            "json",
            "--pin-file",
            str(pin),
        ],
    )
    assert result.exit_code == 1
    check = _security_checks(result.output)["Tool pin verification"]
    assert check["status"] == "FAIL"
    assert first in check["message"]


def test_pin_file_missing_is_config_error(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["check", "--stdio", _cmd("good_server.py"), "--pin-file", str(tmp_path / "nope.json")],
    )
    assert result.exit_code == 3
    assert "Pin file not found" in strip_ansi(result.output)


def test_pin_file_on_audit(tmp_path: Path) -> None:
    pin = tmp_path / "good.json"
    runner.invoke(app, ["pin", "--stdio", _cmd("good_server.py"), "-o", str(pin), "-q"])
    result = runner.invoke(
        app,
        [
            "audit",
            "--stdio",
            _cmd("good_server.py"),
            "-n",
            "1",
            "-w",
            "0",
            "--format",
            "json",
            "--pin-file",
            str(pin),
        ],
    )
    assert result.exit_code == 0
    assert _security_checks(result.output)["Tool pin verification"]["status"] == "PASS"
