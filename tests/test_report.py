import xml.etree.ElementTree as ET

from halflist import __version__
from halflist.report import (
    detect_report_type,
    render_audit_html,
    render_audit_junit,
    render_audit_markdown,
    render_badge_svg,
    render_bench_html,
    render_bench_junit,
    render_bench_markdown,
    render_check_html,
    render_check_junit,
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
                    {
                        "name": "init response",
                        "status": "PASS",
                        "message": None,
                        "duration_ms": 10.0,
                        "suite": "handshake",
                    },
                    {
                        "name": "ping returns pong",
                        "status": "FAIL",
                        "message": "timeout",
                        "duration_ms": 5.0,
                        "suite": "handshake",
                    },
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


# ── JUnit XML ───────────────────────────────────────────────────────────────

JUNIT_CHECK = {
    **SAMPLE_CHECK,
    "suites": [
        {
            "name": "handshake",
            "checks": [
                {
                    "name": "Server responds to initialize",
                    "status": "PASS",
                    "message": None,
                    "duration_ms": 12.0,
                    "suite": "handshake",
                },
                {
                    "name": "Protocol version present",
                    "status": "PASS",
                    "message": None,
                    "duration_ms": 1.0,
                    "suite": "handshake",
                },
            ],
            "passed": 2,
            "failed": 0,
            "warned": 0,
            "skipped": 0,
            "duration_ms": 13.0,
        },
        {
            "name": "tools",
            "checks": [
                {
                    "name": "tools/list returns valid array",
                    "status": "PASS",
                    "message": None,
                    "duration_ms": 34.0,
                    "suite": "tools",
                },
                {
                    "name": "Every tool has a description",
                    "status": "WARN",
                    "message": "2 tool(s) missing description",
                    "duration_ms": 1.0,
                    "suite": "tools",
                },
                {
                    "name": "Prompt injection scan",
                    "status": "FAIL",
                    "message": "found suspicious patterns",
                    "duration_ms": 5.0,
                    "suite": "tools",
                },
                {
                    "name": "Skippable check",
                    "status": "SKIP",
                    "message": "not applicable",
                    "duration_ms": 0.0,
                    "suite": "tools",
                },
            ],
            "passed": 1,
            "failed": 1,
            "warned": 1,
            "skipped": 1,
            "duration_ms": 40.0,
        },
    ],
    "total_passed": 3,
    "total_failed": 1,
    "total_warned": 1,
    "total_duration_ms": 53.0,
    "score": 60,
}


def test_junit_check_valid_xml() -> None:
    xml_str = render_check_junit(JUNIT_CHECK)
    assert xml_str.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    ET.fromstring(xml_str.split("\n", 1)[1])


def test_junit_check_testsuites_structure() -> None:
    xml_str = render_check_junit(JUNIT_CHECK)
    root = ET.fromstring(xml_str.split("\n", 1)[1])
    assert root.tag == "testsuites"
    assert root.get("name") == "halflist"
    assert root.get("tests") == "6"
    assert root.get("failures") == "2"
    assert root.get("skipped") == "1"


def test_junit_check_pass_testcase() -> None:
    xml_str = render_check_junit(JUNIT_CHECK)
    root = ET.fromstring(xml_str.split("\n", 1)[1])
    handshake = root.find(".//testsuite[@name='handshake']")
    assert handshake is not None
    tc = handshake.find("testcase[@name='Server responds to initialize']")
    assert tc is not None
    assert tc.get("classname") == "halflist.handshake"
    assert len(tc) == 0


def test_junit_check_fail_testcase() -> None:
    xml_str = render_check_junit(JUNIT_CHECK)
    root = ET.fromstring(xml_str.split("\n", 1)[1])
    tools = root.find(".//testsuite[@name='tools']")
    assert tools is not None
    tc = tools.find("testcase[@name='Prompt injection scan']")
    assert tc is not None
    failure = tc.find("failure")
    assert failure is not None
    assert failure.get("type") == "FAIL"
    assert "suspicious patterns" in (failure.get("message") or "")


def test_junit_check_warn_testcase() -> None:
    xml_str = render_check_junit(JUNIT_CHECK)
    root = ET.fromstring(xml_str.split("\n", 1)[1])
    tc = root.find(".//testcase[@name='Every tool has a description']")
    assert tc is not None
    failure = tc.find("failure")
    assert failure is not None
    assert failure.get("type") == "WARN"


def test_junit_check_skip_testcase() -> None:
    xml_str = render_check_junit(JUNIT_CHECK)
    root = ET.fromstring(xml_str.split("\n", 1)[1])
    tc = root.find(".//testcase[@name='Skippable check']")
    assert tc is not None
    skipped = tc.find("skipped")
    assert skipped is not None
    assert "not applicable" in (skipped.get("message") or "")


def test_junit_bench_output() -> None:
    xml_str = render_bench_junit(SAMPLE_BENCH)
    root = ET.fromstring(xml_str.split("\n", 1)[1])
    assert root.tag == "testsuites"
    bench_suite = root.find("testsuite[@name='benchmarks']")
    assert bench_suite is not None
    assert bench_suite.get("tests") == "2"


def test_junit_bench_properties() -> None:
    xml_str = render_bench_junit(SAMPLE_BENCH)
    root = ET.fromstring(xml_str.split("\n", 1)[1])
    tc = root.find(".//testcase[@name='greet']")
    assert tc is not None
    props = tc.find("properties")
    assert props is not None
    prop_names = {p.get("name") for p in props.findall("property")}
    assert "p50_ms" in prop_names
    assert "p95_ms" in prop_names
    assert "p99_ms" in prop_names
    assert "iterations" in prop_names


def test_junit_bench_skipped() -> None:
    data = {
        **SAMPLE_BENCH,
        "benchmarks": [
            {
                "tool_name": "broken",
                "iterations": 0,
                "min_ms": 0,
                "max_ms": 0,
                "mean_ms": 0,
                "median_ms": 0,
                "p95_ms": 0,
                "p99_ms": 0,
                "errors": 0,
                "skipped": True,
                "skip_reason": "all warmup calls failed",
            },
        ],
    }
    xml_str = render_bench_junit(data)
    root = ET.fromstring(xml_str.split("\n", 1)[1])
    tc = root.find(".//testcase[@name='broken']")
    assert tc is not None
    assert tc.find("skipped") is not None


def test_junit_bench_errors() -> None:
    data = {
        **SAMPLE_BENCH,
        "benchmarks": [
            {
                "tool_name": "flaky",
                "iterations": 10,
                "min_ms": 5,
                "max_ms": 50,
                "mean_ms": 20,
                "median_ms": 18,
                "p95_ms": 45,
                "p99_ms": 49,
                "errors": 3,
            },
        ],
    }
    xml_str = render_bench_junit(data)
    root = ET.fromstring(xml_str.split("\n", 1)[1])
    tc = root.find(".//testcase[@name='flaky']")
    assert tc is not None
    failure = tc.find("failure")
    assert failure is not None
    assert "3/10" in (failure.get("message") or "")


def test_junit_audit_combined() -> None:
    xml_str = render_audit_junit(SAMPLE_AUDIT)
    root = ET.fromstring(xml_str.split("\n", 1)[1])
    suite_names = [ts.get("name") for ts in root.findall("testsuite")]
    assert "handshake" in suite_names
    assert "benchmarks" in suite_names


def test_junit_special_chars_escaped() -> None:
    data = {
        **SAMPLE_CHECK,
        "suites": [
            {
                "name": "security",
                "checks": [
                    {
                        "name": 'Check with <angle> & "quotes"',
                        "status": "FAIL",
                        "message": "found <script>alert(1)</script> & more",
                        "duration_ms": 1.0,
                        "suite": "security",
                    },
                ],
                "passed": 0,
                "failed": 1,
                "warned": 0,
                "skipped": 0,
                "duration_ms": 1.0,
            },
        ],
    }
    xml_str = render_check_junit(data)
    ET.fromstring(xml_str.split("\n", 1)[1])
