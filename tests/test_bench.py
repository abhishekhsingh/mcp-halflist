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


def test_bench_default_json() -> None:
    result = runner.invoke(
        app, ["bench", "--stdio", _good_cmd(), "--format", "json", "-n", "3", "-w", "0"]
    )
    assert result.exit_code == 0, result.output

    report = json.loads(result.output)
    assert report["version"] == __version__
    assert report["transport"] == "stdio"
    assert report["iterations"] == 3
    assert report["warmup"] == 0
    assert report["benchmarked_count"] <= 5
    assert report["tool_count"] == 5
    assert len(report["benchmarks"]) <= 5


def test_bench_tool_filter() -> None:
    result = runner.invoke(
        app,
        [
            "bench",
            "--stdio",
            _good_cmd(),
            "--format",
            "json",
            "-n",
            "2",
            "-w",
            "0",
            "--tool",
            "greet",
        ],
    )
    assert result.exit_code == 0, result.output

    report = json.loads(result.output)
    assert report["benchmarked_count"] == 1
    assert report["benchmarks"][0]["tool_name"] == "greet"


def test_bench_all_tools() -> None:
    result = runner.invoke(
        app,
        ["bench", "--stdio", _good_cmd(), "--format", "json", "-n", "2", "-w", "0", "--all"],
    )
    assert result.exit_code == 0, result.output

    report = json.loads(result.output)
    assert report["benchmarked_count"] == 5
    assert len(report["benchmarks"]) == 5


def test_bench_terminal() -> None:
    result = runner.invoke(
        app,
        ["bench", "--stdio", _good_cmd(), "-n", "2", "-w", "0"],
    )
    assert result.exit_code == 0
    assert "Connected" in result.output


def test_bench_percentile_sanity() -> None:
    result = runner.invoke(
        app,
        [
            "bench",
            "--stdio",
            _good_cmd(),
            "--format",
            "json",
            "-n",
            "5",
            "-w",
            "0",
            "--tool",
            "add",
        ],
    )
    assert result.exit_code == 0, result.output

    report = json.loads(result.output)
    bm = report["benchmarks"][0]
    assert bm["min_ms"] <= bm["median_ms"] <= bm["max_ms"]
    assert bm["p95_ms"] <= bm["max_ms"]
    assert bm["p99_ms"] <= bm["max_ms"]
    assert bm["min_ms"] >= 0
