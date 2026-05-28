"""Tests for debug logging module."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import httpx
import pytest

from halflist.debug import (
    MCPDebugLogger,
    _format_args,
    _mask_headers,
    _truncate,
    create_debug_event_hooks,
    setup_debug_logging,
)


@pytest.fixture(autouse=True)
def _reset_loggers():
    """Reset halflist and SDK loggers between tests."""
    names = ("halflist", "mcp", "httpx", "httpcore")
    saved = {}
    for name in names:
        lgr = logging.getLogger(name)
        saved[name] = (lgr.level, list(lgr.handlers))
    yield
    for name in names:
        lgr = logging.getLogger(name)
        lgr.setLevel(saved[name][0])
        lgr.handlers = saved[name][1]


# ── setup_debug_logging ─────────────────────────────────────────────────────


def test_setup_debug_enables_halflist_logger() -> None:
    setup_debug_logging(debug=True)
    lgr = logging.getLogger("halflist")
    assert lgr.level == logging.DEBUG
    assert len(lgr.handlers) >= 1


def test_setup_debug_enables_sdk_loggers() -> None:
    setup_debug_logging(debug=True)
    for name in ("mcp", "httpx", "httpcore"):
        lgr = logging.getLogger(name)
        assert lgr.level == logging.DEBUG
        assert len(lgr.handlers) >= 1


def test_setup_debug_false_is_noop() -> None:
    lgr = logging.getLogger("halflist")
    original_level = lgr.level
    original_handlers = list(lgr.handlers)
    setup_debug_logging(debug=False)
    assert lgr.level == original_level
    assert lgr.handlers == original_handlers


def test_env_var_enables_debug(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HALFLIST_LOG_LEVEL", "DEBUG")
    setup_debug_logging(debug=False)
    lgr = logging.getLogger("halflist")
    assert lgr.level == logging.DEBUG


def test_env_var_info_level(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HALFLIST_LOG_LEVEL", "INFO")
    setup_debug_logging(debug=False)
    lgr = logging.getLogger("halflist")
    assert lgr.level == logging.INFO


def test_debug_log_creates_file(tmp_path: Path) -> None:
    log_file = tmp_path / "debug.log"
    setup_debug_logging(debug=True, debug_log=str(log_file))
    lgr = logging.getLogger("halflist")
    file_handlers = [h for h in lgr.handlers if isinstance(h, logging.FileHandler)]
    assert len(file_handlers) >= 1


def test_debug_log_implies_debug(tmp_path: Path) -> None:
    log_file = tmp_path / "debug.log"
    setup_debug_logging(debug=False, debug_log=str(log_file))
    lgr = logging.getLogger("halflist")
    assert lgr.level == logging.DEBUG


# ── _mask_headers ────────────────────────────────────────────────────────────


def test_mask_headers_authorization() -> None:
    result = _mask_headers({"Authorization": "Bearer secret-token-123"})
    assert result["Authorization"] == "*****"


def test_mask_headers_cookie() -> None:
    result = _mask_headers({"Cookie": "session=abc123"})
    assert result["Cookie"] == "*****"


def test_mask_headers_api_key() -> None:
    result = _mask_headers({"X-Api-Key": "key-123"})
    assert result["X-Api-Key"] == "*****"


def test_mask_headers_passthrough() -> None:
    result = _mask_headers({"Content-Type": "application/json", "Accept": "text/html"})
    assert result["Content-Type"] == "application/json"
    assert result["Accept"] == "text/html"


def test_mask_headers_case_insensitive() -> None:
    result = _mask_headers({"AUTHORIZATION": "Bearer tok", "authorization": "Bearer tok2"})
    for val in result.values():
        assert val == "*****"


def test_mask_headers_httpx_headers() -> None:
    headers = httpx.Headers({"Authorization": "Bearer secret", "Content-Type": "application/json"})
    result = _mask_headers(headers)
    assert result["authorization"] == "*****"
    assert result["content-type"] == "application/json"


# ── MCPDebugLogger ───────────────────────────────────────────────────────────


def test_debug_logger_logs_request(caplog: pytest.LogCaptureFixture) -> None:
    setup_debug_logging(debug=True)
    with caplog.at_level(logging.DEBUG, logger="halflist"):
        with MCPDebugLogger("tools/list"):
            pass
    assert any("→ tools/list" in r.message for r in caplog.records)


def test_debug_logger_logs_success(caplog: pytest.LogCaptureFixture) -> None:
    setup_debug_logging(debug=True)
    with caplog.at_level(logging.DEBUG, logger="halflist"):
        with MCPDebugLogger("tools/list") as dbg:
            dbg.success("21 tools")
    assert any("← tools/list: 21 tools" in r.message for r in caplog.records)


def test_debug_logger_logs_error(caplog: pytest.LogCaptureFixture) -> None:
    setup_debug_logging(debug=True)
    with caplog.at_level(logging.DEBUG, logger="halflist"):
        try:
            with MCPDebugLogger("tools/call", "broken_tool"):
                raise ConnectionError("connection lost")
        except ConnectionError:
            pass
    assert any("← tools/call: ERROR ConnectionError" in r.message for r in caplog.records)


def test_debug_logger_logs_timeout(caplog: pytest.LogCaptureFixture) -> None:
    setup_debug_logging(debug=True)
    with caplog.at_level(logging.DEBUG, logger="halflist"):
        try:
            with MCPDebugLogger("tools/call", "slow_tool"):
                raise TimeoutError()
        except TimeoutError:
            pass
    assert any("← tools/call: TIMEOUT" in r.message for r in caplog.records)


def test_debug_logger_with_params(caplog: pytest.LogCaptureFixture) -> None:
    setup_debug_logging(debug=True)
    with caplog.at_level(logging.DEBUG, logger="halflist"):
        with MCPDebugLogger("tools/call", 'search {"query": "test"}') as dbg:
            dbg.success("ok (2 content items)")
    assert any('→ tools/call search {"query": "test"}' in r.message for r in caplog.records)


def test_debug_logger_elapsed_time(caplog: pytest.LogCaptureFixture) -> None:
    import time

    setup_debug_logging(debug=True)
    with caplog.at_level(logging.DEBUG, logger="halflist"):
        with MCPDebugLogger("ping") as dbg:
            time.sleep(0.01)
            dbg.success("pong")
    success_records = [r for r in caplog.records if "← ping: pong" in r.message]
    assert len(success_records) == 1
    assert "ms)" in success_records[0].message


# ── _format_args / _truncate ────────────────────────────────────────────────


def test_format_args_none() -> None:
    assert _format_args(None) == ""


def test_format_args_empty() -> None:
    assert _format_args({}) == ""


def test_format_args_simple() -> None:
    result = _format_args({"query": "test"})
    assert '"query"' in result
    assert '"test"' in result


def test_format_args_truncates_long() -> None:
    long_args = {"data": "x" * 500}
    result = _format_args(long_args)
    assert len(result) <= 203
    assert result.endswith("...")


def test_truncate_short() -> None:
    assert _truncate("hello", 10) == "hello"


def test_truncate_long() -> None:
    result = _truncate("a" * 300, 200)
    assert len(result) == 203
    assert result.endswith("...")


# ── create_debug_event_hooks ─────────────────────────────────────────────────


def test_create_debug_event_hooks_when_enabled() -> None:
    setup_debug_logging(debug=True)
    hooks = create_debug_event_hooks()
    assert "request" in hooks
    assert "response" in hooks
    assert len(hooks["request"]) == 1
    assert len(hooks["response"]) == 1


def test_create_debug_event_hooks_when_disabled() -> None:
    hooks = create_debug_event_hooks()
    assert hooks == {}


# ── HTTP event hook logging ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_request_masks_auth_header(caplog: pytest.LogCaptureFixture) -> None:
    from halflist.debug import _log_request

    setup_debug_logging(debug=True)
    request = httpx.Request(
        "POST",
        "https://example.com/mcp",
        headers={"Authorization": "Bearer secret-token", "Content-Type": "application/json"},
    )
    with caplog.at_level(logging.DEBUG, logger="halflist"):
        await _log_request(request)
    log_output = " ".join(r.message for r in caplog.records)
    assert "*****" in log_output
    assert "secret-token" not in log_output


@pytest.mark.asyncio
async def test_log_response(caplog: pytest.LogCaptureFixture) -> None:
    from halflist.debug import _log_response

    setup_debug_logging(debug=True)
    request = httpx.Request("POST", "https://example.com/mcp")
    response = httpx.Response(200, request=request, content=b'{"result": "ok"}')
    with caplog.at_level(logging.DEBUG, logger="halflist"):
        await _log_response(response)
    assert any("HTTP ← 200" in r.message for r in caplog.records)


# ── CLI flag tests ───────────────────────────────────────────────────────────


def test_debug_flag_on_all_commands() -> None:
    from typer.testing import CliRunner

    from halflist.cli import app
    from tests.conftest import strip_ansi

    runner = CliRunner()
    for cmd in ("check", "bench", "audit", "watch", "pin", "report"):
        result = runner.invoke(app, [cmd, "--help"])
        plain = strip_ansi(result.output)
        assert "--debug" in plain, f"--debug missing from {cmd}"
        assert "--debug-log" in plain, f"--debug-log missing from {cmd}"


# ── Integration test ─────────────────────────────────────────────────────────


def test_debug_output_on_check(caplog: pytest.LogCaptureFixture) -> None:
    from typer.testing import CliRunner
    from halflist.cli import app

    runner = CliRunner()
    servers = Path(__file__).parent / "servers"
    cmd = f"{sys.executable} {servers / 'good_server.py'}"
    with caplog.at_level(logging.DEBUG, logger="halflist"):
        result = runner.invoke(app, ["check", "--stdio", cmd, "--format", "json", "--debug"])
    assert result.exit_code == 0, result.output
    messages = " ".join(r.message for r in caplog.records)
    assert "→ initialize" in messages or "→ tools/list" in messages
