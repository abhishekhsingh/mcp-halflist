from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from halflist import __version__
from halflist.models import (
    AuditReport,
    BenchReport,
    CheckResult,
    HalflistReport,
    ServerInfo,
    SuiteResult,
)

_SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

STATUS_SYMBOLS = {
    "PASS": ("✓", "green"),
    "FAIL": ("✗", "red"),
    "WARN": ("⚠", "yellow"),
    "SKIP": ("—", "dim"),
}

DOT_LEADER_WIDTH = 52


# ---------------------------------------------------------------------------
# Check report helpers
# ---------------------------------------------------------------------------


def compute_score(suites: list[SuiteResult]) -> int:
    total = 0
    earned = 0.0
    for suite in suites:
        for check in suite.checks:
            total += 1
            if check.status == "PASS":
                earned += 1.0
            elif check.status == "WARN":
                earned += 0.5
            elif check.status == "SKIP":
                earned += 0.5
    if total == 0:
        return 0
    return round((earned / total) * 100)


def build_report(
    server_info: ServerInfo | None,
    suites: list[SuiteResult],
) -> HalflistReport:
    total_passed = sum(s.passed for s in suites)
    total_failed = sum(s.failed for s in suites)
    total_warned = sum(s.warned for s in suites)
    total_duration = sum(s.duration_ms for s in suites)
    score = compute_score(suites)

    return HalflistReport(
        version=__version__,
        timestamp=datetime.now(timezone.utc).isoformat(),
        server_info=server_info,
        transport="stdio",
        suites=suites,
        score=score,
        total_passed=total_passed,
        total_failed=total_failed,
        total_warned=total_warned,
        total_duration_ms=total_duration,
    )


# ---------------------------------------------------------------------------
# Shared terminal helpers
# ---------------------------------------------------------------------------


def print_connection(console: Console, server_info: ServerInfo, tool_count: int) -> None:
    console.print(
        f"  [green]✓[/green] Connected to [bold]{server_info.name}[/bold] v{server_info.version}"
    )
    console.print(f"    {tool_count} tools · 0 resources · 0 prompts")
    console.print()


def _score_color(score: int) -> str:
    if score >= 80:
        return "green"
    if score >= 50:
        return "yellow"
    return "red"


def _score_bar(score: int) -> str:
    color = _score_color(score)
    filled = score // 5
    empty = 20 - filled
    return f"[{color}]{'█' * filled}[/{color}][dim]{'░' * empty}[/dim]"


def _latency_color(ms: float) -> str:
    if ms > 1000:
        return "red"
    if ms > 500:
        return "yellow"
    return "green"


# ---------------------------------------------------------------------------
# Check: Phase 2 live progress
# ---------------------------------------------------------------------------


class LiveProgress:
    def __init__(self, suite_names: list[str]) -> None:
        self.suite_names = suite_names
        self.checks: dict[str, list[str]] = {n: [] for n in suite_names}
        self.current: str | None = None
        self._frame = 0
        self._start = time.monotonic()
        self._current_start: float | None = None

    def set_current(self, name: str | None) -> None:
        self.current = name
        self._current_start = time.monotonic() if name else None

    def add_check(self, check: CheckResult) -> None:
        self.checks[check.suite].append(check.status)

    def render(self) -> Group:
        self._frame += 1
        spinner = _SPINNER_FRAMES[self._frame % len(_SPINNER_FRAMES)]
        total_done = sum(len(v) for v in self.checks.values())
        elapsed_total = time.monotonic() - self._start
        header = Text(f"  {spinner} Running checks... {total_done} completed · {elapsed_total:.1f}s\n")
        lines: list[Text] = [header]

        for name in self.suite_names:
            statuses = self.checks.get(name, [])
            line = Text(f"  {name:<12} ")
            for s in statuses:
                sym, color = STATUS_SYMBOLS.get(s, ("?", "white"))
                line.append(sym, style=color)
            padding = max(1, 28 - len(statuses))
            line.append(" " * padding)
            if name == self.current:
                elapsed_item = ""
                if self._current_start is not None:
                    elapsed_item = f" {time.monotonic() - self._current_start:.1f}s"
                line.append(spinner, style="bold blue")
                line.append(f" running...{elapsed_item}", style="bold blue")
            elif statuses:
                line.append(f"{len(statuses)}/{len(statuses)}", style="dim")
            lines.append(line)

        lines.append(Text(""))
        return Group(*lines)

    def __rich__(self) -> Group:
        return self.render()


# ---------------------------------------------------------------------------
# Check: Phase 3 final report
# ---------------------------------------------------------------------------


def render_final_report(console: Console, report: HalflistReport, verbose: bool) -> None:
    score = report.score
    sc = _score_color(score)

    server_line = "unknown"
    if report.server_info:
        server_line = f"{report.server_info.name} v{report.server_info.version}"

    panel_content = (
        f"\n"
        f"  Server:     [bold]{server_line}[/bold]\n"
        f"  Transport:  {report.transport}\n"
        f"  Score:      [{sc}]{score}/100[/{sc}]  {_score_bar(score)}  {score}%\n"
    )

    console.print(
        Panel(
            panel_content,
            title=f"[bold]mcp-halflist v{report.version}[/bold]",
            border_style="blue",
            expand=True,
        )
    )
    console.print()

    for suite in report.suites:
        _render_suite(console, suite, verbose)

    total_dur = report.total_duration_ms / 1000
    console.print(f"  {'─' * 56}")
    parts: list[str] = []
    if report.total_passed > 0:
        parts.append(f"[green]{report.total_passed} passed[/green]")
    if report.total_failed > 0:
        parts.append(f"[red]{report.total_failed} failed[/red]")
    if report.total_warned > 0:
        w = report.total_warned
        parts.append(f"[yellow]{w} warning{'s' if w != 1 else ''}[/yellow]")
    parts.append(f"{total_dur:.1f}s")
    console.print(f"  {' · '.join(parts)}")
    console.print()


def _render_suite(console: Console, suite: SuiteResult, verbose: bool) -> None:
    passed = suite.passed
    total = len(suite.checks)
    suffix = ""
    if suite.warned > 0:
        suffix += f" [yellow]⚠ {suite.warned}[/yellow]"
    if suite.failed > 0:
        suffix += f" [red]✗ {suite.failed}[/red]"

    dashes = "─" * (40 - len(suite.name))
    console.print(f"  [bold]{suite.name}[/bold] {dashes} {passed}/{total} passed{suffix}")

    if not verbose:
        symbols = Text("    ")
        for check in suite.checks:
            sym, color = STATUS_SYMBOLS[check.status]
            symbols.append(sym, style=color)
        console.print(symbols)

    has_nonpass = any(c.status != "PASS" for c in suite.checks)
    for check in suite.checks:
        if verbose or check.status != "PASS":
            _render_check_line(console, check)

    if not verbose and has_nonpass:
        console.print()

    console.print()


def _render_check_line(console: Console, check: CheckResult) -> None:
    sym, color = STATUS_SYMBOLS[check.status]

    detail = ""
    if check.message:
        detail = check.message
    elif check.duration_ms > 0:
        detail = f"{check.duration_ms:.0f}ms"

    name_len = len(check.name)
    dots_count = max(2, DOT_LEADER_WIDTH - name_len)
    dots = "·" * dots_count

    line = Text("    ")
    line.append(sym, style=color)
    line.append(f" {check.name} ")
    line.append(dots, style="dim")
    if detail:
        line.append(f" {detail}", style="dim")
    else:
        line.append(f" {check.status}", style="dim")

    console.print(line)


def render_json(report: HalflistReport) -> str:
    return report.model_dump_json(indent=2)


# ---------------------------------------------------------------------------
# Bench: Phase 2 live progress
# ---------------------------------------------------------------------------


class BenchLiveProgress:
    def __init__(self, tool_names: list[str], iterations: int) -> None:
        self.tool_names = tool_names
        self.iterations = iterations
        self.completed: dict[str, int] = {n: 0 for n in tool_names}
        self.p50s: dict[str, float | None] = {n: None for n in tool_names}
        self.current: str | None = None
        self._frame = 0
        self._start = time.monotonic()
        self._current_start: float | None = None

    def set_current(self, name: str | None) -> None:
        self.current = name
        self._current_start = time.monotonic() if name else None

    def set_call_count(self, name: str, count: int) -> None:
        self.completed[name] = count

    def set_p50(self, name: str, p50: float) -> None:
        self.p50s[name] = p50

    def render(self) -> Group:
        self._frame += 1
        spinner = _SPINNER_FRAMES[self._frame % len(_SPINNER_FRAMES)]
        done_tools = sum(1 for n in self.tool_names if self.p50s[n] is not None)
        total_tools = len(self.tool_names)
        elapsed_total = time.monotonic() - self._start
        header = Text(f"  {spinner} Benchmarking {done_tools}/{total_tools} tools · {elapsed_total:.1f}s\n")
        lines: list[Text] = [header]

        for name in self.tool_names:
            calls = self.completed.get(name, 0)
            p50 = self.p50s.get(name)
            line = Text(f"  {name:<24} ")

            if p50 is not None:
                line.append(f"{self.iterations}/{self.iterations} calls", style="dim")
                line.append("  ")
                line.append("✓", style="green")
                line.append(f"   p50: {p50:.0f}ms", style="dim")
            elif name == self.current:
                elapsed_item = time.monotonic() - self._current_start if self._current_start else 0
                line.append(f"{calls}/{self.iterations} calls", style="dim")
                line.append("  ")
                line.append(spinner, style="bold blue")
                line.append(f"  {elapsed_item:.1f}s", style="dim")
            else:
                line.append("waiting...", style="dim")

            lines.append(line)

        lines.append(Text(""))
        return Group(*lines)

    def __rich__(self) -> Group:
        return self.render()


# ---------------------------------------------------------------------------
# Bench: Phase 3 final report
# ---------------------------------------------------------------------------


def render_bench_report(console: Console, report: BenchReport) -> None:
    server_line = "unknown"
    if report.server_info:
        server_line = f"{report.server_info.name} v{report.server_info.version}"

    panel_content = (
        f"\n"
        f"  Server:     [bold]{server_line}[/bold]\n"
        f"  Transport:  {report.transport}\n"
        f"  Tools:      {report.benchmarked_count} of {report.tool_count} benchmarked"
        f" · {report.iterations} iterations each"
        f" · {report.total_calls} total calls\n"
    )

    console.print(
        Panel(
            panel_content,
            title=f"[bold]mcp-halflist bench v{report.version}[/bold]",
            border_style="blue",
            expand=True,
        )
    )
    console.print()

    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table.add_column("Tool", style="bold", min_width=20)
    table.add_column("p50", justify="right", min_width=8)
    table.add_column("p95", justify="right", min_width=8)
    table.add_column("p99", justify="right", min_width=8)
    table.add_column("min", justify="right", min_width=8)
    table.add_column("max", justify="right", min_width=8)

    for bm in report.benchmarks:
        if bm.errors == bm.iterations:
            table.add_row(bm.tool_name, "[red]all failed[/red]", "", "", "", "")
        else:
            p99c = _latency_color(bm.p99_ms)
            table.add_row(
                bm.tool_name,
                f"{bm.median_ms:.0f}ms",
                f"{bm.p95_ms:.0f}ms",
                f"[{p99c}]{bm.p99_ms:.0f}ms[/{p99c}]",
                f"{bm.min_ms:.0f}ms",
                f"{bm.max_ms:.0f}ms",
            )

    console.print(table)
    console.print()

    conn = report.connection_ms
    disc = report.discovery_ms
    total = report.total_duration_ms / 1000
    console.print(f"  {'─' * 56}")
    console.print(f"  Connection: {conn:.0f}ms · Discovery: {disc:.0f}ms · Total: {total:.1f}s")
    console.print()


def render_bench_json(report: BenchReport) -> str:
    return report.model_dump_json(indent=2)


# ---------------------------------------------------------------------------
# Audit: Phase 3 final report (check + bench combined)
# ---------------------------------------------------------------------------


def render_audit_report(console: Console, report: AuditReport, verbose: bool) -> None:
    score = report.score
    sc = _score_color(score)

    server_line = "unknown"
    if report.server_info:
        server_line = f"{report.server_info.name} v{report.server_info.version}"

    panel_content = (
        f"\n"
        f"  Server:     [bold]{server_line}[/bold]\n"
        f"  Transport:  {report.transport}\n"
        f"  Score:      [{sc}]{score}/100[/{sc}]  {_score_bar(score)}  {score}%\n"
        f"  Tools:      {report.benchmarked_count} of {report.tool_count} benchmarked"
        f" · {report.iterations} iterations each\n"
    )

    console.print(
        Panel(
            panel_content,
            title=f"[bold]mcp-halflist audit v{report.version}[/bold]",
            border_style="blue",
            expand=True,
        )
    )
    console.print()

    for suite in report.suites:
        _render_suite(console, suite, verbose)

    total_check_dur = sum(s.duration_ms for s in report.suites) / 1000
    console.print(f"  {'─' * 56}")
    parts: list[str] = []
    if report.total_passed > 0:
        parts.append(f"[green]{report.total_passed} passed[/green]")
    if report.total_failed > 0:
        parts.append(f"[red]{report.total_failed} failed[/red]")
    if report.total_warned > 0:
        w = report.total_warned
        parts.append(f"[yellow]{w} warning{'s' if w != 1 else ''}[/yellow]")
    parts.append(f"{total_check_dur:.1f}s")
    console.print(f"  {' · '.join(parts)}")
    console.print()

    if report.benchmarks:
        console.print("  [bold]Benchmarks[/bold]")
        console.print()

        table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
        table.add_column("Tool", style="bold", min_width=20)
        table.add_column("p50", justify="right", min_width=8)
        table.add_column("p95", justify="right", min_width=8)
        table.add_column("p99", justify="right", min_width=8)
        table.add_column("min", justify="right", min_width=8)
        table.add_column("max", justify="right", min_width=8)

        for bm in report.benchmarks:
            if bm.errors == bm.iterations:
                table.add_row(bm.tool_name, "[red]all failed[/red]", "", "", "", "")
            else:
                p99c = _latency_color(bm.p99_ms)
                table.add_row(
                    bm.tool_name,
                    f"{bm.median_ms:.0f}ms",
                    f"{bm.p95_ms:.0f}ms",
                    f"[{p99c}]{bm.p99_ms:.0f}ms[/{p99c}]",
                    f"{bm.min_ms:.0f}ms",
                    f"{bm.max_ms:.0f}ms",
                )

        console.print(table)
        console.print()

    conn = report.connection_ms
    disc = report.discovery_ms
    total = report.total_duration_ms / 1000
    console.print(f"  {'─' * 56}")
    console.print(f"  Connection: {conn:.0f}ms · Discovery: {disc:.0f}ms · Total: {total:.1f}s")
    console.print()


def render_audit_json(report: AuditReport) -> str:
    return report.model_dump_json(indent=2)


# ---------------------------------------------------------------------------
# Markdown report generation
# ---------------------------------------------------------------------------


def render_check_markdown(data: dict[str, Any]) -> str:
    server = data.get("server_info") or {}
    name = server.get("name", "unknown")
    version = server.get("version", "?")
    score = data.get("score", 0)
    ts = data.get("timestamp", "")
    if "T" in ts:
        ts = ts.split("T")[0] + " " + ts.split("T")[1][:8]

    lines = [
        "# MCP Conformance Report",
        "",
        f"**Server:** {name} v{version}",
        f"**Score:** {score}/100",
        f"**Date:** {ts}",
        "",
        "## Results",
        "",
        "| Suite | Passed | Failed | Warnings | Duration |",
        "|-------|--------|--------|----------|----------|",
    ]

    for s in data.get("suites", []):
        dur = s.get("duration_ms", 0) / 1000
        lines.append(
            f"| {s['name']} | {s['passed']} | {s['failed']} | {s['warned']} | {dur:.1f}s |"
        )

    total_p = data.get("total_passed", 0)
    total_f = data.get("total_failed", 0)
    total_w = data.get("total_warned", 0)
    total_d = data.get("total_duration_ms", 0) / 1000
    lines.append("")
    lines.append(f"**Total:** {total_p} passed · {total_f} failed · {total_w} warning · {total_d:.1f}s")
    return "\n".join(lines) + "\n"


def render_bench_markdown(data: dict[str, Any]) -> str:
    server = data.get("server_info") or {}
    name = server.get("name", "unknown")
    version = server.get("version", "?")
    ts = data.get("timestamp", "")
    if "T" in ts:
        ts = ts.split("T")[0] + " " + ts.split("T")[1][:8]

    bc = data.get("benchmarked_count", 0)
    tc = data.get("tool_count", 0)
    iters = data.get("iterations", 0)

    lines = [
        "# MCP Benchmark Report",
        "",
        f"**Server:** {name} v{version}",
        f"**Tools:** {bc} of {tc} benchmarked · {iters} iterations each",
        f"**Date:** {ts}",
        "",
        "## Latency (ms)",
        "",
        "| Tool | p50 | p95 | p99 | min | max |",
        "|------|-----|-----|-----|-----|-----|",
    ]

    for bm in data.get("benchmarks", []):
        lines.append(
            f"| {bm['tool_name']} | {bm['median_ms']:.0f} | {bm['p95_ms']:.0f}"
            f" | {bm['p99_ms']:.0f} | {bm['min_ms']:.0f} | {bm['max_ms']:.0f} |"
        )

    conn = data.get("connection_ms", 0)
    disc = data.get("discovery_ms", 0)
    total = data.get("total_duration_ms", 0) / 1000
    lines.append("")
    lines.append(f"**Connection:** {conn:.0f}ms · **Discovery:** {disc:.0f}ms · **Total:** {total:.1f}s")
    return "\n".join(lines) + "\n"


def render_audit_markdown(data: dict[str, Any]) -> str:
    server = data.get("server_info") or {}
    name = server.get("name", "unknown")
    version = server.get("version", "?")
    score = data.get("score", 0)
    ts = data.get("timestamp", "")
    if "T" in ts:
        ts = ts.split("T")[0] + " " + ts.split("T")[1][:8]

    bc = data.get("benchmarked_count", 0)
    tc = data.get("tool_count", 0)
    iters = data.get("iterations", 0)

    lines = [
        "# MCP Audit Report",
        "",
        f"**Server:** {name} v{version}",
        f"**Score:** {score}/100",
        f"**Tools:** {bc} of {tc} benchmarked · {iters} iterations each",
        f"**Date:** {ts}",
        "",
        "## Conformance",
        "",
        "| Suite | Passed | Failed | Warnings | Duration |",
        "|-------|--------|--------|----------|----------|",
    ]

    for s in data.get("suites", []):
        dur = s.get("duration_ms", 0) / 1000
        lines.append(
            f"| {s['name']} | {s['passed']} | {s['failed']} | {s['warned']} | {dur:.1f}s |"
        )

    total_p = data.get("total_passed", 0)
    total_f = data.get("total_failed", 0)
    total_w = data.get("total_warned", 0)
    lines.append("")
    lines.append(f"**Total:** {total_p} passed · {total_f} failed · {total_w} warnings")
    lines.append("")
    lines.append("## Latency (ms)")
    lines.append("")
    lines.append("| Tool | p50 | p95 | p99 | min | max |")
    lines.append("|------|-----|-----|-----|-----|-----|")

    for bm in data.get("benchmarks", []):
        lines.append(
            f"| {bm['tool_name']} | {bm['median_ms']:.0f} | {bm['p95_ms']:.0f}"
            f" | {bm['p99_ms']:.0f} | {bm['min_ms']:.0f} | {bm['max_ms']:.0f} |"
        )

    conn = data.get("connection_ms", 0)
    disc = data.get("discovery_ms", 0)
    total = data.get("total_duration_ms", 0) / 1000
    lines.append("")
    lines.append(f"**Connection:** {conn:.0f}ms · **Discovery:** {disc:.0f}ms · **Total:** {total:.1f}s")
    return "\n".join(lines) + "\n"


def detect_report_type(data: dict[str, Any]) -> str:
    has_suites = "suites" in data
    has_benchmarks = "benchmarks" in data
    if has_suites and has_benchmarks:
        return "audit"
    if has_suites:
        return "check"
    if has_benchmarks:
        return "bench"
    return "unknown"


# ---------------------------------------------------------------------------
# SVG badge generation
# ---------------------------------------------------------------------------

_BADGE_TEMPLATE = """\
<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="20">
  <linearGradient id="b" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="a">
    <rect width="{width}" height="20" rx="3" fill="#fff"/>
  </clipPath>
  <g clip-path="url(#a)">
    <rect width="{label_width}" height="20" fill="#555"/>
    <rect x="{label_width}" width="{value_width}" height="20" fill="{color}"/>
    <rect width="{width}" height="20" fill="url(#b)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11">
    <text x="{label_x}" y="15" fill="#010101" fill-opacity=".3">{label}</text>
    <text x="{label_x}" y="14">{label}</text>
    <text x="{value_x}" y="15" fill="#010101" fill-opacity=".3">{value}</text>
    <text x="{value_x}" y="14">{value}</text>
  </g>
</svg>"""


def render_badge_svg(data: dict[str, Any]) -> str:
    report_type = detect_report_type(data)

    if report_type in ("check", "audit"):
        label = "MCP"
        score = data.get("score", 0)
        value = f"{score}/100"
        if score >= 80:
            color = "#4c1"
        elif score >= 50:
            color = "#dfb317"
        else:
            color = "#e05d44"
    elif report_type == "bench":
        label = "MCP bench"
        benchmarks = data.get("benchmarks", [])
        bc = len(benchmarks)
        if benchmarks:
            avg_p50 = sum(b["median_ms"] for b in benchmarks) / bc
            value = f"{bc} tools · p50 avg {avg_p50:.0f}ms"
        else:
            value = "no data"
        color = "#4c1"
    else:
        label = "MCP"
        value = "unknown"
        color = "#9f9f9f"

    label_width = len(label) * 7 + 10
    value_width = len(value) * 7 + 10
    width = label_width + value_width

    return _BADGE_TEMPLATE.format(
        width=width,
        label_width=label_width,
        value_width=value_width,
        label_x=label_width / 2,
        value_x=label_width + value_width / 2,
        label=label,
        value=value,
        color=color,
    )
