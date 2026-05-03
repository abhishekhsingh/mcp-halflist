from halflist import __version__
from halflist.report import (
    detect_report_type,
    render_audit_html,
    render_audit_markdown,
    render_badge_svg,
    render_bench_html,
    render_bench_markdown,
    render_check_html,
    render_check_markdown,
)

SAMPLE_CHECK = {
    "version": __version__,
    "timestamp": "2026-04-28T12:00:00+00:00",
    "server_info": {"name": "test-server", "version": "1.0.0"},
    "transport": "stdio",
    "suites": [
        {
            "name": "handshake",
            "checks": [],
            "passed": 6,
            "failed": 0,
            "warned": 0,
            "skipped": 0,
            "duration_ms": 100.0,
        }
    ],
    "score": 100,
    "total_passed": 6,
    "total_failed": 0,
    "total_warned": 0,
    "total_duration_ms": 100.0,
}

SAMPLE_BENCH = {
    "version": __version__,
    "timestamp": "2026-04-28T12:00:00+00:00",
    "server_info": {"name": "test-server", "version": "1.0.0"},
    "transport": "stdio",
    "connection_ms": 50.0,
    "discovery_ms": 10.0,
    "tool_count": 3,
    "benchmarked_count": 2,
    "iterations": 10,
    "warmup": 2,
    "benchmarks": [
        {
            "tool_name": "greet",
            "iterations": 10,
            "min_ms": 5.0,
            "max_ms": 50.0,
            "mean_ms": 20.0,
            "median_ms": 18.0,
            "p95_ms": 45.0,
            "p99_ms": 49.0,
            "errors": 0,
        },
        {
            "tool_name": "add",
            "iterations": 10,
            "min_ms": 3.0,
            "max_ms": 30.0,
            "mean_ms": 10.0,
            "median_ms": 8.0,
            "p95_ms": 25.0,
            "p99_ms": 29.0,
            "errors": 0,
        },
    ],
    "total_calls": 20,
    "total_duration_ms": 5000.0,
}


def test_check_markdown() -> None:
    md = render_check_markdown(SAMPLE_CHECK)
    assert "# MCP Conformance Report" in md
    assert "test-server v1.0.0" in md
    assert "100/100" in md
    assert "| handshake |" in md


def test_bench_markdown() -> None:
    md = render_bench_markdown(SAMPLE_BENCH)
    assert "# MCP Benchmark Report" in md
    assert "test-server v1.0.0" in md
    assert "| greet |" in md
    assert "| add |" in md


def test_badge_svg_check() -> None:
    svg = render_badge_svg(SAMPLE_CHECK)
    assert "<svg" in svg
    assert "100/100" in svg
    assert "MCP" in svg


def test_badge_svg_bench() -> None:
    svg = render_badge_svg(SAMPLE_BENCH)
    assert "<svg" in svg
    assert "MCP bench" in svg


SAMPLE_AUDIT = {
    "version": __version__,
    "timestamp": "2026-04-28T12:00:00+00:00",
    "server_info": {"name": "test-server", "version": "1.0.0"},
    "transport": "stdio",
    "score": 100,
    "suites": [
        {
            "name": "handshake",
            "checks": [],
            "passed": 6,
            "failed": 0,
            "warned": 0,
            "skipped": 0,
            "duration_ms": 100.0,
        }
    ],
    "total_passed": 6,
    "total_failed": 0,
    "total_warned": 0,
    "connection_ms": 50.0,
    "discovery_ms": 10.0,
    "tool_count": 2,
    "benchmarked_count": 2,
    "iterations": 10,
    "warmup": 2,
    "benchmarks": [
        {
            "tool_name": "greet",
            "iterations": 10,
            "min_ms": 5.0,
            "max_ms": 50.0,
            "mean_ms": 20.0,
            "median_ms": 18.0,
            "p95_ms": 45.0,
            "p99_ms": 49.0,
            "errors": 0,
        },
    ],
    "total_calls": 10,
    "total_duration_ms": 3000.0,
}


def test_audit_markdown() -> None:
    md = render_audit_markdown(SAMPLE_AUDIT)
    assert "# MCP Audit Report" in md
    assert "test-server v1.0.0" in md
    assert "100/100" in md
    assert "## Conformance" in md
    assert "| handshake |" in md
    assert "## Latency (ms)" in md
    assert "| greet |" in md


def test_badge_svg_audit() -> None:
    svg = render_badge_svg(SAMPLE_AUDIT)
    assert "<svg" in svg
    assert "100/100" in svg
    assert "MCP" in svg


def test_detect_report_type() -> None:
    assert detect_report_type(SAMPLE_CHECK) == "check"
    assert detect_report_type(SAMPLE_BENCH) == "bench"
    assert detect_report_type(SAMPLE_AUDIT) == "audit"
    assert detect_report_type({}) == "unknown"


def test_check_html() -> None:
    html = render_check_html(SAMPLE_CHECK)
    assert "<!DOCTYPE html>" in html
    assert "test-server" in html
    assert "mcp-halflist" in html
    assert "PASS" in html
    assert "HANDSHAKE" in html


def test_bench_html() -> None:
    html = render_bench_html(SAMPLE_BENCH)
    assert "<!DOCTYPE html>" in html
    assert "test-server" in html
    assert "greet" in html
    assert "add" in html
    assert "bar-fill" in html


def test_audit_html() -> None:
    html = render_audit_html(SAMPLE_AUDIT)
    assert "<!DOCTYPE html>" in html
    assert "test-server" in html
    assert "PASS" in html
    assert "HANDSHAKE" in html
    assert "greet" in html
    assert "gauge" in html


def test_check_html_with_checks() -> None:
    data = {
        **SAMPLE_CHECK,
        "suites": [
            {
                "name": "handshake",
                "checks": [
                    {"name": "init response", "status": "PASS", "message": None, "duration_ms": 10.0, "suite": "handshake"},
                    {"name": "ping returns pong", "status": "FAIL", "message": "timeout", "duration_ms": 5.0, "suite": "handshake"},
                ],
                "passed": 1,
                "failed": 1,
                "warned": 0,
                "skipped": 0,
                "duration_ms": 15.0,
            }
        ],
        "total_failed": 1,
        "score": 50,
    }
    html = render_check_html(data)
    assert "FAIL" in html
    assert "init response" in html
    assert "timeout" in html
