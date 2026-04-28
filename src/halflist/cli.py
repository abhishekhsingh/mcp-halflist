from __future__ import annotations

import asyncio
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
        console.print(f"halflist v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None, "--version", callback=version_callback, is_eager=True, help="Print version and exit."
    ),
) -> None:
    pass


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
) -> None:
    """Run conformance checks against an MCP server."""
    if format not in ("terminal", "json"):
        console.print(f"[red]Error:[/red] Unknown format '{format}'. Use 'terminal' or 'json'.")
        raise typer.Exit(EXIT_CONFIG_ERROR)

    effective_quiet = quiet or format == "json"
    exit_code = asyncio.run(_run_checks(stdio, format, suite, verbose, effective_quiet, timeout))
    raise typer.Exit(exit_code)


async def _run_checks(
    command: str,
    format: str,
    suite_filter: list[str] | None,
    verbose: bool,
    quiet: bool,
    timeout: int,
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
    from halflist.suites.tools import ToolsSuite

    is_json = format == "json"
    client = HalflistClient(timeout=timeout, quiet=quiet)

    try:
        # ── Phase 1: Connection (spinner) ──────────────────────────────────
        if not is_json:
            with console.status("[bold blue]Connecting to server via stdio...[/bold blue]"):
                try:
                    await client.connect_stdio(command)
                    server_info = await client.initialize()
                except Exception as e:
                    console.print(f"\n  [red]✗[/red] Connection failed: {e}")
                    return EXIT_TRANSPORT_ERROR
        else:
            try:
                await client.connect_stdio(command)
                server_info = await client.initialize()
            except Exception as e:
                import json

                err = {"error": str(e), "exit_code": EXIT_TRANSPORT_ERROR}
                print(json.dumps(err, indent=2))
                return EXIT_TRANSPORT_ERROR

        try:
            tools = await client.list_tools()
        except Exception:
            tools = []

        if not is_json:
            print_connection(console, server_info, len(tools))

        all_suites_map = {
            "handshake": HandshakeSuite,
            "tools": ToolsSuite,
        }

        if suite_filter:
            for s in suite_filter:
                if s not in all_suites_map:
                    if not is_json:
                        console.print(f"[red]Error:[/red] Unknown suite '{s}'")
                    return EXIT_CONFIG_ERROR
            suites_to_run = {k: v for k, v in all_suites_map.items() if k in suite_filter}
        else:
            suites_to_run = all_suites_map

        suite_results: list[SuiteResult] = []

        # ── Phase 2: Live progress ─────────────────────────────────────────
        if not is_json:
            progress = LiveProgress(list(suites_to_run.keys()))

            with Live(
                progress.render(), console=console, transient=True, refresh_per_second=12
            ) as live:
                for name, suite_cls in suites_to_run.items():
                    progress.set_current(name)
                    live.update(progress.render())

                    def on_check(check, _live=live, _progress=progress):  # type: ignore[assignment]
                        _progress.add_check(check)
                        _live.update(_progress.render())

                    suite_instance = suite_cls(client, on_check=on_check)
                    result = await suite_instance.run()
                    suite_results.append(result)

                progress.set_current(None)
                live.update(progress.render())
        else:
            for _name, suite_cls in suites_to_run.items():
                suite_instance = suite_cls(client)
                result = await suite_instance.run()
                suite_results.append(result)

        report = build_report(server_info, suite_results)

        # ── Phase 3: Final report ──────────────────────────────────────────
        if is_json:
            print(render_json(report))
        else:
            render_final_report(console, report, verbose)

        if report.total_failed > 0:
            return EXIT_FAILURE
        return EXIT_OK
    finally:
        await client.close()
