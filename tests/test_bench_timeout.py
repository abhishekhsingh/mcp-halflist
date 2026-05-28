"""Tests for bench per-call timeout and custom args."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp import types

from halflist.bench import bench_tool
from halflist.cli import _load_tool_args, app

from typer.testing import CliRunner

runner = CliRunner()
SERVERS_DIR = Path(__file__).parent / "servers"


def _good_cmd() -> str:
    return f"{sys.executable} {SERVERS_DIR / 'good_server.py'}"


def _slow_cmd() -> str:
    return f"{sys.executable} {SERVERS_DIR / 'slow_server.py'}"


# ── Per-call timeout ─────────────────────────────────────────────────────────


def _make_tool(name: str = "test_tool") -> types.Tool:
    return types.Tool(
        name=name,
        description="A test tool",
        inputSchema={"type": "object", "properties": {"q": {"type": "string"}}},
    )


@pytest.mark.asyncio
async def test_bench_timeout_counts_as_error() -> None:
    """A tool call that exceeds call_timeout should be counted as an error."""
    client = MagicMock()

    async def slow_call(name, args):
        await asyncio.sleep(10)
        return MagicMock(content=[], isError=False)

    client.call_tool = AsyncMock(side_effect=slow_call)
    tool = _make_tool()

    result = await bench_tool(
        client, tool, iterations=2, warmup=0, call_timeout=0.1,
    )

    assert result.errors == 2
    assert len(result.latencies) == 2
    for lat in result.latencies:
        assert lat >= 100


@pytest.mark.asyncio
async def test_bench_timeout_warmup_failure() -> None:
    """Warmup calls that timeout should count as warmup failures."""
    client = MagicMock()

    async def slow_call(name, args):
        await asyncio.sleep(10)

    client.call_tool = AsyncMock(side_effect=slow_call)
    tool = _make_tool()

    result = await bench_tool(
        client, tool, iterations=5, warmup=2, call_timeout=0.1,
    )

    assert result.skipped is True
    assert result.skip_reason == "all warmup calls failed"


@pytest.mark.asyncio
async def test_bench_no_timeout_works_normally() -> None:
    """Without call_timeout, calls should proceed without wrapping."""
    client = MagicMock()
    client.call_tool = AsyncMock(return_value=MagicMock(content=[], isError=False))
    tool = _make_tool()

    result = await bench_tool(
        client, tool, iterations=3, warmup=0, call_timeout=None,
    )

    assert result.errors == 0
    assert result.iterations == 3
    assert not result.skipped


# ── Custom args ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bench_custom_args_used() -> None:
    """Custom args should be passed to call_tool instead of generated ones."""
    client = MagicMock()
    client.call_tool = AsyncMock(return_value=MagicMock(content=[], isError=False))
    tool = _make_tool()

    custom = {"q": "my custom query"}
    result = await bench_tool(
        client, tool, iterations=2, warmup=0, custom_args=custom,
    )

    assert result.errors == 0
    for call in client.call_tool.call_args_list:
        assert call.args[1] == custom


@pytest.mark.asyncio
async def test_bench_no_custom_args_uses_generated() -> None:
    """Without custom_args, generated args should be used."""
    client = MagicMock()
    client.call_tool = AsyncMock(return_value=MagicMock(content=[], isError=False))
    tool = _make_tool()

    result = await bench_tool(
        client, tool, iterations=2, warmup=0, custom_args=None,
    )

    assert result.errors == 0
    for call in client.call_tool.call_args_list:
        assert call.args[1] == {"q": "test"}


# ── _load_tool_args ─────────────────────────────────────────────────────────


def test_load_tool_args_none() -> None:
    assert _load_tool_args(None) is None


def test_load_tool_args_valid(tmp_path: Path) -> None:
    f = tmp_path / "args.json"
    f.write_text(json.dumps({"greet": {"name": "Alice"}, "add": {"a": 1, "b": 2}}))
    result = _load_tool_args(str(f))
    assert result == {"greet": {"name": "Alice"}, "add": {"a": 1, "b": 2}}


def test_load_tool_args_file_not_found() -> None:
    with pytest.raises(RuntimeError):
        _load_tool_args("/nonexistent/args.json")


def test_load_tool_args_invalid_json(tmp_path: Path) -> None:
    f = tmp_path / "bad.json"
    f.write_text("not json")
    with pytest.raises(RuntimeError):
        _load_tool_args(str(f))


def test_load_tool_args_not_object(tmp_path: Path) -> None:
    f = tmp_path / "list.json"
    f.write_text(json.dumps([1, 2, 3]))
    with pytest.raises(RuntimeError):
        _load_tool_args(str(f))


def test_load_tool_args_tool_value_not_object(tmp_path: Path) -> None:
    f = tmp_path / "bad_val.json"
    f.write_text(json.dumps({"greet": "not a dict"}))
    with pytest.raises(RuntimeError):
        _load_tool_args(str(f))


# ── CLI integration: --args-file ─────────────────────────────────────────────


def test_bench_args_file_integration(tmp_path: Path) -> None:
    f = tmp_path / "args.json"
    f.write_text(json.dumps({"greet": {"name": "CustomName"}}))
    result = runner.invoke(
        app,
        [
            "bench", "--stdio", _good_cmd(), "--format", "json",
            "-n", "2", "-w", "0", "--tool", "greet",
            "--args-file", str(f),
        ],
    )
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["benchmarked_count"] == 1
    assert report["benchmarks"][0]["tool_name"] == "greet"


def test_check_args_file_integration(tmp_path: Path) -> None:
    f = tmp_path / "args.json"
    f.write_text(json.dumps({"greet": {"name": "CustomName"}}))
    result = runner.invoke(
        app,
        [
            "check", "--stdio", _good_cmd(), "--format", "json",
            "--args-file", str(f),
        ],
    )
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["total_failed"] == 0


def test_audit_args_file_integration(tmp_path: Path) -> None:
    f = tmp_path / "args.json"
    f.write_text(json.dumps({"greet": {"name": "CustomName"}}))
    result = runner.invoke(
        app,
        [
            "audit", "--stdio", _good_cmd(), "--format", "json",
            "-n", "2", "-w", "0",
            "--args-file", str(f),
        ],
    )
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["score"] > 0


def test_args_file_not_found_exits() -> None:
    result = runner.invoke(
        app,
        ["bench", "--stdio", _good_cmd(), "--args-file", "/nonexistent/args.json"],
    )
    assert result.exit_code == 3


# ── E2E timeout with real slow server ────────────────────────────────────────


def test_bench_timeout_with_slow_server() -> None:
    """Bench a slow server with a short timeout - should complete, not hang."""
    result = runner.invoke(
        app,
        [
            "bench", "--stdio", _slow_cmd(), "--format", "json",
            "-n", "2", "-w", "1",
            "--tool", "slow_tool", "--timeout", "2",
        ],
    )
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    bm = report["benchmarks"][0]
    assert bm["tool_name"] == "slow_tool"
    assert bm["skipped"] is True
    assert bm["skip_reason"] == "all warmup calls failed"


def test_bench_fast_tool_on_slow_server() -> None:
    """Fast tools on the slow server should still work fine."""
    result = runner.invoke(
        app,
        [
            "bench", "--stdio", _slow_cmd(), "--format", "json",
            "-n", "2", "-w", "1",
            "--tool", "fast_tool", "--timeout", "5",
        ],
    )
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    bm = report["benchmarks"][0]
    assert bm["tool_name"] == "fast_tool"
    assert bm["skipped"] is False
    assert bm["errors"] == 0
