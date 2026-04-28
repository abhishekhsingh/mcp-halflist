from __future__ import annotations

from datetime import datetime, timezone

from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text

from halflist import __version__
from halflist.models import CheckResult, HalflistReport, ServerInfo, SuiteResult

STATUS_SYMBOLS = {
    "PASS": ("✓", "green"),
    "FAIL": ("✗", "red"),
    "WARN": ("⚠", "yellow"),
    "SKIP": ("—", "dim"),
}

DOT_LEADER_WIDTH = 52


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


def print_connection(console: Console, server_info: ServerInfo, tool_count: int) -> None:
    console.print(
        f"  [green]✓[/green] Connected to [bold]{server_info.name}[/bold] v{server_info.version}"
    )
    console.print(f"    {tool_count} tools · 0 resources · 0 prompts")
    console.print()


# ---------------------------------------------------------------------------
# Phase 2: Live progress
# ---------------------------------------------------------------------------


class LiveProgress:
    """Tracks check results per suite and renders a live progress display."""

    def __init__(self, suite_names: list[str]) -> None:
        self.suite_names = suite_names
        self.checks: dict[str, list[str]] = {n: [] for n in suite_names}
        self.current: str | None = None

    def set_current(self, name: str | None) -> None:
        self.current = name

    def add_check(self, check: CheckResult) -> None:
        self.checks[check.suite].append(check.status)

    def render(self) -> Group:
        total_done = sum(len(v) for v in self.checks.values())

        header = Text(f"  Running checks... {total_done} completed\n")
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
                line.append("running...", style="bold blue")
            elif statuses:
                line.append(f"{len(statuses)}/{len(statuses)}", style="dim")

            lines.append(line)

        lines.append(Text(""))
        return Group(*lines)


# ---------------------------------------------------------------------------
# Phase 3: Final report
# ---------------------------------------------------------------------------


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
