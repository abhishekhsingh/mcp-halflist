from __future__ import annotations

import asyncio
import io
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from halflist import __version__
from halflist.constants import EXIT_CONFIG_ERROR, EXIT_FAILURE, EXIT_OK, EXIT_TRANSPORT_ERROR

app = typer.Typer(
    name="halflist",
    help="CI-first conformance testing CLI for MCP servers.",
    add_completion=False,
    no_args_is_help=True,
)

console = Console()


def version_callback(value: bool) -> None:
    if value:
        console.print(
            f"[bold]halflist[/bold] v{__version__}"
            f" · [dim]Lint your MCP server before your users do.[/dim]"
        )
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None, "--version", callback=version_callback, is_eager=True, help="Print version and exit."
    ),
) -> None:
    pass


# ── check ──────────────────────────────────────────────────────────────────────


@app.command()
def check(
    stdio: str = typer.Option(..., "--stdio", help="Command to launch the MCP server via stdio."),
    format: str = typer.Option("terminal", "--format", help="Output format: terminal or json."),
    suite: Optional[list[str]] = typer.Option(None, "--suite", help="Suite(s) to run. Repeatable."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show all check details."),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress server stderr output. Auto-enabled with --format json."
    ),
    timeout: int = typer.Option(30, "--timeout", help="Timeout in seconds per operation."),
    verify_pins: bool = typer.Option(False, "--verify-pins", help="Verify tool pins against saved snapshot."),
) -> None:
    """Run conformance checks against an MCP server."""
    if format not in ("terminal", "json"):
        console.print(f"[red]Error:[/red] Unknown format '{format}'. Use 'terminal' or 'json'.")
        raise typer.Exit(EXIT_CONFIG_ERROR)

    effective_quiet = quiet or format == "json"
    exit_code = asyncio.run(
        _run_checks(stdio, format, suite, verbose, effective_quiet, timeout, verify_pins)
    )
    raise typer.Exit(exit_code)


async def _run_checks(
    command: str,
    format: str,
    suite_filter: list[str] | None,
    verbose: bool,
    quiet: bool,
    timeout: int,
    verify_pins: bool = False,
) -> int:
    from rich.live import Live

    from halflist.client import HalflistClient
    from halflist.models import SuiteResult
    from halflist.report import (
        LiveProgress,
        build_report,
        print_connection,
        render_final_report,
        render_json,
    )
    from halflist.suites.handshake import HandshakeSuite
    from halflist.suites.security import SecuritySuite
    from halflist.suites.tools import ToolsSuite

    is_json = format == "json"
    progress_console = Console(stderr=True) if is_json and sys.stderr.isatty() else Console(file=io.StringIO()) if is_json else console
    client = HalflistClient(timeout=timeout, quiet=quiet)

    try:
        # ── Phase 1: Connection (spinner) ──────────────────────────────────
        with progress_console.status("[bold blue]Connecting to server via stdio...[/bold blue]"):
            try:
                await client.connect_stdio(command)
                server_info = await client.initialize()
            except Exception as e:
                if is_json:
                    import json

                    err = {"error": str(e), "exit_code": EXIT_TRANSPORT_ERROR}
                    print(json.dumps(err, indent=2))
                else:
                    console.print(f"\n  [red]✗[/red] Connection failed: {e}")
                return EXIT_TRANSPORT_ERROR

        try:
            tools = await client.list_tools()
        except Exception:
            tools = []

        print_connection(progress_console, server_info, len(tools))

        all_suites_map: dict[str, type] = {
            "handshake": HandshakeSuite,
            "tools": ToolsSuite,
            "security": SecuritySuite,
        }

        if suite_filter:
            for s in suite_filter:
                if s not in all_suites_map:
                    progress_console.print(f"[red]Error:[/red] Unknown suite '{s}'")
                    return EXIT_CONFIG_ERROR
            suites_to_run = {k: v for k, v in all_suites_map.items() if k in suite_filter}
        else:
            suites_to_run = all_suites_map

        suite_results: list[SuiteResult] = []

        # ── Phase 2: Live progress ─────────────────────────────────────────
        progress = LiveProgress(list(suites_to_run.keys()))

        with Live(
            progress, console=progress_console, transient=True, refresh_per_second=12
        ) as live:
            for name, suite_cls in suites_to_run.items():
                progress.set_current(name)
                live.refresh()

                def on_check(check, _live=live, _progress=progress):  # type: ignore[assignment]
                    _progress.add_check(check)
                    _live.refresh()

                if suite_cls is SecuritySuite:
                    suite_instance = SecuritySuite(
                        client, on_check=on_check, verify_pins=verify_pins
                    )
                else:
                    suite_instance = suite_cls(client, on_check=on_check)
                result = await suite_instance.run()
                suite_results.append(result)

            progress.set_current(None)
            live.refresh()

        report = build_report(server_info, suite_results)

        # ── Phase 3: Final report ──────────────────────────────────────────
        if is_json:
            print(render_json(report))
        else:
            render_final_report(console, report, verbose, is_filtered=bool(suite_filter))

        if report.total_failed > 0:
            return EXIT_FAILURE
        return EXIT_OK
    finally:
        await client.close()


# ── bench ──────────────────────────────────────────────────────────────────────


@app.command()
def bench(
    stdio: str = typer.Option(..., "--stdio", help="Command to launch the MCP server via stdio."),
    tool: Optional[list[str]] = typer.Option(None, "--tool", help="Tool(s) to benchmark. Repeatable."),
    all_tools: bool = typer.Option(False, "--all", help="Benchmark all tools (default: first 5)."),
    iterations: int = typer.Option(10, "--iterations", "-n", help="Number of iterations per tool."),
    warmup: int = typer.Option(2, "--warmup", "-w", help="Warmup iterations (discarded)."),
    format: str = typer.Option("terminal", "--format", help="Output format: terminal or json."),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress server stderr output. Auto-enabled with --format json."
    ),
    timeout: int = typer.Option(30, "--timeout", help="Timeout in seconds per operation."),
) -> None:
    """Benchmark latency per tool on an MCP server."""
    if format not in ("terminal", "json"):
        console.print(f"[red]Error:[/red] Unknown format '{format}'. Use 'terminal' or 'json'.")
        raise typer.Exit(EXIT_CONFIG_ERROR)

    effective_quiet = quiet or format == "json"
    exit_code = asyncio.run(
        _run_bench(stdio, tool, all_tools, iterations, warmup, format, effective_quiet, timeout)
    )
    raise typer.Exit(exit_code)


async def _run_bench(
    command: str,
    tool_names: list[str] | None,
    bench_all: bool,
    iterations: int,
    warmup: int,
    format: str,
    quiet: bool,
    timeout: int,
) -> int:
    import time

    from rich.live import Live

    from halflist.bench import bench_tool, select_tools
    from halflist.client import HalflistClient
    from halflist.models import BenchReport, ToolBenchmark
    from halflist.report import BenchLiveProgress, print_connection, render_bench_json, render_bench_report

    is_json = format == "json"
    progress_console = Console(stderr=True) if is_json and sys.stderr.isatty() else Console(file=io.StringIO()) if is_json else console
    client = HalflistClient(timeout=timeout, quiet=quiet)

    try:
        # ── Phase 1: Connection ────────────────────────────────────────────
        with progress_console.status("[bold blue]Connecting to server via stdio...[/bold blue]"):
            try:
                t0 = time.monotonic()
                await client.connect_stdio(command)
                server_info = await client.initialize()
                connection_ms = (time.monotonic() - t0) * 1000
            except Exception as e:
                if is_json:
                    import json

                    err = {"error": str(e), "exit_code": EXIT_TRANSPORT_ERROR}
                    print(json.dumps(err, indent=2))
                else:
                    console.print(f"\n  [red]✗[/red] Connection failed: {e}")
                return EXIT_TRANSPORT_ERROR

        t_disc = time.monotonic()
        try:
            all_tool_list = await client.list_tools()
        except Exception:
            all_tool_list = []
        discovery_ms = (time.monotonic() - t_disc) * 1000

        selected = select_tools(all_tool_list, tool_names, bench_all)

        print_connection(progress_console, server_info, len(all_tool_list))

        if not selected:
            progress_console.print("  [yellow]No tools to benchmark.[/yellow]")
            return EXIT_OK

        # ── Phase 2: Benchmarking ──────────────────────────────────────────
        bench_start = time.monotonic()
        benchmarks: list[ToolBenchmark] = []

        progress = BenchLiveProgress(
            [t.name for t in selected], iterations
        )

        with Live(
            progress, console=progress_console, transient=True, refresh_per_second=12
        ) as live:
            for t in selected:
                progress.set_current(t.name)
                live.refresh()

                def on_call(count, _live=live, _prog=progress, _name=t.name):  # type: ignore[assignment]
                    _prog.set_call_count(_name, count)
                    _live.refresh()

                result = await bench_tool(client, t, iterations, warmup, on_call=on_call)
                benchmarks.append(result)
                if result.skipped:
                    progress.set_skipped(t.name)
                else:
                    progress.set_p50(t.name, result.median_ms)
                live.refresh()

            progress.set_current(None)
            live.refresh()

        total_duration = (time.monotonic() - bench_start) * 1000 + connection_ms + discovery_ms
        total_calls = sum(b.iterations for b in benchmarks if not b.skipped)

        report = BenchReport(
            version=__version__,
            timestamp=__import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ).isoformat(),
            server_info=server_info,
            transport="stdio",
            connection_ms=round(connection_ms, 2),
            discovery_ms=round(discovery_ms, 2),
            tool_count=len(all_tool_list),
            benchmarked_count=sum(1 for b in benchmarks if not b.skipped),
            iterations=iterations,
            warmup=warmup,
            benchmarks=benchmarks,
            total_calls=total_calls,
            total_duration_ms=round(total_duration, 2),
        )

        # ── Phase 3: Report ────────────────────────────────────────────────
        if is_json:
            print(render_bench_json(report))
        else:
            render_bench_report(console, report)

        return EXIT_OK
    finally:
        await client.close()


# ── audit ──────────────────────────────────────────────────────────────────────


@app.command()
def audit(
    stdio: str = typer.Option(..., "--stdio", help="Command to launch the MCP server via stdio."),
    iterations: int = typer.Option(10, "--iterations", "-n", help="Benchmark iterations per tool."),
    warmup: int = typer.Option(2, "--warmup", "-w", help="Warmup iterations (discarded)."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show all check details."),
    format: str = typer.Option("terminal", "--format", help="Output format: terminal or json."),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress server stderr output. Auto-enabled with --format json."
    ),
    timeout: int = typer.Option(30, "--timeout", help="Timeout in seconds per operation."),
    verify_pins: bool = typer.Option(False, "--verify-pins", help="Verify tool pins against saved snapshot."),
) -> None:
    """Run full conformance check + benchmark in one shot."""
    if format not in ("terminal", "json"):
        console.print(f"[red]Error:[/red] Unknown format '{format}'. Use 'terminal' or 'json'.")
        raise typer.Exit(EXIT_CONFIG_ERROR)

    effective_quiet = quiet or format == "json"
    exit_code = asyncio.run(
        _run_audit(stdio, iterations, warmup, verbose, format, effective_quiet, timeout, verify_pins)
    )
    raise typer.Exit(exit_code)


async def _run_audit(
    command: str,
    iterations: int,
    warmup: int,
    verbose: bool,
    format: str,
    quiet: bool,
    timeout: int,
    verify_pins: bool = False,
) -> int:
    import time
    from datetime import datetime, timezone

    from rich.live import Live

    from halflist.bench import bench_tool
    from halflist.client import HalflistClient
    from halflist.models import AuditReport, SuiteResult, ToolBenchmark
    from halflist.report import (
        BenchLiveProgress,
        LiveProgress,
        build_report,
        print_connection,
        render_audit_json,
        render_audit_report,
    )
    from halflist.suites.handshake import HandshakeSuite
    from halflist.suites.security import SecuritySuite
    from halflist.suites.tools import ToolsSuite

    is_json = format == "json"
    progress_console = Console(stderr=True) if is_json and sys.stderr.isatty() else Console(file=io.StringIO()) if is_json else console
    client = HalflistClient(timeout=timeout, quiet=quiet)

    try:
        # ── Phase 1: Connection ────────────────────────────────────────────
        with progress_console.status("[bold blue]Connecting to server via stdio...[/bold blue]"):
            try:
                t0 = time.monotonic()
                await client.connect_stdio(command)
                server_info = await client.initialize()
                connection_ms = (time.monotonic() - t0) * 1000
            except Exception as e:
                if is_json:
                    import json

                    err = {"error": str(e), "exit_code": EXIT_TRANSPORT_ERROR}
                    print(json.dumps(err, indent=2))
                else:
                    console.print(f"\n  [red]✗[/red] Connection failed: {e}")
                return EXIT_TRANSPORT_ERROR

        t_disc = time.monotonic()
        try:
            all_tools = await client.list_tools()
        except Exception:
            all_tools = []
        discovery_ms = (time.monotonic() - t_disc) * 1000

        print_connection(progress_console, server_info, len(all_tools))

        # ── Phase 2a: Conformance checks ───────────────────────────────────
        all_suites_map: dict[str, type] = {
            "handshake": HandshakeSuite,
            "tools": ToolsSuite,
            "security": SecuritySuite,
        }

        suite_results: list[SuiteResult] = []

        progress = LiveProgress(list(all_suites_map.keys()))

        with Live(
            progress, console=progress_console, transient=True, refresh_per_second=12
        ) as live:
            for name, suite_cls in all_suites_map.items():
                progress.set_current(name)
                live.refresh()

                def on_check(check, _live=live, _progress=progress):  # type: ignore[assignment]
                    _progress.add_check(check)
                    _live.refresh()

                if suite_cls is SecuritySuite:
                    suite_instance = SecuritySuite(
                        client, on_check=on_check, verify_pins=verify_pins
                    )
                else:
                    suite_instance = suite_cls(client, on_check=on_check)
                result = await suite_instance.run()
                suite_results.append(result)

            progress.set_current(None)
            live.refresh()

        check_report = build_report(server_info, suite_results)

        # ── Phase 2b: Benchmarking (all tools) ─────────────────────────────
        benchmarks: list[ToolBenchmark] = []

        if all_tools:
            bench_progress = BenchLiveProgress(
                [t.name for t in all_tools], iterations
            )

            with Live(
                bench_progress, console=progress_console, transient=True, refresh_per_second=12
            ) as live:
                for t in all_tools:
                    bench_progress.set_current(t.name)
                    live.refresh()

                    def on_call(count, _live=live, _prog=bench_progress, _name=t.name):  # type: ignore[assignment]
                        _prog.set_call_count(_name, count)
                        _live.refresh()

                    bm_result = await bench_tool(client, t, iterations, warmup, on_call=on_call)
                    benchmarks.append(bm_result)
                    if bm_result.skipped:
                        bench_progress.set_skipped(t.name)
                    else:
                        bench_progress.set_p50(t.name, bm_result.median_ms)
                    live.refresh()

                bench_progress.set_current(None)
                live.refresh()

        total_duration = (time.monotonic() - t0) * 1000
        total_calls = sum(b.iterations for b in benchmarks if not b.skipped)

        report = AuditReport(
            version=__version__,
            timestamp=datetime.now(timezone.utc).isoformat(),
            server_info=server_info,
            transport="stdio",
            score=check_report.score,
            suites=suite_results,
            total_passed=check_report.total_passed,
            total_failed=check_report.total_failed,
            total_warned=check_report.total_warned,
            connection_ms=round(connection_ms, 2),
            discovery_ms=round(discovery_ms, 2),
            tool_count=len(all_tools),
            benchmarked_count=sum(1 for b in benchmarks if not b.skipped),
            iterations=iterations,
            warmup=warmup,
            benchmarks=benchmarks,
            total_calls=total_calls,
            total_duration_ms=round(total_duration, 2),
        )

        # ── Phase 3: Report ────────────────────────────────────────────────
        if is_json:
            print(render_audit_json(report))
        else:
            render_audit_report(console, report, verbose)

        if report.total_failed > 0:
            return EXIT_FAILURE
        return EXIT_OK
    finally:
        await client.close()


# ── watch ──────────────────────────────────────────────────────────────────────


@app.command()
def watch(
    stdio: str = typer.Option(..., "--stdio", help="Command to launch the MCP server via stdio."),
    interval: int = typer.Option(60, "--interval", "-i", help="Seconds between probes."),
    count: Optional[int] = typer.Option(None, "--count", "-c", help="Number of probes (default: infinite)."),
    log: Optional[str] = typer.Option(None, "--log", "-l", help="Append JSONL probes to this file."),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress server stderr output."
    ),
    timeout: int = typer.Option(30, "--timeout", help="Timeout in seconds per operation."),
) -> None:
    """Continuously monitor an MCP server's health."""
    exit_code = asyncio.run(_run_watch(stdio, interval, count, log, quiet, timeout))
    raise typer.Exit(exit_code)


async def _run_watch(
    command: str,
    interval: int,
    count: int | None,
    log_path: str | None,
    quiet: bool,
    timeout: int,
) -> int:
    import time

    from rich.live import Live
    from rich.text import Text

    from halflist.report import _SPINNER_FRAMES
    from halflist.watch import run_probe

    STATUS_STYLE = {
        "ok": "[green]ok[/green]",
        "degraded": "[yellow]degraded[/yellow]",
        "down": "[red]down[/red]",
    }

    log_file = None
    if log_path:
        log_file = open(log_path, "a")  # noqa: SIM115

    try:
        probe_num = 0
        while True:
            probe_start = time.monotonic()
            probe_task = asyncio.create_task(run_probe(command, quiet, timeout))
            frame = 0

            with Live(Text(""), console=console, transient=True, refresh_per_second=12) as live:
                while not probe_task.done():
                    frame += 1
                    spinner = _SPINNER_FRAMES[frame % len(_SPINNER_FRAMES)]
                    elapsed = time.monotonic() - probe_start
                    live.update(Text(f"  {spinner} Probing... {elapsed:.1f}s"))
                    await asyncio.sleep(1 / 12)

            probe = probe_task.result()
            probe_json = probe.model_dump_json()

            styled_status = STATUS_STYLE.get(probe.status, probe.status)
            ts_short = probe.timestamp[:19] if "T" in probe.timestamp else probe.timestamp
            detail = ""
            if probe.connection_ms is not None:
                detail += f"  conn={probe.connection_ms:.0f}ms"
            if probe.tool_count is not None:
                detail += f"  tools={probe.tool_count}"
            if probe.error:
                detail += f"  error={probe.error}"

            console.print(f"  [{ts_short}]  {styled_status}  {probe.probe_duration_ms:.0f}ms{detail}")

            if log_file:
                log_file.write(probe_json + "\n")
                log_file.flush()

            probe_num += 1
            if count is not None and probe_num >= count:
                break

            await asyncio.sleep(interval)

        return EXIT_OK
    finally:
        if log_file:
            log_file.close()


# ── report ─────────────────────────────────────────────────────────────────────


@app.command()
def report(
    json_file: Path = typer.Argument(..., help="Path to a halflist JSON report file."),
    format: str = typer.Option("markdown", "--format", help="Output format: markdown or html."),
    badge: bool = typer.Option(False, "--badge", help="Generate an SVG badge instead."),
    output: Optional[str] = typer.Option(None, "-o", "--output", help="Write output to file."),
) -> None:
    """Generate markdown, HTML, or badge from a halflist JSON report."""
    import json

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

    if format not in ("markdown", "html"):
        console.print(f"[red]Error:[/red] Unknown format '{format}'. Use 'markdown' or 'html'.")
        raise typer.Exit(EXIT_CONFIG_ERROR)

    if not json_file.exists():
        console.print(f"[red]Error:[/red] File not found: {json_file}")
        raise typer.Exit(EXIT_CONFIG_ERROR)

    try:
        data = json.loads(json_file.read_text())
    except json.JSONDecodeError as e:
        console.print(f"[red]Error:[/red] Invalid JSON: {e}")
        raise typer.Exit(EXIT_CONFIG_ERROR)

    if badge:
        result = render_badge_svg(data)
    else:
        report_type = detect_report_type(data)
        renderers = {
            "markdown": {"check": render_check_markdown, "bench": render_bench_markdown, "audit": render_audit_markdown},
            "html": {"check": render_check_html, "bench": render_bench_html, "audit": render_audit_html},
        }
        renderer = renderers[format].get(report_type)
        if renderer is None:
            console.print("[red]Error:[/red] Unrecognized report format.")
            raise typer.Exit(EXIT_CONFIG_ERROR)
        result = renderer(data)

    if output:
        Path(output).write_text(result)
        console.print(f"  Written to {output}")
    else:
        print(result, end="")


# ── pin ───────────────────────────────────────────────────────────────────────


@app.command()
def pin(
    stdio: str = typer.Option(..., "--stdio", help="Command to launch the MCP server via stdio."),
    output: Optional[str] = typer.Option(None, "-o", "--output", help="Write pin file to custom path."),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress server stderr output."
    ),
    timeout: int = typer.Option(30, "--timeout", help="Timeout in seconds per operation."),
) -> None:
    """Snapshot tool definitions for change detection."""
    exit_code = asyncio.run(_run_pin(stdio, output, quiet, timeout))
    raise typer.Exit(exit_code)


async def _run_pin(
    command: str,
    output_path: str | None,
    quiet: bool,
    timeout: int,
) -> int:
    import hashlib
    import json
    from datetime import datetime, timezone

    from halflist.client import HalflistClient
    from halflist.models import PinData

    client = HalflistClient(timeout=timeout, quiet=quiet)

    try:
        with console.status("[bold blue]Connecting to server via stdio...[/bold blue]"):
            try:
                await client.connect_stdio(command)
                server_info = await client.initialize()
            except Exception as e:
                console.print(f"\n  [red]✗[/red] Connection failed: {e}")
                return EXIT_TRANSPORT_ERROR

        try:
            tools = await client.list_tools()
        except Exception as e:
            console.print(f"  [red]✗[/red] Could not list tools: {e}")
            return EXIT_FAILURE

        tool_hashes: dict[str, str] = {}
        for t in tools:
            payload = json.dumps(
                {
                    "name": t.name,
                    "description": t.description,
                    "inputSchema": t.inputSchema,
                },
                sort_keys=True,
            )
            tool_hashes[t.name] = hashlib.sha256(payload.encode()).hexdigest()

        pin_data = PinData(
            server_name=server_info.name,
            server_version=server_info.version,
            timestamp=datetime.now(timezone.utc).isoformat(),
            tool_hashes=tool_hashes,
        )

        if output_path:
            pin_file = Path(output_path)
        else:
            pins_dir = Path.home() / ".halflist" / "pins"
            pins_dir.mkdir(parents=True, exist_ok=True)
            safe_name = server_info.name.replace("/", "_").replace("\\", "_")
            pin_file = pins_dir / f"{safe_name}.json"

        pin_file.write_text(pin_data.model_dump_json(indent=2) + "\n")

        console.print(
            f"  [green]✓[/green] Pinned {len(tool_hashes)} tools"
            f" from [bold]{server_info.name}[/bold] v{server_info.version}"
        )
        console.print(f"  [dim]Saved to {pin_file}[/dim]")
        return EXIT_OK
    finally:
        await client.close()
