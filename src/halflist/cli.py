from __future__ import annotations

import asyncio
import io
import sys
from pathlib import Path
from typing import Any, Optional

import typer
from rich.console import Console

from halflist import __version__
from halflist.constants import DEFAULT_TIMEOUT, EXIT_CONFIG_ERROR, EXIT_FAILURE, EXIT_OK, EXIT_TRANSPORT_ERROR

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


# ── Shared helpers ────────────────────────────────────────────────────────────


def _validate_transport(
    stdio: str | None,
    http: str | None,
    header: list[str] | None,
    oauth_token_url: str | None,
    oauth_client_id: str | None,
    oauth_client_secret: str | None,
) -> int | None:
    """Validate transport flags. Returns exit code on error, None on success."""
    if stdio and http:
        console.print("[red]Error:[/red] --stdio and --http are mutually exclusive.")
        return EXIT_CONFIG_ERROR
    if not stdio and not http:
        console.print("[red]Error:[/red] Provide --stdio or --http.")
        return EXIT_CONFIG_ERROR

    has_auth = bool(header) or bool(oauth_token_url)
    if has_auth and stdio:
        console.print("[red]Error:[/red] --header and --oauth-* flags require --http, not --stdio.")
        return EXIT_CONFIG_ERROR

    oauth_flags = [oauth_token_url, oauth_client_id, oauth_client_secret]
    oauth_set = sum(1 for f in oauth_flags if f)
    if 0 < oauth_set < 3:
        console.print(
            "[red]Error:[/red] OAuth requires all of --oauth-token-url, --oauth-client-id, --oauth-client-secret."
        )
        return EXIT_CONFIG_ERROR

    return None


async def _resolve_headers(
    header: list[str] | None,
    oauth_token_url: str | None,
    oauth_client_id: str | None,
    oauth_client_secret: str | None,
    oauth_scope: str | None,
    progress_console: Console,
) -> dict[str, str] | None:
    """Build headers dict from --header and/or --oauth-* flags."""
    headers: dict[str, str] = {}

    if header:
        for h in header:
            if ": " not in h:
                progress_console.print(f"[red]Error:[/red] Invalid header format: '{h}'. Use 'Key: Value'.")
                raise typer.Exit(EXIT_CONFIG_ERROR)
            key, val = h.split(": ", 1)
            headers[key] = val

    if oauth_token_url and oauth_client_id and oauth_client_secret:
        from halflist.auth import fetch_oauth_token

        if "Authorization" in headers:
            progress_console.print("  [yellow]⚠[/yellow] OAuth token takes precedence over --header Authorization")

        try:
            token = await fetch_oauth_token(
                oauth_token_url, oauth_client_id, oauth_client_secret, oauth_scope,
            )
        except Exception as e:
            progress_console.print(f"[red]Error:[/red] OAuth token fetch failed: {e}")
            raise typer.Exit(EXIT_TRANSPORT_ERROR)

        headers["Authorization"] = f"Bearer {token}"

    return headers or None


async def _connect_client(
    client: Any,
    stdio: str | None,
    http: str | None,
    headers: dict[str, str] | None,
) -> None:
    """Connect client via the appropriate transport."""
    if stdio:
        await client.connect_stdio(stdio)
    else:
        assert http is not None
        await client.connect_http(http, headers)


async def _discover(
    client: Any,
    progress_console: Console | None = None,
) -> tuple[list, int | None, int | None]:
    """Discover tools, and optionally resources/prompts counts."""
    try:
        tools = await client.list_tools()
    except Exception as e:
        tools = []
        if progress_console:
            progress_console.print(f"  [yellow]⚠[/yellow] Tool discovery failed: {e}")

    resource_count: int | None = None
    if client.has_capability("resources"):
        try:
            resources = await client.list_resources()
            resource_count = len(resources)
        except Exception as e:
            resource_count = 0
            if progress_console:
                progress_console.print(f"  [yellow]⚠[/yellow] Resource discovery failed: {e}")

    prompt_count: int | None = None
    if client.has_capability("prompts"):
        try:
            prompts = await client.list_prompts()
            prompt_count = len(prompts)
        except Exception as e:
            prompt_count = 0
            if progress_console:
                progress_console.print(f"  [yellow]⚠[/yellow] Prompt discovery failed: {e}")

    return tools, resource_count, prompt_count


def _build_suite_map() -> dict[str, type]:
    from halflist.suites.handshake import HandshakeSuite
    from halflist.suites.prompts import PromptsSuite
    from halflist.suites.resources import ResourcesSuite
    from halflist.suites.security import SecuritySuite
    from halflist.suites.tools import ToolsSuite

    return {
        "handshake": HandshakeSuite,
        "tools": ToolsSuite,
        "resources": ResourcesSuite,
        "prompts": PromptsSuite,
        "security": SecuritySuite,
    }


# ── check ─────────────────────────────────────────────────────────────────────


@app.command()
def check(
    stdio: Optional[str] = typer.Option(None, "--stdio", help="Command to launch the MCP server via stdio."),
    http: Optional[str] = typer.Option(None, "--http", help="URL of the MCP server via HTTP."),
    header: Optional[list[str]] = typer.Option(None, "--header", help="HTTP header (Key: Value). Repeatable."),
    oauth_token_url: Optional[str] = typer.Option(None, "--oauth-token-url", help="OAuth2 token endpoint URL."),
    oauth_client_id: Optional[str] = typer.Option(None, "--oauth-client-id", help="OAuth2 client ID."),
    oauth_client_secret: Optional[str] = typer.Option(None, "--oauth-client-secret", help="OAuth2 client secret."),
    oauth_scope: Optional[str] = typer.Option(None, "--oauth-scope", help="OAuth2 scope."),
    format: str = typer.Option("terminal", "--format", help="Output format: terminal or json."),
    suite: Optional[list[str]] = typer.Option(None, "--suite", help="Suite(s) to run. Repeatable."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show all check details."),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress server stderr output. Auto-enabled with --format json."
    ),
    timeout: int = typer.Option(DEFAULT_TIMEOUT, "--timeout", help="Timeout in seconds per operation."),
    verify_pins: bool = typer.Option(False, "--verify-pins", help="Verify tool pins against saved snapshot."),
) -> None:
    """Run conformance checks against an MCP server."""
    if format not in ("terminal", "json"):
        console.print(f"[red]Error:[/red] Unknown format '{format}'. Use 'terminal' or 'json'.")
        raise typer.Exit(EXIT_CONFIG_ERROR)

    err = _validate_transport(stdio, http, header, oauth_token_url, oauth_client_id, oauth_client_secret)
    if err is not None:
        raise typer.Exit(err)

    effective_quiet = quiet or format == "json"
    exit_code = asyncio.run(
        _run_checks(
            stdio, http, header, oauth_token_url, oauth_client_id, oauth_client_secret, oauth_scope,
            format, suite, verbose, effective_quiet, timeout, verify_pins,
        )
    )
    raise typer.Exit(exit_code)


async def _run_checks(
    stdio: str | None,
    http: str | None,
    header: list[str] | None,
    oauth_token_url: str | None,
    oauth_client_id: str | None,
    oauth_client_secret: str | None,
    oauth_scope: str | None,
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
        print_banner,
        print_connection,
        render_final_report,
        render_json,
    )
    from halflist.suites.security import SecuritySuite

    is_json = format == "json"
    progress_console = Console(stderr=True) if is_json and sys.stderr.isatty() else Console(file=io.StringIO()) if is_json else console
    client = HalflistClient(timeout=timeout, quiet=quiet)

    try:
        if not is_json:
            print_banner(progress_console)

        headers = await _resolve_headers(
            header, oauth_token_url, oauth_client_id, oauth_client_secret, oauth_scope, progress_console,
        )

        with progress_console.status("[bold blue]Connecting to server...[/bold blue]"):
            try:
                await _connect_client(client, stdio, http, headers)
                server_info = await client.initialize()
            except Exception as e:
                if is_json:
                    import json

                    err = {"error": str(e), "exit_code": EXIT_TRANSPORT_ERROR}
                    print(json.dumps(err, indent=2))
                else:
                    console.print(f"\n  [red]✗[/red] Connection failed: {e}")
                return EXIT_TRANSPORT_ERROR

        tools, resource_count, prompt_count = await _discover(client, progress_console)
        print_connection(
            progress_console, server_info, len(tools),
            resource_count, prompt_count, client.transport,
        )

        all_suites_map = _build_suite_map()

        if suite_filter:
            for s in suite_filter:
                if s not in all_suites_map:
                    progress_console.print(f"[red]Error:[/red] Unknown suite '{s}'")
                    return EXIT_CONFIG_ERROR
            suites_to_run = {k: v for k, v in all_suites_map.items() if k in suite_filter}
        else:
            suites_to_run = all_suites_map

        suite_results: list[SuiteResult] = []

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

        report = build_report(server_info, suite_results, transport=client.transport)

        if is_json:
            print(render_json(report))
        else:
            render_final_report(console, report, verbose, is_filtered=bool(suite_filter))

        if report.total_failed > 0:
            return EXIT_FAILURE
        return EXIT_OK
    finally:
        await client.close()


# ── bench ─────────────────────────────────────────────────────────────────────


@app.command()
def bench(
    stdio: Optional[str] = typer.Option(None, "--stdio", help="Command to launch the MCP server via stdio."),
    http: Optional[str] = typer.Option(None, "--http", help="URL of the MCP server via HTTP."),
    header: Optional[list[str]] = typer.Option(None, "--header", help="HTTP header (Key: Value). Repeatable."),
    oauth_token_url: Optional[str] = typer.Option(None, "--oauth-token-url", help="OAuth2 token endpoint URL."),
    oauth_client_id: Optional[str] = typer.Option(None, "--oauth-client-id", help="OAuth2 client ID."),
    oauth_client_secret: Optional[str] = typer.Option(None, "--oauth-client-secret", help="OAuth2 client secret."),
    oauth_scope: Optional[str] = typer.Option(None, "--oauth-scope", help="OAuth2 scope."),
    tool: Optional[list[str]] = typer.Option(None, "--tool", help="Tool(s) to benchmark. Repeatable."),
    all_tools: bool = typer.Option(False, "--all", help="Benchmark all tools (default: first 5)."),
    iterations: int = typer.Option(10, "--iterations", "-n", help="Number of iterations per tool."),
    warmup: int = typer.Option(2, "--warmup", "-w", help="Warmup iterations (discarded)."),
    format: str = typer.Option("terminal", "--format", help="Output format: terminal or json."),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress server stderr output. Auto-enabled with --format json."
    ),
    timeout: int = typer.Option(DEFAULT_TIMEOUT, "--timeout", help="Timeout in seconds per operation."),
) -> None:
    """Benchmark latency per tool on an MCP server."""
    if format not in ("terminal", "json"):
        console.print(f"[red]Error:[/red] Unknown format '{format}'. Use 'terminal' or 'json'.")
        raise typer.Exit(EXIT_CONFIG_ERROR)

    err = _validate_transport(stdio, http, header, oauth_token_url, oauth_client_id, oauth_client_secret)
    if err is not None:
        raise typer.Exit(err)

    effective_quiet = quiet or format == "json"
    exit_code = asyncio.run(
        _run_bench(
            stdio, http, header, oauth_token_url, oauth_client_id, oauth_client_secret, oauth_scope,
            tool, all_tools, iterations, warmup, format, effective_quiet, timeout,
        )
    )
    raise typer.Exit(exit_code)


async def _run_bench(
    stdio: str | None,
    http: str | None,
    header: list[str] | None,
    oauth_token_url: str | None,
    oauth_client_id: str | None,
    oauth_client_secret: str | None,
    oauth_scope: str | None,
    tool_names: list[str] | None,
    bench_all: bool,
    iterations: int,
    warmup: int,
    format: str,
    quiet: bool,
    timeout: int,
) -> int:
    import time
    from datetime import datetime, timezone

    from rich.live import Live

    from halflist.bench import bench_tool, select_tools
    from halflist.client import HalflistClient
    from halflist.models import BenchReport, ToolBenchmark
    from halflist.report import BenchLiveProgress, print_banner, print_connection, render_bench_json, render_bench_report

    is_json = format == "json"
    progress_console = Console(stderr=True) if is_json and sys.stderr.isatty() else Console(file=io.StringIO()) if is_json else console
    client = HalflistClient(timeout=timeout, quiet=quiet)

    try:
        if not is_json:
            print_banner(progress_console)

        headers = await _resolve_headers(
            header, oauth_token_url, oauth_client_id, oauth_client_secret, oauth_scope, progress_console,
        )

        with progress_console.status("[bold blue]Connecting to server...[/bold blue]"):
            try:
                t0 = time.monotonic()
                await _connect_client(client, stdio, http, headers)
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
        except Exception as e:
            all_tool_list = []
            progress_console.print(f"  [yellow]⚠[/yellow] Tool discovery failed: {e}")
        discovery_ms = (time.monotonic() - t_disc) * 1000

        selected = select_tools(all_tool_list, tool_names, bench_all)

        print_connection(progress_console, server_info, len(all_tool_list), transport=client.transport)

        if not selected:
            progress_console.print("  [yellow]No tools to benchmark.[/yellow]")
            return EXIT_OK

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
            timestamp=datetime.now(timezone.utc).isoformat(),
            server_info=server_info,
            transport=client.transport,
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

        if is_json:
            print(render_bench_json(report))
        else:
            render_bench_report(console, report)

        return EXIT_OK
    finally:
        await client.close()


# ── audit ─────────────────────────────────────────────────────────────────────


@app.command()
def audit(
    stdio: Optional[str] = typer.Option(None, "--stdio", help="Command to launch the MCP server via stdio."),
    http: Optional[str] = typer.Option(None, "--http", help="URL of the MCP server via HTTP."),
    header: Optional[list[str]] = typer.Option(None, "--header", help="HTTP header (Key: Value). Repeatable."),
    oauth_token_url: Optional[str] = typer.Option(None, "--oauth-token-url", help="OAuth2 token endpoint URL."),
    oauth_client_id: Optional[str] = typer.Option(None, "--oauth-client-id", help="OAuth2 client ID."),
    oauth_client_secret: Optional[str] = typer.Option(None, "--oauth-client-secret", help="OAuth2 client secret."),
    oauth_scope: Optional[str] = typer.Option(None, "--oauth-scope", help="OAuth2 scope."),
    iterations: int = typer.Option(10, "--iterations", "-n", help="Benchmark iterations per tool."),
    warmup: int = typer.Option(2, "--warmup", "-w", help="Warmup iterations (discarded)."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show all check details."),
    format: str = typer.Option("terminal", "--format", help="Output format: terminal or json."),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress server stderr output. Auto-enabled with --format json."
    ),
    timeout: int = typer.Option(DEFAULT_TIMEOUT, "--timeout", help="Timeout in seconds per operation."),
    verify_pins: bool = typer.Option(False, "--verify-pins", help="Verify tool pins against saved snapshot."),
) -> None:
    """Run full conformance check + benchmark in one shot."""
    if format not in ("terminal", "json"):
        console.print(f"[red]Error:[/red] Unknown format '{format}'. Use 'terminal' or 'json'.")
        raise typer.Exit(EXIT_CONFIG_ERROR)

    err = _validate_transport(stdio, http, header, oauth_token_url, oauth_client_id, oauth_client_secret)
    if err is not None:
        raise typer.Exit(err)

    effective_quiet = quiet or format == "json"
    exit_code = asyncio.run(
        _run_audit(
            stdio, http, header, oauth_token_url, oauth_client_id, oauth_client_secret, oauth_scope,
            iterations, warmup, verbose, format, effective_quiet, timeout, verify_pins,
        )
    )
    raise typer.Exit(exit_code)


async def _run_audit(
    stdio: str | None,
    http: str | None,
    header: list[str] | None,
    oauth_token_url: str | None,
    oauth_client_id: str | None,
    oauth_client_secret: str | None,
    oauth_scope: str | None,
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
        print_banner,
        print_connection,
        render_audit_json,
        render_audit_report,
    )
    from halflist.suites.security import SecuritySuite

    is_json = format == "json"
    progress_console = Console(stderr=True) if is_json and sys.stderr.isatty() else Console(file=io.StringIO()) if is_json else console
    client = HalflistClient(timeout=timeout, quiet=quiet)

    try:
        if not is_json:
            print_banner(progress_console)

        headers = await _resolve_headers(
            header, oauth_token_url, oauth_client_id, oauth_client_secret, oauth_scope, progress_console,
        )

        with progress_console.status("[bold blue]Connecting to server...[/bold blue]"):
            try:
                t0 = time.monotonic()
                await _connect_client(client, stdio, http, headers)
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
        tools, resource_count, prompt_count = await _discover(client, progress_console)
        all_tools = tools
        discovery_ms = (time.monotonic() - t_disc) * 1000

        print_connection(
            progress_console, server_info, len(all_tools),
            resource_count, prompt_count, client.transport,
        )

        all_suites_map = _build_suite_map()

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

        check_report = build_report(server_info, suite_results, transport=client.transport)

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
            transport=client.transport,
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

        if is_json:
            print(render_audit_json(report))
        else:
            render_audit_report(console, report, verbose)

        if report.total_failed > 0:
            return EXIT_FAILURE
        return EXIT_OK
    finally:
        await client.close()


# ── watch ─────────────────────────────────────────────────────────────────────


@app.command()
def watch(
    stdio: Optional[str] = typer.Option(None, "--stdio", help="Command to launch the MCP server via stdio."),
    http: Optional[str] = typer.Option(None, "--http", help="URL of the MCP server via HTTP."),
    header: Optional[list[str]] = typer.Option(None, "--header", help="HTTP header (Key: Value). Repeatable."),
    oauth_token_url: Optional[str] = typer.Option(None, "--oauth-token-url", help="OAuth2 token endpoint URL."),
    oauth_client_id: Optional[str] = typer.Option(None, "--oauth-client-id", help="OAuth2 client ID."),
    oauth_client_secret: Optional[str] = typer.Option(None, "--oauth-client-secret", help="OAuth2 client secret."),
    oauth_scope: Optional[str] = typer.Option(None, "--oauth-scope", help="OAuth2 scope."),
    interval: int = typer.Option(60, "--interval", "-i", help="Seconds between probes."),
    count: Optional[int] = typer.Option(None, "--count", "-c", help="Number of probes (default: infinite)."),
    log: Optional[str] = typer.Option(None, "--log", "-l", help="Append JSONL probes to this file."),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress server stderr output."
    ),
    timeout: int = typer.Option(DEFAULT_TIMEOUT, "--timeout", help="Timeout in seconds per operation."),
) -> None:
    """Continuously monitor an MCP server's health."""
    err = _validate_transport(stdio, http, header, oauth_token_url, oauth_client_id, oauth_client_secret)
    if err is not None:
        raise typer.Exit(err)

    exit_code = asyncio.run(
        _run_watch(
            stdio, http, header, oauth_token_url, oauth_client_id, oauth_client_secret, oauth_scope,
            interval, count, log, quiet, timeout,
        )
    )
    raise typer.Exit(exit_code)


async def _run_watch(
    stdio: str | None,
    http: str | None,
    header: list[str] | None,
    oauth_token_url: str | None,
    oauth_client_id: str | None,
    oauth_client_secret: str | None,
    oauth_scope: str | None,
    interval: int,
    count: int | None,
    log_path: str | None,
    quiet: bool,
    timeout: int,
) -> int:
    import time

    from rich.live import Live
    from rich.text import Text

    from halflist.report import _SPINNER_FRAMES, print_banner
    from halflist.watch import run_probe

    _WATCH_STATUS = {
        "ok": ("OK", "green"),
        "degraded": ("DEGRADED", "yellow"),
        "down": ("DOWN", "red"),
    }

    print_banner(console)

    headers = await _resolve_headers(
        header, oauth_token_url, oauth_client_id, oauth_client_secret, oauth_scope, console,
    )

    log_file = None
    if log_path:
        log_file = open(log_path, "a")  # noqa: SIM115

    try:
        probe_num = 0
        while True:
            probe_start = time.monotonic()
            probe_task = asyncio.create_task(
                run_probe(stdio=stdio, http_url=http, headers=headers, quiet=quiet, timeout=timeout)
            )
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

            probe_num += 1
            label, color = _WATCH_STATUS.get(probe.status, (probe.status.upper(), "white"))
            ts_short = probe.timestamp[11:19] if "T" in probe.timestamp else probe.timestamp

            line = Text(f"  #{probe_num:<3} ")
            line.append(f"[{ts_short}]  ", style="dim")
            line.append("██", style=color)
            line.append(f" {label:<11}", style=f"bold {color}")
            dur_s = probe.probe_duration_ms / 1000
            line.append(f"{dur_s:.1f}s", style="dim")
            if probe.connection_ms is not None:
                line.append(f"  conn={probe.connection_ms:.0f}ms", style="dim")
            if probe.tool_count is not None:
                line.append(f"  tools={probe.tool_count}", style="dim")
            if probe.error:
                line.append(f"  {probe.error}", style="dim red")

            console.print(line)

            if log_file:
                log_file.write(probe_json + "\n")
                log_file.flush()

            if count is not None and probe_num >= count:
                break

            await asyncio.sleep(interval)

        return EXIT_OK
    finally:
        if log_file:
            log_file.close()


# ── report ────────────────────────────────────────────────────────────────────


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


# ── pin ──────────────────────────────────────────────────────────────────────


@app.command()
def pin(
    stdio: Optional[str] = typer.Option(None, "--stdio", help="Command to launch the MCP server via stdio."),
    http: Optional[str] = typer.Option(None, "--http", help="URL of the MCP server via HTTP."),
    header: Optional[list[str]] = typer.Option(None, "--header", help="HTTP header (Key: Value). Repeatable."),
    oauth_token_url: Optional[str] = typer.Option(None, "--oauth-token-url", help="OAuth2 token endpoint URL."),
    oauth_client_id: Optional[str] = typer.Option(None, "--oauth-client-id", help="OAuth2 client ID."),
    oauth_client_secret: Optional[str] = typer.Option(None, "--oauth-client-secret", help="OAuth2 client secret."),
    oauth_scope: Optional[str] = typer.Option(None, "--oauth-scope", help="OAuth2 scope."),
    output: Optional[str] = typer.Option(None, "-o", "--output", help="Write pin file to custom path."),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress server stderr output."
    ),
    timeout: int = typer.Option(DEFAULT_TIMEOUT, "--timeout", help="Timeout in seconds per operation."),
) -> None:
    """Snapshot tool definitions for change detection."""
    err = _validate_transport(stdio, http, header, oauth_token_url, oauth_client_id, oauth_client_secret)
    if err is not None:
        raise typer.Exit(err)

    exit_code = asyncio.run(
        _run_pin(
            stdio, http, header, oauth_token_url, oauth_client_id, oauth_client_secret, oauth_scope,
            output, quiet, timeout,
        )
    )
    raise typer.Exit(exit_code)


async def _run_pin(
    stdio: str | None,
    http: str | None,
    header: list[str] | None,
    oauth_token_url: str | None,
    oauth_client_id: str | None,
    oauth_client_secret: str | None,
    oauth_scope: str | None,
    output_path: str | None,
    quiet: bool,
    timeout: int,
) -> int:
    import hashlib
    import json
    from datetime import datetime, timezone

    from halflist.client import HalflistClient
    from halflist.models import PinData
    from halflist.report import print_banner

    client = HalflistClient(timeout=timeout, quiet=quiet)

    try:
        print_banner(console)

        headers = await _resolve_headers(
            header, oauth_token_url, oauth_client_id, oauth_client_secret, oauth_scope, console,
        )

        with console.status("[bold blue]Connecting to server...[/bold blue]"):
            try:
                await _connect_client(client, stdio, http, headers)
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
