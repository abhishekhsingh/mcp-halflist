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
        f"  [green]✓[/green] Connected to [bold]{server_info.name}[/bold]"
        f" v{server_info.version} · {tool_count} tools discovered"
    )
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


def _fmt_ms(ms: float) -> str:
    if ms < 1.0:
        return "<1ms"
    return f"{ms:.0f}ms"


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


def render_final_report(
    console: Console, report: HalflistReport, verbose: bool, *, is_filtered: bool = False,
) -> None:
    server_line = "unknown"
    if report.server_info:
        server_line = f"{report.server_info.name} v{report.server_info.version}"

    if is_filtered:
        panel_content = (
            f"  Server:     [bold]{server_line}[/bold]\n"
            f"  Transport:  {report.transport}\n"
            f"  [dim](score suppressed — filtered suite run)[/dim]"
        )
    else:
        score = report.score
        sc = _score_color(score)
        panel_content = (
            f"  Server:     [bold]{server_line}[/bold]\n"
            f"  Transport:  {report.transport}\n"
            f"  Score:      [{sc}]{score}/100[/{sc}]  {_score_bar(score)}  [{sc}]{score}%[/{sc}]"
        )

    console.print(
        Panel(
            panel_content,
            title=f"[bold]mcp-halflist v{report.version}[/bold]",
            subtitle="[dim]Lint your MCP server before your users do.[/dim]",
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

    if is_filtered:
        if report.total_failed > 0:
            console.print("\n  [bold red]FAIL[/bold red]")
        else:
            console.print("\n  [bold green]PASS[/bold green]")
    else:
        if report.total_failed > 0:
            console.print(f"\n  [bold red]FAIL[/bold red] Score: {report.score}/100")
        else:
            console.print(f"\n  [bold green]PASS[/bold green] Score: {report.score}/100")
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
        self.skipped: set[str] = set()
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

    def set_skipped(self, name: str) -> None:
        self.skipped.add(name)

    def render(self) -> Group:
        self._frame += 1
        spinner = _SPINNER_FRAMES[self._frame % len(_SPINNER_FRAMES)]
        done_tools = sum(1 for n in self.tool_names if self.p50s[n] is not None or n in self.skipped)
        total_tools = len(self.tool_names)
        elapsed_total = time.monotonic() - self._start
        header = Text(f"  {spinner} Benchmarking {done_tools}/{total_tools} tools · {elapsed_total:.1f}s\n")
        lines: list[Text] = [header]

        for name in self.tool_names:
            calls = self.completed.get(name, 0)
            p50 = self.p50s.get(name)
            line = Text(f"  {name:<24} ")

            if name in self.skipped:
                line.append("── skipped (args rejected)", style="dim")
            elif p50 is not None:
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
        f"  Server:     [bold]{server_line}[/bold]\n"
        f"  Transport:  {report.transport}\n"
        f"  Tools:      {report.benchmarked_count} of {report.tool_count} benchmarked"
        f" · {report.iterations} iterations each"
        f" · {report.total_calls} total calls"
    )

    console.print(
        Panel(
            panel_content,
            title=f"[bold]mcp-halflist v{report.version}[/bold]",
            subtitle="[dim]Lint your MCP server before your users do.[/dim]",
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

    skipped_count = 0
    benchmarked_count = 0
    for bm in report.benchmarks:
        if bm.skipped:
            skipped_count += 1
            table.add_row(
                f"[dim]{bm.tool_name}[/dim]",
                "[dim]skipped (args rejected)[/dim]", "", "", "", "",
            )
        elif bm.errors == bm.iterations:
            benchmarked_count += 1
            table.add_row(bm.tool_name, "[red]all failed[/red]", "", "", "", "")
        else:
            benchmarked_count += 1
            p99c = _latency_color(bm.p99_ms)
            table.add_row(
                bm.tool_name,
                _fmt_ms(bm.median_ms),
                _fmt_ms(bm.p95_ms),
                f"[{p99c}]{_fmt_ms(bm.p99_ms)}[/{p99c}]",
                _fmt_ms(bm.min_ms),
                _fmt_ms(bm.max_ms),
            )

    console.print(table)
    console.print()

    conn = report.connection_ms
    disc = report.discovery_ms
    total = report.total_duration_ms / 1000
    console.print(f"  {'─' * 56}")
    summary_parts: list[str] = [f"{benchmarked_count} benchmarked"]
    if skipped_count > 0:
        summary_parts.append(f"[dim]{skipped_count} skipped (args rejected)[/dim]")
    summary_parts.append(f"{total:.1f}s")
    console.print(f"  {' · '.join(summary_parts)}")
    console.print(f"  Connection: {conn:.0f}ms · Discovery: {disc:.0f}ms")
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
        f"  Server:     [bold]{server_line}[/bold]\n"
        f"  Transport:  {report.transport}\n"
        f"  Score:      [{sc}]{score}/100[/{sc}]  {_score_bar(score)}  [{sc}]{score}%[/{sc}]\n"
        f"  Tools:      {report.benchmarked_count} of {report.tool_count} benchmarked"
        f" · {report.iterations} iterations each"
    )

    console.print(
        Panel(
            panel_content,
            title=f"[bold]mcp-halflist v{report.version}[/bold]",
            subtitle="[dim]Lint your MCP server before your users do.[/dim]",
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

        audit_skipped = 0
        audit_benched = 0
        for bm in report.benchmarks:
            if bm.skipped:
                audit_skipped += 1
                table.add_row(
                    f"[dim]{bm.tool_name}[/dim]",
                    "[dim]skipped (args rejected)[/dim]", "", "", "", "",
                )
            elif bm.errors == bm.iterations:
                audit_benched += 1
                table.add_row(bm.tool_name, "[red]all failed[/red]", "", "", "", "")
            else:
                audit_benched += 1
                p99c = _latency_color(bm.p99_ms)
                table.add_row(
                    bm.tool_name,
                    _fmt_ms(bm.median_ms),
                    _fmt_ms(bm.p95_ms),
                    f"[{p99c}]{_fmt_ms(bm.p99_ms)}[/{p99c}]",
                    _fmt_ms(bm.min_ms),
                    _fmt_ms(bm.max_ms),
                )

        console.print(table)
        console.print()

        bench_summary_parts: list[str] = [f"{audit_benched} benchmarked"]
        if audit_skipped > 0:
            bench_summary_parts.append(f"[dim]{audit_skipped} skipped (args rejected)[/dim]")
        console.print(f"  {' · '.join(bench_summary_parts)}")
        console.print()

    conn = report.connection_ms
    disc = report.discovery_ms
    total = report.total_duration_ms / 1000
    console.print(f"  {'─' * 56}")
    console.print(f"  Connection: {conn:.0f}ms · Discovery: {disc:.0f}ms · Total: {total:.1f}s")

    if report.total_failed > 0:
        console.print(f"\n  [bold red]FAIL[/bold red] Score: {score}/100")
    else:
        console.print(f"\n  [bold green]PASS[/bold green] Score: {score}/100")
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

    def _md_ms(v: float) -> str:
        return "<1" if v < 1.0 else f"{v:.0f}"

    for bm in data.get("benchmarks", []):
        if bm.get("skipped"):
            lines.append(f"| {bm['tool_name']} | *skipped (args rejected)* | | | | |")
        else:
            lines.append(
                f"| {bm['tool_name']} | {_md_ms(bm['median_ms'])} | {_md_ms(bm['p95_ms'])}"
                f" | {_md_ms(bm['p99_ms'])} | {_md_ms(bm['min_ms'])} | {_md_ms(bm['max_ms'])} |"
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

    def _md_ms(v: float) -> str:
        return "<1" if v < 1.0 else f"{v:.0f}"

    for bm in data.get("benchmarks", []):
        if bm.get("skipped"):
            lines.append(f"| {bm['tool_name']} | *skipped (args rejected)* | | | | |")
        else:
            lines.append(
                f"| {bm['tool_name']} | {_md_ms(bm['median_ms'])} | {_md_ms(bm['p95_ms'])}"
                f" | {_md_ms(bm['p99_ms'])} | {_md_ms(bm['min_ms'])} | {_md_ms(bm['max_ms'])} |"
            )

    conn = data.get("connection_ms", 0)
    disc = data.get("discovery_ms", 0)
    total = data.get("total_duration_ms", 0) / 1000
    lines.append("")
    lines.append(f"**Connection:** {conn:.0f}ms · **Discovery:** {disc:.0f}ms · **Total:** {total:.1f}s")
    return "\n".join(lines) + "\n"


def _html_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>mcp-halflist — {title}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  background:#0d1117;color:#c9d1d9;line-height:1.5;padding:2rem}}
.container{{max-width:900px;margin:0 auto}}
h1{{font-size:1.5rem;margin-bottom:.25rem}}
.subtitle{{color:#8b949e;font-size:.875rem;margin-bottom:1.5rem}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:1.25rem;margin-bottom:1rem}}
.card h2{{font-size:1.1rem;margin-bottom:.75rem;color:#e6edf3}}
.meta-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:.5rem .75rem;margin-bottom:1rem}}
.meta-item{{font-size:.875rem}}.meta-label{{color:#8b949e}}.meta-value{{color:#e6edf3;font-weight:600}}
.gauge-wrap{{display:flex;align-items:center;gap:1.5rem;margin-bottom:1rem}}
.gauge{{position:relative;width:100px;height:100px}}
.gauge svg{{transform:rotate(-90deg)}}
.gauge-bg{{fill:none;stroke:#30363d;stroke-width:8}}
.gauge-fg{{fill:none;stroke-width:8;stroke-linecap:round;transition:stroke-dashoffset .6s ease}}
.gauge-text{{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
  font-size:1.5rem;font-weight:700}}
.verdict{{font-size:1.25rem;font-weight:700}}
.pass{{color:#3fb950}}.fail{{color:#f85149}}.warn{{color:#d29922}}.skip{{color:#8b949e}}
details{{margin-bottom:.5rem}}
summary{{cursor:pointer;padding:.5rem .75rem;background:#21262d;border-radius:6px;
  font-weight:600;font-size:.9rem;list-style:none}}
summary::-webkit-details-marker{{display:none}}
summary::before{{content:"\\25B6";display:inline-block;margin-right:.5rem;font-size:.7rem;
  transition:transform .15s}}
details[open]>summary::before{{transform:rotate(90deg)}}
.check-list{{padding:.5rem .75rem}}
.check-row{{display:flex;align-items:baseline;gap:.5rem;padding:.25rem 0;font-size:.875rem;
  border-bottom:1px solid #21262d}}
.check-row:last-child{{border-bottom:none}}
.check-icon{{width:1.2em;text-align:center;flex-shrink:0}}
.check-name{{flex:1}}.check-msg{{color:#8b949e;text-align:right;max-width:50%;word-break:break-word}}
table{{width:100%;border-collapse:collapse;font-size:.875rem}}
th{{text-align:left;padding:.5rem .75rem;border-bottom:2px solid #30363d;color:#8b949e;font-weight:600}}
td{{padding:.5rem .75rem;border-bottom:1px solid #21262d}}
.bar-cell{{width:40%}}
.bar-wrap{{background:#21262d;border-radius:3px;height:18px;position:relative;overflow:hidden}}
.bar-fill{{height:100%;border-radius:3px;transition:width .4s ease}}
.bar-label{{position:absolute;right:6px;top:0;line-height:18px;font-size:.75rem;color:#e6edf3}}
.summary-row{{display:flex;gap:1.5rem;flex-wrap:wrap;font-size:.875rem;color:#8b949e;margin-top:.75rem}}
.footer{{text-align:center;color:#484f58;font-size:.75rem;margin-top:2rem}}
</style>
</head>
<body>
<div class="container">
<h1>mcp-halflist</h1>
<p class="subtitle">Lint your MCP server before your users do.</p>
{body}
<p class="footer">Generated by mcp-halflist v{version}</p>
</div>
</body>
</html>"""


def _score_color_hex(score: int) -> str:
    if score >= 80:
        return "#3fb950"
    if score >= 50:
        return "#d29922"
    return "#f85149"


def _score_gauge_svg(score: int) -> str:
    color = _score_color_hex(score)
    r = 42
    c = 2 * 3.14159 * r
    offset = c * (1 - score / 100)
    return (
        f'<div class="gauge"><svg viewBox="0 0 100 100">'
        f'<circle cx="50" cy="50" r="{r}" class="gauge-bg"/>'
        f'<circle cx="50" cy="50" r="{r}" class="gauge-fg" '
        f'stroke="{color}" stroke-dasharray="{c:.1f}" stroke-dashoffset="{offset:.1f}"/>'
        f'</svg><div class="gauge-text" style="color:{color}">{score}</div></div>'
    )


def _status_icon(status: str) -> str:
    if status == "PASS":
        return '<span class="check-icon pass">&#10003;</span>'
    if status == "FAIL":
        return '<span class="check-icon fail">&#10007;</span>'
    if status == "WARN":
        return '<span class="check-icon warn">&#9888;</span>'
    return '<span class="check-icon skip">&mdash;</span>'


def _render_suites_html(suites: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for s in suites:
        name = _html_escape(s["name"])
        passed = s["passed"]
        total = len(s.get("checks", []))
        dur = s.get("duration_ms", 0) / 1000
        summary_extra = ""
        if s.get("failed", 0) > 0:
            summary_extra += f' <span class="fail">&#10007; {s["failed"]}</span>'
        if s.get("warned", 0) > 0:
            summary_extra += f' <span class="warn">&#9888; {s["warned"]}</span>'

        checks_html = ""
        for c in s.get("checks", []):
            icon = _status_icon(c["status"])
            cname = _html_escape(c["name"])
            msg = _html_escape(c.get("message") or c["status"])
            checks_html += (
                f'<div class="check-row">{icon}'
                f'<span class="check-name">{cname}</span>'
                f'<span class="check-msg">{msg}</span></div>\n'
            )

        parts.append(
            f'<details><summary>{name} &mdash; {passed}/{total} passed'
            f' &middot; {dur:.1f}s{summary_extra}</summary>\n'
            f'<div class="check-list">{checks_html}</div></details>\n'
        )
    return "".join(parts)


def _latency_bar_color(ms: float) -> str:
    if ms > 1000:
        return "#f85149"
    if ms > 500:
        return "#d29922"
    return "#3fb950"


def _render_bench_table_html(benchmarks: list[dict[str, Any]]) -> str:
    if not benchmarks:
        return ""
    active = [b for b in benchmarks if not b.get("skipped")]
    max_p99 = max((b["p99_ms"] for b in active), default=1) or 1
    rows = ""

    def _h_ms(v: float) -> str:
        return "&lt;1ms" if v < 1.0 else f"{v:.0f}ms"

    for bm in benchmarks:
        name = _html_escape(bm["tool_name"])
        if bm.get("skipped"):
            rows += (
                f'<tr style="color:#8b949e"><td>{name}</td>'
                f'<td colspan="6" style="font-style:italic">skipped (args rejected)</td></tr>\n'
            )
            continue
        p50 = bm["median_ms"]
        p95 = bm["p95_ms"]
        p99 = bm["p99_ms"]
        pct = min(100, (p99 / max_p99) * 100)
        color = _latency_bar_color(p99)
        rows += (
            f"<tr><td>{name}</td><td>{_h_ms(p50)}</td><td>{_h_ms(p95)}</td>"
            f"<td>{_h_ms(p99)}</td><td>{_h_ms(bm['min_ms'])}</td><td>{_h_ms(bm['max_ms'])}</td>"
            f'<td class="bar-cell"><div class="bar-wrap">'
            f'<div class="bar-fill" style="width:{pct:.0f}%;background:{color}"></div>'
            f'<div class="bar-label">{p99:.0f}ms</div></div></td></tr>\n'
        )
    return (
        "<table><thead><tr><th>Tool</th><th>p50</th><th>p95</th><th>p99</th>"
        "<th>min</th><th>max</th><th>p99 bar</th></tr></thead><tbody>\n"
        + rows + "</tbody></table>\n"
    )


def render_check_html(data: dict[str, Any]) -> str:
    server = data.get("server_info") or {}
    name = _html_escape(server.get("name", "unknown"))
    version = _html_escape(server.get("version", "?"))
    score = data.get("score", 0)
    total_dur = data.get("total_duration_ms", 0) / 1000

    verdict_cls = "pass" if data.get("total_failed", 0) == 0 else "fail"
    verdict_word = "PASS" if verdict_cls == "pass" else "FAIL"

    body = f'<div class="card"><div class="gauge-wrap">{_score_gauge_svg(score)}\n'
    body += f'<div><div class="verdict {verdict_cls}">{verdict_word}</div>\n'
    body += f'<div class="meta-item"><span class="meta-value">{name}</span> v{version}</div>\n'
    body += f'<div class="meta-item">{total_dur:.1f}s total</div></div></div>\n'
    body += '<div class="meta-grid">'
    body += f'<div class="meta-item"><span class="meta-label">Transport:</span> <span class="meta-value">{data.get("transport", "stdio")}</span></div>'
    body += f'<div class="meta-item"><span class="meta-label">Passed:</span> <span class="meta-value pass">{data.get("total_passed", 0)}</span></div>'
    body += f'<div class="meta-item"><span class="meta-label">Failed:</span> <span class="meta-value fail">{data.get("total_failed", 0)}</span></div>'
    body += f'<div class="meta-item"><span class="meta-label">Warnings:</span> <span class="meta-value warn">{data.get("total_warned", 0)}</span></div>'
    body += '</div></div>\n'

    body += '<div class="card"><h2>Suites</h2>\n'
    body += _render_suites_html(data.get("suites", []))
    body += '</div>\n'

    return _HTML_TEMPLATE.format(
        title=f"{name} — Conformance",
        body=body,
        version=data.get("version", "?"),
    )


def render_bench_html(data: dict[str, Any]) -> str:
    server = data.get("server_info") or {}
    name = _html_escape(server.get("name", "unknown"))
    version = _html_escape(server.get("version", "?"))
    total_dur = data.get("total_duration_ms", 0) / 1000

    body = f'<div class="card"><h2>{name} v{version} &mdash; Benchmark</h2>\n'
    body += '<div class="meta-grid">'
    body += f'<div class="meta-item"><span class="meta-label">Transport:</span> <span class="meta-value">{data.get("transport", "stdio")}</span></div>'
    body += f'<div class="meta-item"><span class="meta-label">Tools:</span> <span class="meta-value">{data.get("benchmarked_count", 0)} of {data.get("tool_count", 0)}</span></div>'
    body += f'<div class="meta-item"><span class="meta-label">Iterations:</span> <span class="meta-value">{data.get("iterations", 0)}</span></div>'
    body += f'<div class="meta-item"><span class="meta-label">Connection:</span> <span class="meta-value">{data.get("connection_ms", 0):.0f}ms</span></div>'
    body += f'<div class="meta-item"><span class="meta-label">Total:</span> <span class="meta-value">{total_dur:.1f}s</span></div>'
    body += '</div></div>\n'

    body += '<div class="card"><h2>Latency per Tool</h2>\n'
    body += _render_bench_table_html(data.get("benchmarks", []))
    body += '</div>\n'

    return _HTML_TEMPLATE.format(
        title=f"{name} — Benchmark",
        body=body,
        version=data.get("version", "?"),
    )


def render_audit_html(data: dict[str, Any]) -> str:
    server = data.get("server_info") or {}
    name = _html_escape(server.get("name", "unknown"))
    version = _html_escape(server.get("version", "?"))
    score = data.get("score", 0)
    total_dur = data.get("total_duration_ms", 0) / 1000

    verdict_cls = "pass" if data.get("total_failed", 0) == 0 else "fail"
    verdict_word = "PASS" if verdict_cls == "pass" else "FAIL"

    body = f'<div class="card"><div class="gauge-wrap">{_score_gauge_svg(score)}\n'
    body += f'<div><div class="verdict {verdict_cls}">{verdict_word}</div>\n'
    body += f'<div class="meta-item"><span class="meta-value">{name}</span> v{version}</div>\n'
    body += f'<div class="meta-item">{total_dur:.1f}s total</div></div></div>\n'
    body += '<div class="meta-grid">'
    body += f'<div class="meta-item"><span class="meta-label">Transport:</span> <span class="meta-value">{data.get("transport", "stdio")}</span></div>'
    body += f'<div class="meta-item"><span class="meta-label">Passed:</span> <span class="meta-value pass">{data.get("total_passed", 0)}</span></div>'
    body += f'<div class="meta-item"><span class="meta-label">Failed:</span> <span class="meta-value fail">{data.get("total_failed", 0)}</span></div>'
    body += f'<div class="meta-item"><span class="meta-label">Warnings:</span> <span class="meta-value warn">{data.get("total_warned", 0)}</span></div>'
    body += f'<div class="meta-item"><span class="meta-label">Tools:</span> <span class="meta-value">{data.get("benchmarked_count", 0)} of {data.get("tool_count", 0)}</span></div>'
    body += f'<div class="meta-item"><span class="meta-label">Iterations:</span> <span class="meta-value">{data.get("iterations", 0)}</span></div>'
    body += '</div></div>\n'

    body += '<div class="card"><h2>Conformance</h2>\n'
    body += _render_suites_html(data.get("suites", []))
    body += '</div>\n'

    if data.get("benchmarks"):
        body += '<div class="card"><h2>Latency per Tool</h2>\n'
        body += _render_bench_table_html(data.get("benchmarks", []))
        body += '</div>\n'

    return _HTML_TEMPLATE.format(
        title=f"{name} — Audit",
        body=body,
        version=data.get("version", "?"),
    )


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
